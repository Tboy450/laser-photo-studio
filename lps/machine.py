"""Talking to the controller (MKS DLC32, Grbl 1.1h): serial link, status parsing, safety checks, the 1% positioning
pulse and the perimeter check. Nothing here homes the machine, writes settings or uses G0/M3 for engraving.

Rules carried over from the project (LASER-AUTOMATION-BRIEF.md, apps/positioning-laser):
  * COM4 at 115200, DTR and RTS off (so opening the port doesn't reboot the controller).
  * Never send $H (no homing switches). Never write $ settings. $X only after the operator asks.
  * Expect $30=1000, $31=0, $32=1, $100=$101=100 before any laser output.
  * Positioning dot = S10 (1%) bursts: M3 S10, G4 P0.25, M5 S0 - only while idle and verified off.
"""
from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass

EXPECTED_SETTINGS = {"30": 1000.0, "31": 0.0, "32": 1.0, "100": 100.0, "101": 100.0}
POINTER_S = 10
FORBIDDEN = re.compile(r"^\s*(\$H|\$RST|\$SLP|\$\d+\s*=|\$N\d*\s*=|G28|G30|G53)", re.I)
RESET_TEXT = re.compile(r"^(Grbl \d|ESP-ROM:|rst:|\[MSG:.*[Rr]eset)")


class LinkError(Exception):
    """The USB link failed (unplugged, port vanished, access denied)."""


class ControllerError(Exception):
    """The controller answered with something unsafe or unexpected."""


# ----------------------------------------------------------------------------------------------- wire
class SerialWire:
    def __init__(self, port: str = "COM4", baud: int = 115200):
        self.port, self.baud = port, baud
        self.ser = None

    def open(self):
        try:
            import serial
        except ImportError as e:  # pragma: no cover
            raise LinkError("pyserial is not installed (run: python -m pip install --user pyserial)") from e
        s = serial.Serial()
        s.port, s.baudrate = self.port, self.baud
        s.bytesize, s.parity, s.stopbits = 8, "N", 1
        s.timeout, s.write_timeout = 0, 1.0
        s.xonxoff = s.rtscts = s.dsrdtr = False
        s.dtr = False
        s.rts = False
        try:
            s.open()
        except Exception as e:
            msg = str(e)
            if "Access is denied" in msg or "PermissionError" in msg:
                msg = f"{self.port} is busy - close LaserGRBL / Positioning Laser / other senders first."
            elif "FileNotFoundError" in msg or "could not open port" in msg:
                msg = f"{self.port} not found - is the laser plugged in and switched on?"
            raise LinkError(msg) from e
        self.ser = s

    def write(self, data: bytes):
        try:
            self.ser.write(data)
        except Exception as e:
            raise LinkError(f"USB write failed: {e}") from e

    def read(self) -> str:
        try:
            n = self.ser.in_waiting
            return self.ser.read(n).decode("ascii", "replace") if n else ""
        except Exception as e:
            raise LinkError(f"USB read failed: {e}") from e

    def close(self):
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass


def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [(p.device, p.description) for p in lp.comports()]
    except Exception:
        return []


# ----------------------------------------------------------------------------------------------- status
@dataclass
class Status:
    state: str
    sub: str
    mpos: tuple | None
    wpos: tuple | None
    wco: tuple | None
    feed: float
    spindle: float
    ov: tuple | None
    raw: str
    at: float

    @property
    def laser_on(self) -> bool:
        return self.spindle > 0

    @property
    def idle_off(self) -> bool:
        return self.state == "Idle" and self.feed == 0 and self.spindle == 0


def _xyz(v: str):
    try:
        return tuple(float(x) for x in v.split(","))
    except ValueError:
        return None


