"""Detached job runner:  pythonw -m lps.runner <job folder>

Runs a saved, verified job on the controller and keeps going if the app is closed. Progress, the last command
handed to the port and the resume point are written to state.json continuously. It never homes, never restarts
itself after a fault, and stops cleanly on request (finishing the current row so position is kept).
"""
from __future__ import annotations

import ctypes
import datetime as dt
import math
import os
import sys
import time
import traceback
from pathlib import Path

from . import jobs, recovery, position_memory
from .machine import (ControllerError, Grbl, LinkError, SerialWire, check_settings, require_off)


class Runner:
    def __init__(self, folder, wire=None, settle: float = 1.0, heartbeat: float = 5.0):
        self.folder = Path(folder)
        self.job = jobs.read_json(self.folder / "job.json")
        if not self.job:
            raise SystemExit(f"no job.json in {folder}")
        self.spec = jobs.read_json(self.folder / "run.json", {}) or {}
        self.wire = wire
        self.settle = settle
        self.heartbeat = heartbeat
        self.g: Grbl | None = None
        self.ctl_seq = int(self.spec.get("control_seq",
                                         (jobs.read_json(self.folder / "control.json", {}) or {}).get("seq", 0)))
        self.next_ctl = 0.0
        self.paused = False
        self.paused_by_machine = False
        self.stop_req = self.estop_req = False
        self.last_xy = None
        self.last_written = -1
        self.pi = int(self.spec.get("start_pass", 0))
        self.last_status_at = time.monotonic()
        self.last_motion_at = time.monotonic()
        self.last_wpos = None
        self.active_s = 0.0
        self.active_mark = None
        self.parking = False
        self.next_save = 0.0
        self.memory = position_memory.PositionMemory(self.spec.get("position_memory_path") or
                                                     self.folder / "position-memory.json")
        m = self.job["material"]
        self.hop = int(m.get("hop_feed", 3000))
        self.env = self.job.get("envelope")
        park = self.spec.get("park", [0.0, 0.0])
        self.park_xy = (float(park[0]), float(park[1]))
        self.state = dict(phase="starting", message="Starting...", pid=os.getpid(), job=self.job["name"],
                          started=dt.datetime.now().isoformat(timespec="seconds"), pass_index=self.pi,
                          pass_count=len(self.job["passes"]), completed=list(self.spec.get("completed", [])),
                          resume=None, laser_on=False, wpos=None, controller="", sent=0, pass_total=0,
                          last_written=None, last_xy=None, progress=0.0, remaining_s=None, elapsed_s=0.0,
                          demo=bool(self.spec.get("demo")))

    # ---------------------------------------------------------------- bookkeeping
    def log(self, msg: str):
        line = f"{dt.datetime.now():%H:%M:%S} {msg}"
        try:
            with open(self.folder / "log.txt", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def save(self, force=False):
        now = time.monotonic()
        if not force and now < self.next_save:
            return
        self.next_save = now + 0.25
        if self.active_mark is not None:
            self.active_s += now - self.active_mark
            self.active_mark = now
        self.state["elapsed_s"] = round(self.active_s, 1)
        self.state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        self.state["position_record"] = self.memory.data
        if self.memory.enabled:
            self.memory.save()
        self._progress()
        if self.state.get("demo") and self.wire is not None and hasattr(self.wire, "ctrl"):
            c = self.wire.ctrl
            self.state["demo_state"] = dict(phys=c.phys, morg=c.morg, wco=c.wco)
        try:
            jobs.write_json(self.folder / "state.json", self.state)
        except OSError:
            pass

    def phase(self, phase: str, message: str):
        self.state["phase"], self.state["message"] = phase, message
        self.log(f"[{phase}] {message}")
        self.save(force=True)

    def _progress(self):
        ps = self.job["passes"]
        est = [max(1.0, float(p.get("est_s", 1.0))) for p in ps]
        total = sum(est)
        done = sum(est[i] for i in self.state["completed"] if i < len(est))
        if self.state["phase"] in ("running", "paused") and self.pi < len(est) and self.pi not in self.state["completed"]:
            frac = self.state["sent"] / max(1, self.state["pass_total"])
            done += est[self.pi] * min(1.0, frac)
        self.state["progress"] = round(min(1.0, done / total), 4) if total else 0.0
        rate = self.active_s / done if done > 30 and self.active_s > 30 else 1.0
        self.state["remaining_s"] = round(max(0.0, total - done) * max(0.5, min(3.0, rate)), 0)

    # ---------------------------------------------------------------- control file
    def check_control(self):
        now = time.monotonic()
        if now < self.next_ctl:
            return None
        self.next_ctl = now + 0.1
        c = jobs.read_json(self.folder / "control.json", {}) or {}
        seq = int(c.get("seq", 0))
        if seq <= self.ctl_seq:
            return None
        self.ctl_seq = seq
        cmd = c.get("cmd")
        self.log(f"request: {cmd}")
        if cmd == "pause" and not self.paused:
            self.g.realtime(b"!")
            self.paused = True
            self.phase("paused", "Paused (feed hold). Laser is off while held. Press Resume to continue.")
        elif cmd == "resume" and self.paused:
            self.g.realtime(b"~")
            self.paused = self.paused_by_machine = False
            self.phase("running", "Running.")
        elif cmd == "stop":
            self.stop_req = True
            if self.paused:
                self.g.realtime(b"~")
                self.paused = False
            self.phase("stopping", "Stopping after the current row (keeps position)...")
        elif cmd == "estop":
            self.estop_req = True
        return cmd

    # ---------------------------------------------------------------- watchdogs
    def watch(self):
        now = time.monotonic()
        g = self.g
        st = g.status
        if st is not None and st.at > self.last_status_at:
            self.last_status_at = st.at
            self.state["controller"] = st.state + (f":{st.sub}" if st.sub else "")
            self.state["laser_on"] = st.laser_on
            if st.wpos:
                wp = (round(st.wpos[0], 3), round(st.wpos[1], 3))
                if wp != self.last_wpos:
                    self.last_wpos = wp
                    self.last_motion_at = now
                self.state["wpos"] = list(wp)
                self.state["position_at"] = time.time()
                e = self.env
                if e and not self.parking and not (e[0] - 1 <= wp[0] <= e[2] + 1 and e[1] - 1 <= wp[1] <= e[3] + 1):
                    raise ControllerError(f"Head reported at X{wp[0]} Y{wp[1]}, outside this job's area. Stopped.")
            if st.state in ("Alarm", "Door", "Sleep"):
                raise ControllerError(f"Controller went to {st.state}.")
            if st.state == "Hold" and not self.paused:
                self.paused = self.paused_by_machine = True
                self.phase("paused", "Paused at the machine. Resume there, or press Resume here.")
            elif st.state == "Run" and self.paused and self.paused_by_machine:
                self.paused = self.paused_by_machine = False
                self.phase("running", "Running.")
            if st.ov and tuple(st.ov[:3]) != (100, 100, 100):
                raise ControllerError(f"Speed/power override changed at the machine ({st.ov}). Set it back to 100%.")
        if now - self.last_status_at > self.heartbeat:
            raise LinkError(f"The controller stopped answering (no status for {self.heartbeat:.0f} s).")
        if g.reset_seen:
            raise LinkError("The controller restarted during the job.")
        if g.errors:
            raise ControllerError(f"The controller rejected a command ({g.errors[0]}).")
        if g.alarm:
            raise ControllerError(f"Controller alarm ({g.alarm}).")
        if g.pending and not self.paused and now - g.last_ack_at > 15:
            if (st is None or st.state not in ("Run", "Jog")) or now - self.last_motion_at > 5:
                raise ControllerError("No acknowledgement and no movement for 15 s.")

    def poll(self, interval=0.2):
        now = time.monotonic()
        if now - getattr(self, "_polled", 0.0) >= interval:
            self._polled = now
            self.g.realtime(b"?")
        self.g.pump()

    def wait_idle(self, timeout=600.0):
        end = time.monotonic() + timeout
        seen = self.g.status_serial
        while time.monotonic() < end:
            self.poll(0.15)
            self.watch()
            st = self.g.status
            if self.g.status_serial > seen and st and st.state == "Idle" and not self.g.pending:
                self.memory.settled(st)
                return st
            self.save()
            time.sleep(0.01)
        raise ControllerError("The machine didn't come to rest in time.")

    # ---------------------------------------------------------------- phases
    def connect(self):
        self.phase("connecting", "Opening the USB port...")
        if self.wire is None:
            if self.spec.get("demo"):
                from .fakegrbl import FakeController, FakeWire
                ctrl = FakeController(speedup=float(self.spec.get("demo_speed", 25.0)))
                ctrl.take_output()
                ds = self.spec.get("demo_state") or {}
                ctrl.phys, ctrl.morg, ctrl.wco = (list(ds.get(k, [0.0, 0.0])) for k in ("phys", "morg", "wco"))
                self.wire = FakeWire(ctrl)
                self.settle = 0.05
            else:
                self.wire = SerialWire(self.spec.get("port", "COM4"), int(self.spec.get("baud", 115200)))
        self.g = Grbl(self.wire, log=self.log, observer=self.memory.protocol)
        self.g.open(settle=self.settle)
        if self.g.reset_seen:
            raise ControllerError("The controller restarted when the job connected, so its position can't be "
                                  "trusted. Nothing was burned. Re-check the start point/perimeter and start again.")
        self.g.command("M5 S0")
        st = self.g.query_status()
        self.last_status_at = time.monotonic()
        if st.state != "Idle" or not st.idle_off:
            raise ControllerError(f"Machine is {st.state} (feed {st.feed:g}, laser {st.spindle:g}); nothing was sent.")
        exp = self.spec.get("expected_start")
        if exp is not None:
            if not st.wpos or math.hypot(st.wpos[0] - exp[0], st.wpos[1] - exp[1]) > 0.05:
                raise ControllerError(f"Head is at {st.wpos}, expected X{exp[0]} Y{exp[1]}. Nothing was sent. "
                                      "Re-check the start point.")
        problems = check_settings(self.g.settings())
        if problems:
            raise ControllerError("Controller settings changed: " + ", ".join(problems) + ". Nothing was sent.")
        require_off(self.g, 0)
        self.g.command("G21 G90 G94 G54 M5 S0")
        st = self.wait_idle(25)
        self.memory.arm(st, self.spec.get("setup_context") or dict(job_folder=str(self.folder)))

    def load_passes(self):
        out = []
        for p in self.job["passes"]:
            f = self.folder / p["file"]
            if jobs.sha256(f) != p["sha256"]:
                raise ControllerError(f"{p['file']} changed after it was checked. Re-save the job.")
            out.append(jobs.read_body(f))
        return out

    def stream(self, items, body) -> str:
        g = self.g
        i = 0
        armed = False
        stop_after = False
        self.state["pass_total"] = len(body)
        self.memory.begin("engraving", dict(job_folder=str(self.folder), pass_index=self.pi,
                                            start_index=self.state["sent"], pass_total=len(body)))
        while True:
            self.check_control()
            if self.estop_req:
                return "estop"
            if self.stop_req:
                stop_after = True
            if not self.paused:
                while i < len(items):
                    cmd, bi = items[i]
                    if stop_after and not armed:
                        break
                    if not g.can_send(cmd):
                        break
                    g.send(cmd)
                    if cmd == "M4 S0":
                        armed = True
                    elif cmd == "M5 S0":
                        armed = False
                    else:
                        p = recovery.xy(cmd)
                        if p:
                            self.last_xy = p
                    if bi is not None:
                        self.last_written = bi
                        self.state["sent"] = bi + 1
                    self.state["last_written"] = [self.pi, self.last_written]
                    self.state["last_xy"] = list(self.last_xy) if self.last_xy else None
                    i += 1
            self.poll()
            accepted = i - len(g.pending)
            body_indices = [bi for _, bi in items[max(0, accepted - 8):accepted] if bi is not None]
            if body_indices:
                self.state["last_accepted"] = [self.pi, body_indices[-1]]
            self.watch()
            if i >= len(items) and not g.pending:
                return "done"
            if stop_after and not armed and not g.pending:
                nxt = next((bi for _, bi in items[i:] if bi is not None), len(body))
                return f"stop:{nxt}"
            self.save()
            time.sleep(0.002)

    def park(self, final=False):
        self.parking = True
        try:
            self.memory.begin("park", dict(target=self.park_xy))
            self.g.command("M5 S0")
            self.g.command(f"G1 X{self.park_xy[0]:.3f} Y{self.park_xy[1]:.3f} F{self.hop} S0")
            self.last_xy = self.park_xy
            st = self.wait_idle(300)
            if final and (not st.wpos or math.hypot(st.wpos[0] - self.park_xy[0], st.wpos[1] - self.park_xy[1]) > 0.05):
                raise ControllerError(f"Park position not confirmed ({st.wpos}).")
            require_off(self.g, 0)
        finally:
            self.parking = False

    def wait_photo(self, title: str) -> bool:
        n = len(self.job["passes"])
        self.state["photo_wait_since"] = dt.datetime.now().isoformat(timespec="seconds")
        self.phase("waiting_photo", f"{title} done ({self.pi + 1} of {n}). Head parked, laser off. Take your photo, "
                                    "then press Continue.")
        self.active_mark = None
        while True:
            cmd = self.check_control()
            if cmd == "continue":
                break
            if cmd == "stop" or self.estop_req:
                return False
            self.poll(0.5)
            self.watch()
            self.save()
            time.sleep(0.05)
        self.active_mark = time.monotonic()
        self.state["photo_wait_since"] = None
        return True

    def estop(self) -> tuple:
        """Feed hold, wait for the stop, then reset: laser off at once, position kept if the hold completed."""
        g = self.g
        g.realtime(b"!")
        held = False
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            try:
                st = g.query_status(0.5)
                if st.state == "Hold" and st.sub == "0" or st.state == "Idle":
                    held = True
                    break
            except ControllerError:
                pass
        g.realtime(b"\x18")
        time.sleep(0.4)
        g.reset_seen = False
        g.pump()
        g.pending.clear()
        g.pending_bytes = 0
        g.errors.clear()
        try:
            g.command("M5 S0")
        except ControllerError:
            pass
        st = g.query_status()
        return held and st.state != "Alarm", st

    # ---------------------------------------------------------------- main
    def run(self) -> str:
        bodies = None
        try:
            self.acquire_lock()
            keep_awake(True)
            bodies = self.load_passes()
            self.connect()
            n = len(bodies)
            start_index = int(self.spec.get("start_index", 0))
            lead = list(self.spec.get("lead") or [])
            self.active_mark = time.monotonic()
            for pi in range(self.pi, n):
                self.pi = pi
                body = bodies[pi]
                p = self.job["passes"][pi]
                if pi == int(self.spec.get("start_pass", 0)):
                    items = [(c, None) for c in lead] + [(body[k], k) for k in range(start_index, len(body))]
                    self.state["sent"] = start_index
                else:
                    items = [(c, k) for k, c in enumerate(body)]
                    self.state["sent"] = 0
                self.last_written = (start_index - 1) if pi == int(self.spec.get("start_pass", 0)) else -1
                self.state.update(pass_index=pi, pass_key=p["key"], pass_title=p["title"])
                self.phase("running", f"{p['title']} ({pi + 1} of {n}) running.")
                res = self.stream(items, body)
                if res == "estop":
                    return self.finish_estop(bodies)
                if res.startswith("stop:"):
                    idx = int(res.split(":")[1])
                    self.wait_idle(120)
                    self.g.command("M5 S0")
                    point = self.last_xy or self.park_xy
                    self.state["resume"] = recovery.resume_spec(body, pi, idx, point, self.hop)
                    self.state["resume"]["kept_position"] = True
                    self.phase("stopped", f"Stopped after a row in {p['title']}. Position kept, laser off. "
                                          "Resume will continue with the next row.")
                    return "stopped"
                self.wait_idle(300)
                self.g.command("M5 S0")
                self.state["completed"].append(pi)
                self.save(force=True)
                if pi < n - 1 and self.spec.get("pause_between", True):
                    self.park()
                    if not self.wait_photo(p["title"]):
                        self.state["resume"] = recovery.resume_spec(bodies[pi + 1], pi + 1, 0, self.park_xy, self.hop)
                        self.state["resume"]["kept_position"] = True
                        self.phase("stopped", "Stopped between passes. Position kept, laser off.")
                        return "stopped"
            self.park(final=True)
            self.state["resume"] = None
            self.phase("complete", "Finished! Laser off, head parked at the start point.")
            return "complete"
        except LinkError as e:
            return self.dropout(str(e), bodies)
        except ControllerError as e:
            return self.fault(str(e), bodies)
        except Exception as e:  # pragma: no cover - unexpected bug: stop the laser and record
            self.log(traceback.format_exc())
            return self.fault(f"Unexpected error: {e}", bodies)
        finally:
            try:
                self.memory.disconnect()
            except OSError as e:
                self.log(f"Position record could not be saved: {e}")
            try:
                if self.g:
                    self.g.close()
            except Exception:
                pass
            self.release_lock()
            keep_awake(False)
            self.active_mark = None
            try:
                self.save(force=True)
            except OSError as e:
                self.log(f"Final progress record could not be saved: {e}")

    def finish_estop(self, bodies):
        ok, st = self.estop()
        body = bodies[self.pi]
        point = tuple(st.wpos[:2]) if st.wpos else self.last_xy
        loc = recovery.locate(body, point, max(0, self.last_written - 400), self.last_written + 1) if point else None
        if ok and loc:
            idx, partial = loc
            self.state["resume"] = recovery.resume_spec(body, self.pi, idx, point, self.hop, partial)
            self.state["resume"]["kept_position"] = True
            self.phase("stopped", "Emergency stop: laser off, position kept. Resume continues exactly from here.")
        else:
            self.state["resume"] = self.dropout_resume(bodies, point_hint=point)
            self.phase("fault", "Emergency stop: laser off. Position may have shifted - use Resume after a stop "
                                "to check it with the dot first.")
        return self.state["phase"]

    def dropout_resume(self, bodies, point_hint=None):
        if bodies is None:
            return None
        pi = self.pi
        if pi in self.state["completed"]:
            if pi + 1 >= len(bodies):
                return None
            point = self.last_xy or self.park_xy
            return recovery.resume_spec(bodies[pi + 1], pi + 1, 0, point, self.hop)
        body = bodies[pi]
        idx = self.last_written + 1
        point = self.last_xy or point_hint
        if point is None:
            return None
        return recovery.resume_spec(body, pi, max(0, idx), point, self.hop)

    def dropout(self, msg, bodies):
        self.state["resume"] = self.dropout_resume(bodies) if self.state["phase"] not in ("connecting", "starting") \
            else None
        if self.state["resume"]:
            self.state["resume"]["kept_position"] = False
            self.state["resume"]["position_basis"] = "last_sent_endpoint_not_confirmed"
            p = self.state["resume"]["expected_start"]
            self.phase("dropout", f"USB connection lost: {msg} Last sent endpoint: X{p[0]:.2f} Y{p[1]:.2f}. "
                                  "This is a candidate stop, not confirmed motion. Reported position, idle checkpoint "
                                  "and accepted/sent command indices are saved. Use 'Resume after dropout' to reconcile.")
        else:
            self.phase("fault", f"Couldn't start: {msg}")
        return "dropout"

    def fault(self, msg, bodies):
        if self.g is not None and self.state["phase"] not in ("connecting", "starting"):
            try:
                ok, st = self.estop()
                self.state["resume"] = self.dropout_resume(bodies, point_hint=tuple(st.wpos[:2]) if st.wpos else None)
                if self.state["resume"]:
                    self.state["resume"]["kept_position"] = False
            except Exception as e:  # link gone as well
                self.log(f"stop after fault failed: {e}")
                self.state["resume"] = self.dropout_resume(bodies)
        elif self.g is not None:
            try:
                self.g.command("M5 S0")
            except Exception:
                pass
        self.phase("fault", f"Stopped: {msg}")
        return "fault"

    # ---------------------------------------------------------------- one sender at a time
    def acquire_lock(self):
        other = jobs.active_runner()
        if other and other.get("pid") != os.getpid():
            raise ControllerError(f"Another job is already running ({other.get('job')}).")
        jobs.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        jobs.write_json(jobs.LOCK_FILE, dict(pid=os.getpid(), job=str(self.folder),
                                             since=dt.datetime.now().isoformat(timespec="seconds")))

    def release_lock(self):
        info = jobs.read_json(jobs.LOCK_FILE)
        if info and info.get("pid") == os.getpid():
            try:
                jobs.LOCK_FILE.unlink()
            except OSError:
                pass


def keep_awake(on: bool):
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))
        except Exception:
            pass


def main(argv=None):
    argv = argv or sys.argv[1:]
    folder = Path(argv[0])
    Runner(folder).run()


if __name__ == "__main__":
    main()
