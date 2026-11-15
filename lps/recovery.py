"""Build continuation plans, without claiming a serial acknowledgement proves motion.
  * Never home. After a reboot, reconcile the physical position before declaring coordinates.
  * A last-sent endpoint is a candidate only: a reset or partial write can discard queued motion.
    position_memory keeps reported coordinates and confirmed idle checkpoints separately.
  * Continuing after a command avoids repeats ONLY if completion of that command was established.
"""
from __future__ import annotations

import re

from .planner import fmt

MOVE = re.compile(r"G1 X(-?\d+\.\d+) Y(-?\d+\.\d+) F(\d+) S(\d+)")


def xy(cmd: str):
    m = MOVE.fullmatch(cmd)
    return (float(m[1]), float(m[2])) if m else None


def endpoint_before(body: list, index: int, default=None):
    for k in range(min(index, len(body)) - 1, -1, -1):
        p = xy(body[k])
        if p:
            return p
    return default


def arming_at(body: list, index: int):
    """The laser mode active just before body[index]: "M4 S0", a crawl line's "M3 S<n>", or None (off)."""
    for k in range(min(index, len(body)) - 1, -1, -1):
        if body[k] == "M4 S0" or body[k].startswith("M3 "):
            return body[k]
        if body[k] == "M5 S0":
            return None
    return None


def armed_at(body: list, index: int) -> bool:
    return arming_at(body, index) is not None


def lead_in(body: list, index: int, point, hop_feed: int = 3000) -> list:
    """Laser off, move to the resume point, then re-arm as the body was (after the move, never during it)."""
    lead = ["M5 S0", f"G1 X{fmt(point[0])} Y{fmt(point[1])} F{int(hop_feed)} S0"]
    arm = arming_at(body, index)
    if arm:
        lead.append(arm)
    return lead


def locate(body: list, point, lo: int = 0, hi: int | None = None, tol: float = 0.02):
    """Where along the pass is `point`? Returns (index_to_resume_from, partial_command_or_None).
    If the point is inside a powered move, the partial command finishes that move from the point (e-stop mid-row);
    inside a laser-off move, that move is simply repeated from the point."""
    hi = len(body) if hi is None else min(hi, len(body))
    prev = endpoint_before(body, lo)
    best = None
    for k in range(lo, hi):
        m = MOVE.fullmatch(body[k])
        if not m:
            continue
        e = (float(m[1]), float(m[2]))
        if abs(e[0] - point[0]) <= tol and abs(e[1] - point[1]) <= tol:
            best = (k + 1, None)
        elif prev is not None and _on_segment(point, prev, e, tol):
            best = (k, f"G1 X{fmt(e[0])} Y{fmt(e[1])} F{m[3]} S{m[4]}" if int(m[4]) > 0 else None)
        prev = e
    return best


def _on_segment(p, a, b, tol):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return False
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2
    if t < -1e-9 or t > 1 + 1e-9:
        return False
    qx, qy = ax + t * dx, ay + t * dy
    return (p[0] - qx) ** 2 + (p[1] - qy) ** 2 <= tol * tol


def dwell_resume(body: list, index: int, last_written: int):
    """Burn-in-place passes: never burn a spot twice. If the spot whose M3 was last handed to the controller hadn't
    reached its M5 by `index`, continue after that spot instead (it's left part-burned, never repeated).
    Returns (index, spot_number_skipped_or_None)."""
    k3 = next((k for k in range(min(last_written, len(body) - 1), -1, -1) if body[k].startswith("M3 ")), None)
    if k3 is None:
        return index, None
    m5 = next((k for k in range(k3 + 1, len(body)) if body[k] == "M5 S0"), len(body) - 1)
    if index <= m5:
        return m5 + 1, sum(1 for k in range(k3 + 1) if body[k].startswith("M3 "))
    return index, None


def is_dwell(body: list) -> bool:
    """Any M3 pass: burn-in-place or crawl."""
    return any(c.startswith("M3 ") for c in body)


def pass_kind(body: list) -> str:
    if not is_dwell(body):
        return "rows"
    return "crawl" if any((m := MOVE.fullmatch(c)) and int(m[4]) > 0 for c in body) else "dwell"


def crawl_resume(body: list, last_acked: int) -> int:
    """Crawl lines: continue after the last step whose pause was acknowledged (a G4 is acknowledged when it ends,
    so that step is done). At most the one step in progress is burned again."""
    for k in range(min(last_acked, len(body) - 1), -1, -1):
        c = body[k]
        if c.startswith("G4 P") or c == "M5 S0" or c.startswith("M3 "):
            return k + 1
    return 0


def resume_spec(body: list, pass_index: int, index: int, point, hop_feed: int = 3000, partial: str | None = None):
    lead = lead_in(body, index, point, hop_feed)
    if partial:
        lead.append(partial)
        index += 1
    return dict(start_pass=pass_index, start_index=index, lead=lead, expected_start=[round(point[0], 3),
                                                                                       round(point[1], 3)])