def parse_status(line: str, last_wco=None) -> Status | None:
    line = line.strip()
    if not (line.startswith("<") and line.endswith(">")):
        return None
    parts = line[1:-1].split("|")
    st, _, sub = parts[0].partition(":")
    mpos = wpos = wco = ov = None
    feed = spindle = 0.0
    for f in parts[1:]:
        k, _, v = f.partition(":")
        if k == "MPos":
            mpos = _xyz(v)
        elif k == "WPos":
            wpos = _xyz(v)
        elif k == "WCO":
            wco = _xyz(v)
        elif k == "FS":
            fs = _xyz(v) or (0.0, 0.0)
            feed, spindle = fs[0], fs[1] if len(fs) > 1 else 0.0
        elif k == "F":
            feed = float(v) if v else 0.0
        elif k == "Ov":
            o = _xyz(v)
            ov = tuple(int(x) for x in o) if o else None
    wco = wco or last_wco
    if wpos is None and mpos is not None and wco is not None:
        wpos = tuple(round(a - b, 3) for a, b in zip(mpos, wco))
    if mpos is None and wpos is not None and wco is not None:
        mpos = tuple(round(a + b, 3) for a, b in zip(wpos, wco))
    return Status(st, sub, mpos, wpos, wco, feed, spindle, ov, line, time.monotonic())


def check_settings(settings: dict, expected=None) -> list:
    problems = []
    for k, want in (expected or EXPECTED_SETTINGS).items():
        got = settings.get(k)
        if got is None:
            problems.append(f"${k} missing (expected {want:g})")
        elif abs(got - want) > 1e-6:
            problems.append(f"${k}={got:g} (expected {want:g})")
    return problems


# ----------------------------------------------------------------------------------------------- protocol
class Grbl:
    """Synchronous Grbl 1.1 protocol helper (one owner thread)."""

    def __init__(self, wire, log=None, rx_bytes: int = 120, max_pending: int = 8):
        self.wire = wire
        self.log = log or (lambda s: None)
        self.rx_bytes, self.max_pending = rx_bytes, max_pending
        self.buf = ""
        self.pending = deque()
        self.pending_bytes = 0
        self.acked = 0
        self.errors = []
        self.alarm = None
        self.reset_seen = False
        self.status: Status | None = None
        self.status_serial = 0
        self.wco = None
        self.last_ack_at = time.monotonic()
        self.capture = None
        self.messages = deque(maxlen=300)

    # -- low level
    def open(self, settle: float = 1.0) -> str:
        self.wire.open()
        time.sleep(settle)
        boot = self.wire.read()
        for line in boot.splitlines():
            self._line(line.strip())
        return boot

    def close(self):
        self.wire.close()

    def realtime(self, b: bytes):
        self.wire.write(b)

    def send(self, line: str):
        if FORBIDDEN.match(line):
            raise ControllerError(f"refused to send {line!r} (homing / settings / machine moves are never sent)")
        data = (line + "\n").encode("ascii")
        self.wire.write(data)
        self.pending.append(len(data))
        self.pending_bytes += len(data)

    def can_send(self, line: str) -> bool:
        return len(self.pending) < self.max_pending and self.pending_bytes + len(line) + 1 <= self.rx_bytes

    def pump(self):
        text = self.wire.read()
        if not text:
            return
        self.buf += text
        while True:
            i = self.buf.find("\n")
            if i < 0:
                break
            line = self.buf[:i].strip()
            self.buf = self.buf[i + 1:]
            if line:
                self._line(line)

    def _line(self, line: str):
        if not line:
            return
        if line == "ok" or line.startswith("error:"):
            if self.pending:
                self.pending_bytes -= self.pending.popleft()
            self.acked += 1
            self.last_ack_at = time.monotonic()
            if line.startswith("error:"):
                self.errors.append(line)
                self.log(f"controller: {line}")
            if self.capture is not None:
                self.capture.append(line)
            return
        if line.startswith("<"):
            st = parse_status(line, self.wco)
            if st:
                if st.wco:
                    self.wco = st.wco
                self.status = st
                self.status_serial += 1
            return
        if line.startswith("ALARM:"):
            self.alarm = line
        if RESET_TEXT.match(line):
            self.reset_seen = True
        self.messages.append(line)
        self.log(f"controller: {line}")
        if self.capture is not None:
            self.capture.append(line)

    # -- request/response helpers (only when nothing else is streaming)
    def command(self, line: str, timeout: float = 4.0) -> list:
        self.capture = []
        self.send(line)
        end = time.monotonic() + timeout
        try:
            while time.monotonic() < end:
                self.pump()
                if self.capture and self.capture[-1] in ("ok",) or (self.capture and self.capture[-1].startswith("error:")):
                    out = list(self.capture)
                    if out[-1].startswith("error:"):
                        raise ControllerError(f"{line!r} rejected: {out[-1]}")
                    return out
                time.sleep(0.004)
        finally:
            self.capture = None
        raise ControllerError(f"no answer to {line!r}")

    def exchange(self, lines, timeout: float = 4.0) -> list:
        """Send several lines in ONE write and wait for all their acknowledgements. Used for the 1% burst so the
        controller already holds its own OFF command before the laser turns on."""
        for line in lines:
            if FORBIDDEN.match(line):
                raise ControllerError(f"refused to send {line!r}")
        data = "".join(line + "\n" for line in lines).encode("ascii")
        if len(data) > self.rx_bytes:
            raise ControllerError("burst too long for one write")
        self.capture = []
        self.wire.write(data)
        for line in lines:
            self.pending.append(len(line) + 1)
            self.pending_bytes += len(line) + 1
        end = time.monotonic() + timeout
        try:
            while time.monotonic() < end:
                self.pump()
                acks = [x for x in self.capture if x == "ok" or x.startswith("error:")]
                if any(x.startswith("error:") for x in acks):
                    raise ControllerError(f"burst rejected: {acks}")
                if len(acks) >= len(lines):
                    return list(self.capture)
                time.sleep(0.004)
        finally:
            self.capture = None
        raise ControllerError("burst not acknowledged")

    def query_status(self, timeout: float = 2.0) -> Status:
        serial = self.status_serial
        self.realtime(b"?")
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump()
            if self.status_serial > serial:
                return self.status
            time.sleep(0.004)
        raise ControllerError("controller did not report its status")

    def settings(self) -> dict:
        out = {}
        for line in self.command("$$", timeout=5.0):
            m = re.match(r"^\$(\d+)=([-\d.]+)", line)
            if m:
                out[m[1]] = float(m[2])
        return out

    def modal(self) -> str:
        for line in self.command("$G"):
            if line.startswith("[GC:"):
                return line
        raise ControllerError("controller did not report its modes ($G)")

    def wait_idle(self, timeout: float = 120.0, poll: float = 0.15, cancel=None) -> Status:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cancel is not None and cancel.is_set():
                raise ControllerError("cancelled")
            st = self.query_status()
            if st.state in ("Alarm", "Door"):
                raise ControllerError(f"controller state {st.state}")
            if st.state == "Idle" and not self.pending:
                return st
            time.sleep(poll)
        raise ControllerError("machine did not come to rest in time")


