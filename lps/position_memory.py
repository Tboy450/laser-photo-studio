"""Local setup journal. Saved coordinates are evidence, never an automatic move.

An idle checkpoint is distinct from a sent endpoint and from sampled telemetry.
The setup worker and detached runner own this journal in turn. Disconnected UI
windows only read it, so a stale window cannot overwrite the active sender.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path

from . import jobs


def memory_path(port="COM4", demo=False):
    name = re.sub(r"[^A-Za-z0-9_-]", "_", port.upper())
    return jobs.SETTINGS_FILE.parent / "Recovery" / f"{'demo-' if demo else ''}{name}.json"


def snapshot(st):
    return dict(wpos=st.wpos, mpos=st.mpos, wco=st.wco, state=st.state,
                feed=st.feed, spindle=st.spindle, recorded_at=time.time())


def matches(st, saved, tolerance=.011):
    """All three coordinate reports must match; WPos alone cannot prove an origin."""
    return bool(st and st.idle_off and saved and all(
        getattr(st, k) is not None and saved.get(k) is not None
        and math.dist(getattr(st, k)[:2], saved[k][:2]) <= tolerance
        for k in ("wpos", "mpos", "wco")))


class PositionMemory:
    def __init__(self, path):
        self.path = Path(path)
        self.data = jobs.read_json(self.path, {}) or {}
        self.enabled = False
        self.next_save = 0.0

    def save(self, force=False):
        if not force and time.monotonic() < self.next_save:
            return
        self.next_save = time.monotonic() + .25
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data.update(version=1, updated=time.time())
        # Unique temporary names also tolerate an old UI and runner shutting down
        # at nearly the same time. Flush before replacement; never truncate the record.
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def arm(self, st, context):
        if self.data:
            history = self.path.parent / "history"
            history.mkdir(parents=True, exist_ok=True)
            jobs.write_json(history / f"{self.path.stem}-{time.time_ns()}.json", self.data)
        self.enabled = True
        self.data = dict(version=1, context=copy.deepcopy(context), last_reported=snapshot(st),
                         last_idle=snapshot(st), in_flight=False, operation=None,
                         last_sent=None, attempted=None, disconnected=False, reset=False)
        self.save(True)

    def context(self, context):
        if self.enabled:
            self.data["context"] = copy.deepcopy(context)
            self.save(True)

    def begin(self, name, detail=None):
        if self.enabled:
            self.data.update(in_flight=True, operation=dict(name=name, detail=detail, started=time.time()))
            self.save(True)  # durable BEFORE any move is written

    def protocol(self, event, value):
        if not self.enabled:
            return
        if event == "attempt":
            self.data["attempted"] = value
            if re.match(r"(?:G[01] |\$J=)", value) and re.search(r"[XY]-?\d", value):
                self.data["attempted_motion"] = value
        elif event == "sent":
            self.data["last_sent"] = value
            self.data["attempted"] = None
            if re.match(r"(?:G[01] |\$J=)", value) and re.search(r"[XY]-?\d", value):
                self.data["last_sent_motion"] = value
                self.data["attempted_motion"] = None
        elif event == "status":
            self.data["last_reported"] = snapshot(value)
            if value.state in ("Run", "Jog") or value.feed > 0:
                self.data["in_flight"] = True
        elif event == "reset":
            self.data["reset"] = True
            self.save(True)
            self.enabled = False  # reboot coordinates must not overwrite old-frame evidence
            return
        self.save()

    def invalidate(self, reason):
        if self.data:
            self.data.update(coordinate_uncertain=reason, in_flight=True)
            self.save(True)
        self.enabled = False

    def settled(self, st):
        if self.enabled and st and st.idle_off:
            if not self.data.get("in_flight") and matches(st, self.data.get("last_idle")):
                return
            self.data.update(last_idle=snapshot(st), last_reported=snapshot(st),
                             in_flight=False, attempted=None)
            self.save(True)

    def disconnect(self):
        if self.enabled:
            self.data["disconnected"] = True
            self.save(True)
        self.enabled = False
