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


def armed_at(body: list, index: int) -> bool:
    """Is dynamic laser mode (M4) active just before body[index]?"""
    for k in range(min(index, len(body)) - 1, -1, -1):
        if body[k] == "M4 S0":
            return True
        if body[k] == "M5 S0":
            return False
    return False


def lead_in(body: list, index: int, point, hop_feed: int = 3000) -> list:
    lead = ["M5 S0", f"G1 X{fmt(point[0])} Y{fmt(point[1])} F{int(hop_feed)} S0"]
    if armed_at(body, index):
        lead.append("M4 S0")
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


def resume_spec(body: list, pass_index: int, index: int, point, hop_feed: int = 3000, partial: str | None = None):
    lead = lead_in(body, index, point, hop_feed)
    if partial:
        lead.append(partial)
        index += 1
    return dict(start_pass=pass_index, start_index=index, lead=lead, expected_start=[round(point[0], 3),
                                                                                       round(point[1], 3)])