def modal_has(modal: str, word: str) -> bool:
    return re.search(r"[: ]" + re.escape(word) + r"(?:\.0+)?(?= |\])", modal) is not None


def require_off(g: Grbl, power: int = 0):
    md = g.modal()
    if not (modal_has(md, "M5") and modal_has(md, f"S{power}")):
        raise ControllerError(f"laser-off state not confirmed ({md})")
    return md


def require_idle_off(st: Status):
    if st.state != "Idle":
        raise ControllerError(f"machine is {st.state}, not Idle")
    if st.feed != 0 or st.spindle != 0:
        raise ControllerError("machine must report zero feed and zero laser output")
    if st.ov and len(st.ov) >= 3 and st.ov[2] != 100:
        raise ControllerError("laser power override is not 100%")


# ----------------------------------------------------------------------------------------------- machine ops
def connect_checks(g: Grbl) -> dict:
    """After opening: report state, settings and modes. Sends only laser-off and read-only queries."""
    st = g.query_status()
    info = dict(state=st.state, wpos=st.wpos, mpos=st.mpos, reset_seen=g.reset_seen, alarm=st.state == "Alarm")
    if st.state == "Alarm":
        info["settings_problems"] = []
        info["note"] = "Controller is locked (alarm). Unlock with $X - it does not move the machine. Never home."
        return info
    g.command("M5 S0")
    sets = g.settings()
    info["settings"] = sets
    info["settings_problems"] = check_settings(sets)
    info["modal"] = g.modal()
    info["status"] = g.query_status()
    return info


