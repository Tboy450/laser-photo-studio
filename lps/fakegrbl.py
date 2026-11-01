"""Simulated Grbl 1.1h laser controller for tests and the app's demo mode (no hardware is touched).

It keeps the head's true position on the bed separately from what the controller reports, so tests can check that
a resume after a USB dropout + reboot lines up physically. Every powered move is logged in bed coordinates.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import deque

from .machine import LinkError

WORD = re.compile(r"([A-Z])([-+]?\d*\.?\d+)")


class FakeController:
    RX = 128
    PLANNER = 15

    def __init__(self, speedup: float = 400.0, alarm_on_boot: bool = False, report: str = "WPos", settings=None):
        self.speedup = speedup
        self.alarm_on_boot = alarm_on_boot
        self.report = report
        self.settings = {0: 10, 1: 25, 10: 0 if report == "WPos" else 1, 22: 1, 30: 1000, 31: 0, 32: 1,
                         100: 100.0, 101: 100.0, 110: 6000.0, 111: 6000.0, 120: 500.0, 121: 500.0}
        if settings:
            self.settings.update(settings)
        self.phys = [0.0, 0.0]
        self.morg = [0.0, 0.0]
        self.wco = [0.0, 0.0]
        self.lock = threading.RLock()
        self.burns = []
        self.pulses = []
        self.received = []
        self.forbidden = []
        self.overflow = False
        self.powered = True
        self._boot(first=True)

    # ------------------------------------------------------------------ lifecycle
    def _boot(self, first=False):
        self.rx = bytearray()
        if first:
            self.out = deque()
        self.planner = deque()
        self.cur = None
        self.hold = False
        self.alarm_lock = self.alarm_on_boot
        self.modal = dict(motion="G0", F=0.0, S=0, spindle="M5", dist="G90")
        self.last = time.monotonic()
        self.out.append("\r\nGrbl 1.1h ['$' for help]\r\n")
        if self.alarm_lock:
            self.out.append("[MSG:'$H'|'$X' to unlock]\r\n")

    def reboot(self):
        """Power/USB reset: motion stops where it is and the machine position restarts at 0 there."""
        with self.lock:
            self._interrupt()
            self.morg = list(self.phys)
            self._boot()

    def _interrupt(self):
        if self.cur is not None:
            self._finish_block(self.cur, partial=True)
        self.cur = None
        self.planner.clear()

    # ------------------------------------------------------------------ io
    def feed_bytes(self, data: bytes):
        with self.lock:
            self.tick()
            for b in data:
                ch = bytes([b])
                if ch == b"?":
                    self.out.append(self._status() + "\r\n")
                elif ch == b"!":
                    if self.cur is not None or self.planner:
                        self.hold = True
                elif ch == b"~":
                    self.hold = False
                elif b == 0x18:
                    self._soft_reset()
                elif b in (0x85, 0x99, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x9A, 0x9B, 0x9C):
                    if b == 0x85:
                        self._jog_cancel()
                else:
                    self.rx.append(b)
            if len(self.rx) > self.RX:
                self.overflow = True
            self._parse_lines()

    def take_output(self) -> str:
        with self.lock:
            self.tick()
            self._parse_lines()
            s = "".join(self.out)
            self.out.clear()
            return s

    # ------------------------------------------------------------------ simulation
    def tick(self):
        now = time.monotonic()
        dt = (now - self.last) * self.speedup
        self.last = now
        self._advance(dt)

    def run_until_idle(self, limit: float = 1e9):
        """Finish everything already received (tests: what the controller does after USB is lost)."""
        with self.lock:
            self.hold = False
            while (self.cur is not None or self.planner or b"\n" in self.rx) and limit > 0:
                self._advance(1e6)
                self._parse_lines()
                limit -= 1

    def _advance(self, dt: float):
        while dt > 0 and not self.hold:
            if self.cur is None:
                if not self.planner:
                    return
                self.cur = self.planner.popleft()
                self.cur["start"] = list(self.phys)
                self.cur["t"] = 0.0
            blk = self.cur
            step = min(dt, blk["dur"] - blk["t"])
            blk["t"] += step
            dt -= step
            if blk["kind"] in ("move", "jog"):
                f = blk["t"] / blk["dur"] if blk["dur"] > 0 else 1.0
                self.phys = [blk["start"][i] + (blk["end"][i] - blk["start"][i]) * f for i in range(2)]
            if blk["t"] >= blk["dur"] - 1e-12:
                self._finish_block(blk)
                self.cur = None
            self._parse_lines()

    def _finish_block(self, blk, partial=False):
        if blk["kind"] == "move" and blk["spindle"] in ("M3", "M4") and blk["S"] > 0 and blk["motion"] == "G1":
            self.burns.append((blk["start"][0], blk["start"][1], self.phys[0], self.phys[1], blk["S"],
                               blk["F"], blk["spindle"], partial))
        if blk["kind"] == "dwell" and blk["spindle"] == "M3" and blk["S"] > 0:
            self.pulses.append((self.phys[0], self.phys[1], blk["S"], blk["t"]))
        if blk.get("ok_when_done") and not partial:
            self.out.append("ok\r\n")

    def _soft_reset(self):
        moving = self.cur is not None and not self.hold
        self._interrupt()
        self._boot()
        if moving:
            self.alarm_lock = True
            self.out.append("ALARM:3\r\n")

    def _jog_cancel(self):
        if self.cur is not None and self.cur["kind"] == "jog":
            self.cur = None
        self.planner = deque(b for b in self.planner if b["kind"] != "jog")

    # ------------------------------------------------------------------ reporting
    def _mpos(self):
        return [self.phys[i] - self.morg[i] for i in range(2)]

    def _wpos(self):
        m = self._mpos()
        return [m[i] - self.wco[i] for i in range(2)]

    def state_name(self):
        if self.hold:
            return "Hold:0"
        if self.cur is not None or self.planner:
            return "Jog" if (self.cur or self.planner[0])["kind"] == "jog" else "Run"
        return "Alarm" if self.alarm_lock else "Idle"

    def _status(self):
        st = self.state_name()
        if self.cur is not None and self.cur["kind"] in ("move", "jog") and not self.hold:
            feed = self.cur["F"]
            sp = self.cur["S"] if self.cur["spindle"] in ("M3", "M4") else 0
        elif self.cur is not None and self.cur["kind"] == "dwell":
            feed, sp = 0, self.cur["S"] if self.cur["spindle"] == "M3" else 0
        else:
            feed = 0
            sp = self.modal["S"] if self.modal["spindle"] != "M5" else 0
        if self.report == "WPos":
            w = self._wpos()
            pos = f"WPos:{w[0]:.3f},{w[1]:.3f},0.000"
            wco = ""
        else:
            m = self._mpos()
            pos = f"MPos:{m[0]:.3f},{m[1]:.3f},0.000"
            wco = f"|WCO:{self.wco[0]:.3f},{self.wco[1]:.3f},0.000"
        return f"<{st}|{pos}|FS:{feed:g},{sp:g}{wco}|Ov:100,100,100>"

    # ------------------------------------------------------------------ parser
    def _parse_lines(self):
        while True:
            if self.cur is not None and self.cur["kind"] == "dwell":
                return  # Grbl's main loop is busy inside G4 until the dwell ends
            i = self.rx.find(b"\n")
            if i < 0:
                return
            line = self.rx[:i].decode("ascii", "replace").strip().upper().replace(" ", "")
            if self._is_motion(line) and len(self.planner) >= self.PLANNER:
                return
            if re.match(r"^G0?4(?!\d)", line) and (self.cur is not None or self.planner):
                return  # G4 first waits for all motion to finish (buffer sync)
            del self.rx[:i + 1]
            self.received.append(line)
            reply = self._execute(line)
            if reply is not None:
                self.out.append(reply + "\r\n")

    @staticmethod
    def _is_motion(line):
        return bool(re.search(r"G0?[0-4](?!\d)|X|Y|\$J=", line)) and not line.startswith("$$")

    def _execute(self, line: str) -> str:
        if not line:
            return "ok"
        if line.startswith("$"):
            return self._dollar(line)
        if self.alarm_lock:
            return "error:9"
        words = WORD.findall(line)
        if not words:
            return "error:1"
        g = [float(v) for k, v in words if k == "G"]
        vals = {k: float(v) for k, v in words if k != "G"}
        m = vals.get("M")
        if any(int(x) in (28, 30, 53, 92) for x in g):
            self.forbidden.append(line)
            return "error:20"
        if 10 in [int(x) for x in g]:
            if vals.get("L") == 20 and vals.get("P") in (0, 1):
                mp = self._mpos()
                if "X" in vals:
                    self.wco[0] = mp[0] - vals["X"]
                if "Y" in vals:
                    self.wco[1] = mp[1] - vals["Y"]
                return "ok"
            return "error:20"
        for x in g:
            if int(x) in (0, 1):
                self.modal["motion"] = f"G{int(x)}"
            elif int(x) == 91:
                return "error:20"
        if "F" in vals:
            self.modal["F"] = vals["F"]
        if "S" in vals:
            self.modal["S"] = int(vals["S"])
        if m is not None:
            if int(m) in (3, 4, 5):
                self.modal["spindle"] = f"M{int(m)}"
            elif int(m) in (2, 30, 0, 1):
                self.forbidden.append(line)
        if 4 in [int(x) for x in g]:
            p = vals.get("P", 0.0)
            self.planner.append(dict(kind="dwell", dur=p, spindle=self.modal["spindle"], S=self.modal["S"],
                                     F=0, motion="G4", ok_when_done=True))
            return None
        if "X" in vals or "Y" in vals:
            w = self._wpos()
            tx, ty = vals.get("X", w[0]), vals.get("Y", w[1])
            end = [tx + self.wco[0] + self.morg[0], ty + self.wco[1] + self.morg[1]]
            last = self.planner[-1]["end"] if self.planner and "end" in self.planner[-1] else \
                (self.cur["end"] if self.cur is not None and "end" in self.cur else self.phys)
            dist = math.hypot(end[0] - last[0], end[1] - last[1])
            motion = self.modal["motion"]
            if motion == "G1" and self.modal["F"] <= 0:
                return "error:22"
            feed = self.modal["F"] if motion == "G1" else float(self.settings[110])
            self.planner.append(dict(kind="move", end=end, dur=dist / (feed / 60.0), F=feed, S=self.modal["S"],
                                     spindle=self.modal["spindle"], motion=motion))
        return "ok"

    def _dollar(self, line: str) -> str:
        if line == "$$":
            self.out.extend(f"${k}={v:g}\r\n" if isinstance(v, int) else f"${k}={v:.3f}\r\n"
                            for k, v in sorted(self.settings.items()))
            return "ok"
        if line == "$G":
            md = self.modal
            self.out.append(f"[GC:{md['motion']} G54 G17 G21 G90 G94 {md['spindle']} M9 T0 F{md['F']:g} S{md['S']}]\r\n")
            return "ok"
        if line == "$I":
            self.out.append("[VER:1.1h.20190825:]\r\n[OPT:V,15,128]\r\n")
            return "ok"
        if line == "$X":
            self.alarm_lock = False
            self.out.append("[MSG:Caution: Unlocked]\r\n")
            return "ok"
        if line.startswith("$J="):
            if self.alarm_lock:
                return "error:9"
            vals = {k: float(v) for k, v in WORD.findall(line[3:]) if k in "XYF"}
            rel = "G91" in line
            w = self._wpos()
            tx = w[0] + vals.get("X", 0.0) if rel else vals.get("X", w[0])
            ty = w[1] + vals.get("Y", 0.0) if rel else vals.get("Y", w[1])
            end = [tx + self.wco[0] + self.morg[0], ty + self.wco[1] + self.morg[1]]
            dist = math.hypot(end[0] - self.phys[0], end[1] - self.phys[1])
            f = vals.get("F", 1000.0)
            self.planner.append(dict(kind="jog", end=end, dur=dist / (f / 60.0), F=f, S=0, spindle="M5", motion="G1"))
            return "ok"
        self.forbidden.append(line)
        return "error:3"


class FakeWire:
    """Wire into a FakeController. `fail_after_lines` simulates the USB dropping out on that write."""

    def __init__(self, ctrl: FakeController, fail_after_lines: int | None = None):
        self.ctrl = ctrl
        self.fail_after_lines = fail_after_lines
        self.lines_written = 0
        self.dead = False
        self.opened = False

    def open(self):
        if self.dead:
            raise LinkError("port not found")
        self.opened = True

    def write(self, data: bytes):
        if self.dead:
            raise LinkError("USB write failed: device not functioning")
        n = data.count(b"\n")
        if self.fail_after_lines is not None and self.lines_written + n > self.fail_after_lines:
            self.dead = True
            raise LinkError("USB write failed: access denied")
        self.lines_written += n
        self.ctrl.feed_bytes(data)

    def read(self) -> str:
        if self.dead:
            raise LinkError("USB read failed: device not functioning")
        return self.ctrl.take_output()

    def close(self):
        self.opened = False


def coverage(ctrl: FakeController, geom, bed_from_work=(0.0, 0.0), tol: float = 0.02):
    """Fraction of each cell burned (summed over all logged burns), in the job's work coordinates."""
    import numpy as np
    cov = np.zeros((geom.rows, geom.cols))
    for x0, y0, x1, y1, s, f, mode, partial in ctrl.burns:
        wx0, wx1 = x0 - bed_from_work[0], x1 - bed_from_work[0]
        wy = y0 - bed_from_work[1]
        if abs(y1 - y0) > 1e-6:
            raise AssertionError(f"powered move not horizontal: {(x0, y0, x1, y1)}")
        r = (geom.yt - wy) / geom.pitch - 0.5
        ri = int(round(r))
        if abs(r - ri) > tol / geom.pitch or not 0 <= ri < geom.rows:
            raise AssertionError(f"burn off the row grid at y={wy:.4f}")
        a, b = (min(wx0, wx1) - geom.x0) / geom.pitch, (max(wx0, wx1) - geom.x0) / geom.pitch
        for c in range(max(0, int(math.floor(a))), min(geom.cols, int(math.ceil(b)))):
            cov[ri, c] += max(0.0, min(b, c + 1) - max(a, c))
    return cov
