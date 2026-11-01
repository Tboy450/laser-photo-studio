"""Background thread that owns the USB port while the app is connected (setup work: jog, origin, dot, perimeter).
A running job is owned by the detached runner instead; the app disconnects before starting one."""
from __future__ import annotations

import queue
import threading
import time

from . import machine
from .machine import ControllerError, Grbl, LinkError, SerialWire

DOT_LIMIT_S = 60.0


class MachineWorker(threading.Thread):
    def __init__(self, events: queue.Queue, port="COM4", baud=115200, demo=False, demo_state=None):
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

    # ---------------------------------------------------------------- api (called from the UI thread)
    def submit(self, name, fn, *args, **kw):
        self.cancel.clear()
        self.tasks.put((name, fn, args, kw))

    def dot(self, on: bool):
        self.dot_until = time.monotonic() + DOT_LIMIT_S if on else 0.0
        self.emit("dot", on)

    def stop(self):
        self.dot_until = 0.0
        self.cancel.set()
        self.quit.set()

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
            self.g = Grbl(wire)
            self.g.open(settle=settle)
            rebooted = self.g.reset_seen
            info = machine.connect_checks(self.g)
            info["rebooted"] = rebooted
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
                    self.emit("status", st)
                    if self.g.reset_seen:
                        self.g.reset_seen = False
                        self.emit("rebooted", "The controller restarted. Its position is no longer known.")
                    next_poll = now + 0.3
                self.g.pump()
                time.sleep(0.03)
        except LinkError as e:
            self.emit("link_lost", str(e))
        except Exception as e:
            self.emit("link_lost", f"{e}")
        finally:
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
        if self.dot_until and name not in ("dot_jog",):
            self.dot_until = 0.0
            self.emit("dot", False)
        self.busy = True
        self.emit("busy", name, True)
        try:
            res = fn(self.g, *args, **kw)
            self.emit("done", name, res)
        except LinkError:
            raise
        except ControllerError as e:
            self.emit("failed", name, str(e))
        except Exception as e:  # keep the link alive on bugs; report them
            self.emit("failed", name, f"{type(e).__name__}: {e}")
        finally:
            self.busy = False
            self.emit("busy", name, False)