def pointer_pulse(g: Grbl, s: int = POINTER_S, dwell: float = 0.25):
    """One 1% burst while standing still, verified off before and after (as Positioning Laser.exe)."""
    g.realtime(b"\x99")
    require_idle_off(g.query_status())
    g.command(f"G1 F3000 M5 S{s}")
    md = g.modal()
    if not (modal_has(md, "M5") and modal_has(md, f"S{s}")):
        raise ControllerError("pointer power not confirmed before the burst")
    g.exchange([f"M3 S{s}", f"G4 P{dwell:g}", "M5 S0"], timeout=4.0 + dwell)
    require_off(g, 0)
    require_idle_off(g.query_status())


def set_origin_here(g: Grbl, x: float = 0.0, y: float = 0.0) -> Status:
    """Make the head's current spot work X,Y (G54 work offset, as in the project: G10 L20 P1)."""
    require_idle_off(g.query_status())
    g.command(f"G10 L20 P1 X{x:.3f} Y{y:.3f}")
    st = g.query_status()
    if not st.wpos or abs(st.wpos[0] - x) > 0.011 or abs(st.wpos[1] - y) > 0.011:
        raise ControllerError(f"origin not confirmed (reports {st.wpos})")
    return st


def jog(g: Grbl, dx: float, dy: float, feed: int = 1000):
    st = g.query_status()
    if st.state not in ("Idle", "Jog"):
        raise ControllerError(f"can't jog while {st.state}")
    g.command(f"$J=G91 G21 X{dx:.3f} Y{dy:.3f} F{int(feed)}")


def jog_keep_position(g: Grbl, dx: float, dy: float, feed: int = 1000) -> Status:
    """Jog the head, then give it back the work X,Y it had: the job (the picture) moves with the head on the real
    piece. Laser off; same G10 L20 P1 as setting the start point."""
    st = g.query_status()
    if st.state != "Idle" or not st.wpos:
        raise ControllerError(f"wait until the head has stopped (machine is {st.state})")
    x, y = st.wpos[0], st.wpos[1]
    jog(g, dx, dy, feed)
    g.wait_idle()
    return set_origin_here(g, x, y)


def move_off(g: Grbl, x: float, y: float, feed: int = 1500, cancel=None) -> Status:
    """Laser-off move to work X,Y and wait until it arrives."""
    g.command("M5 S0")
    g.command(f"G1 X{x:.3f} Y{y:.3f} F{int(feed)} S0")
    st = g.wait_idle(cancel=cancel)
    return st


def perimeter_check(g: Grbl, points, pulses: int = 3, feed: int = 1500, cancel: threading.Event | None = None,
                    progress=None, return_to=(0.0, 0.0)):
    """Visit each corner with the laser off, then flash the 1% dot there so you can see the job's edges.
    Returns to the origin at the end so a job can start from work 0,0."""
    cancel = cancel or threading.Event()
    st = g.query_status()
    if st.state != "Idle":
        raise ControllerError(f"machine is {st.state}, not Idle")
    md = g.modal()
    motion = "G1" if modal_has(md, "G1") else "G0"
    m = re.search(r" F(\d+(?:\.\d+)?)", md)
    old_feed = m[1] if m else "1000"
    g.command("G21 G90 G94 G54 M5 S0")
    try:
        for i, (x, y, name) in enumerate(points):
            if cancel.is_set():
                break
            if progress:
                progress(i, len(points), name, "moving")
            move_off(g, x, y, feed, cancel)
            if progress:
                progress(i, len(points), name, "dot")
            for _ in range(max(1, pulses)):
                if cancel.is_set():
                    break
                pointer_pulse(g)
                time.sleep(0.15)
    finally:
        g.command("M5 S0")
        if return_to is not None:
            move_off(g, return_to[0], return_to[1], feed)
        require_off(g, 0)
        g.command(f"{motion} F{old_feed} M5 S0")
        if progress:
            progress(len(points), len(points), "origin", "done")
