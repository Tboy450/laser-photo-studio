"""Background thread that owns the USB port while the app is connected (setup work: jog, origin, dot, perimeter).
A running job is owned by the detached runner instead; the app disconnects before starting one."""
from __future__ import annotations

import queue
import threading
import time

from . import machine, position_memory
from .machine import ControllerError, Grbl, LinkError, SerialWire

DOT_LIMIT_S = 60.0


class MachineWorker(threading.Thread):
    def __init__(self, events: queue.Queue, port="COM4", baud=115200, demo=False, demo_state=None, context=None):
        super().__init__(daemon=True)
        self.events = events
        self.port, self.baud, self.demo, self.demo_state = port, baud, demo, demo_state or {}
        self.tasks: queue.Queue = queue.Queue()
        self.quit = threading.Event()
        self.cancel = threading.Event()
        self.dot_until = 0.0
        self.g: Grbl | None = None
        self.ctrl = None
        self.busy = False
        self.memory = position_memory.PositionMemory(position_memory.memory_path(port, demo))
        self.context = context or {}

    # ---------------------------------------------------------------- api (called from the UI thread)
    def submit(self, name, fn, *args, **kw):
        self.cancel.clear()
        self.tasks.put((name, fn, args, kw))

    def dot(self, on: bool):
        self.dot_until = time.monotonic() + DOT_LIMIT_S if on else 0.0
        self.emit("dot", on)

    def stop(self):
        self.dot_until = 0.0
        self.quit.set()
        self.cancel.set()

    def remember_setup(self, g, context):
        self.context = context
        self.memory.context(context)

    def trace_progress(self, i, n, name, phase):
        if self.memory.enabled:
            self.memory.data["path_progress"] = dict(sent_moves=i, total=n, shape=name, phase=phase)
            self.memory.save()
        self.emit("perim", i, n, name, phase)

    def restore_position(self, g, point, observed, context, keep_coordinates=False):
        self.context = context
        st = g.query_status()
        machine.require_idle_off(st)
        if g.reset_seen or not machine.same_position(st, observed):
            raise ControllerError("Controller position changed while restoring. Reconnect and check the saved setup again.")
        if keep_coordinates:
            return st
        return machine.set_origin_here(g, *point, observed=observed)

    def emit(self, *ev):
        self.events.put(ev)

    # ---------------------------------------------------------------- thread
    def run(self):
        try:
            if self.demo:
                from .fakegrbl import FakeController, FakeWire
                self.ctrl = FakeController(speedup=25.0)
                self.ctrl.take_output()
                for k in ("phys", "morg", "wco"):
                    if k in self.demo_state:
                        setattr(self.ctrl, k, list(self.demo_state[k]))
                wire = FakeWire(self.ctrl)
                settle = 0.05
            else:
                wire = SerialWire(self.port, self.baud)
                settle = 1.0
            self.g = Grbl(wire, observer=self.memory.protocol)
            self.g.open(settle=settle)
            rebooted = self.g.reset_seen
            info = machine.connect_checks(self.g)
            info["rebooted"] = rebooted or self.g.reset_seen
            info["position_memory"] = self.memory.data
            self.g.reset_seen = False
            self.emit("connected", info)
            next_poll = 0.0
            while not self.quit.is_set():
                try:
                    name, fn, args, kw = self.tasks.get_nowait()
                except queue.Empty:
                    name = None
                if name:
                    self._task(name, fn, args, kw)
                    continue
                now = time.monotonic()
                if self.dot_until and now < self.dot_until:
                    self._pulse()
                    continue
                if self.dot_until and now >= self.dot_until:
                    self.dot_until = 0.0
                    self.emit("dot", False)
                if now >= next_poll:
                    st = self.g.query_status()
                    if self.g.reset_seen:
                        self.g.reset_seen = False
                        self.emit("rebooted", "The controller restarted. Its position is no longer known.")
                    elif not self.g.pending:
                        self.memory.settled(st)
                    self.emit("status", st)
                    next_poll = now + 0.3
                self.g.pump()
                time.sleep(0.03)
        except LinkError as e:
            self.emit("link_lost", str(e))
        except Exception as e:
            self.emit("link_lost", f"{e}")
        finally:
            try:
                self.memory.disconnect()
            except OSError as e:
                self.emit("error", f"Position record could not be saved: {e}")
            try:
                if self.g is not None:
                    try:
                        self.g.command("M5 S0", timeout=1.0)
                    except Exception:
                        pass
                    self.g.close()
            except Exception:
                pass
            state = None
            if self.ctrl is not None:
                state = dict(phys=self.ctrl.phys, morg=self.ctrl.morg, wco=self.ctrl.wco)
            self.emit("disconnected", state)

    def _pulse(self):
        try:
            self.busy = True
            st = self.g.query_status()
            if st.state in ("Jog", "Run"):
                time.sleep(0.1)
                return
            machine.pointer_pulse(self.g)
            time.sleep(0.2)
        except ControllerError as e:
            self.dot_until = 0.0
            self.emit("dot", False)
            self.emit("error", f"Dot stopped: {e}")
        finally:
            self.busy = False

    def _task(self, name, fn, args, kw):
        if self.dot_until and name not in ("dot_jog", "dot_follow"):
            self.dot_until = 0.0
            self.emit("dot", False)
        self.busy = True
        self.emit("busy", name, True)
        try:
            if not self.memory.enabled and name in ("jog", "dot_jog", "follow", "dot_follow", "goto", "perimeter"):
                self.memory.invalidate("The app moved the head after reconnect, before the saved reference was restored.")
            if name != "remember_setup":
                self.memory.context(self.context)
                self.memory.begin(name)
            res = fn(self.g, *args, **kw)
            if name in ("origin", "here", "declare", "restore_position", "follow", "dot_follow"):
                if isinstance(res, machine.Status):
                    self.memory.arm(res, self.context)
            elif isinstance(res, machine.Status) and not self.g.reset_seen and not self.g.pending:
                self.memory.settled(res)
            if isinstance(res, machine.Status):
                self.emit("status", res)
            self.emit("done", name, res)
        except LinkError:
            if name in ("origin", "here", "declare", "restore_position", "follow", "dot_follow"):
                self.memory.invalidate("USB disconnected while changing the coordinate reference; completion is unknown.")
            raise
        except ControllerError as e:
            if name in ("origin", "here", "declare", "restore_position", "follow", "dot_follow"):
                self.memory.invalidate("The coordinate-setting operation did not finish successfully.")
            self.emit("failed", name, str(e))
        except Exception as e:  # keep the link alive on bugs; report them
            self.emit("failed", name, f"{type(e).__name__}: {e}")
        finally:
            self.busy = False
            self.emit("busy", name, False)
