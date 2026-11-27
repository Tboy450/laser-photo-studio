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
    best_distance = tol * tol
    for k in range(lo, hi):
        m = MOVE.fullmatch(body[k])
        if not m:
            continue
        e = (float(m[1]), float(m[2]))
        endpoint_distance = (e[0] - point[0]) ** 2 + (e[1] - point[1]) ** 2
        if endpoint_distance <= best_distance:
            best, best_distance = (k + 1, None), endpoint_distance
        if prev is not None:
            distance = _segment_distance_squared(point, prev, e)
            # A point on the unfinished stroke is a better match than a nearby endpoint.
            if distance is not None and distance < endpoint_distance and distance <= best_distance:
                best = (k, body[k] if int(m[4]) > 0 else None)
                best_distance = distance
        prev = e
    return best


def _segment_distance_squared(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return None
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2
    if t < -1e-9 or t > 1 + 1e-9:
        return None
    qx, qy = ax + t * dx, ay + t * dy
    return (p[0] - qx) ** 2 + (p[1] - qy) ** 2


def held_resume_lead(lead, expected, reported):
    """Avoid moving a physically held head to its rounded status coordinates."""
    if (expected and reported and tuple(expected[:2]) == tuple(reported[:2])
            and len(lead) >= 2 and lead[0] == "M5 S0"):
        move = MOVE.fullmatch(lead[1])
        if move and int(move[4]) == 0 and (float(move[1]), float(move[2])) == tuple(expected[:2]):
            return [lead[0], *lead[2:]]
    return lead


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
