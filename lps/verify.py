"""Offline replay check of every job before it can be saved or sent (LASER-AUTOMATION-BRIEF.md):
only allowed power and speed values, inside the envelope, and every intended cell burned exactly once."""
from __future__ import annotations

import re

import numpy as np

from .planner import JobPlan, PassPlan

MOVE = re.compile(r"G1 X(-?\d+\.\d{3}) Y(-?\d+\.\d{3}) F(\d+) S(\d+)")
FORBIDDEN_HINT = ("G0", "$", "M3", "G10", "G92", "G28", "G30", "G53", "M2", "M30")   # M3: dwell passes only
M3 = re.compile(r"M3 S(\d+)")
DWELL = re.compile(r"G4 P(\d+(?:\.\d+)?)")


def trace_moves(job):
    """XY moves from a verified job, with the original feed and a preview-only mark flag. Burn-in-place passes
    contribute their laser-off travel moves (the spots are standing still, so they add no line)."""
    for p in job.passes:
        for command in p.commands:
            if command in ("M5 S0", "M4 S0") or (p.kind == "dwell" and (M3.fullmatch(command)
                                                                        or DWELL.fullmatch(command))):
                continue
            move = MOVE.fullmatch(command)
            if move is None:
                raise ValueError(f"Unexpected move in checked job: {command!r}")
            yield float(move[1]), float(move[2]), int(move[3]), int(move[4]) > 0
    yield 0.0, 0.0, 3000, False


def allowed_values(job: JobPlan, p: PassPlan):
    m = job.material
    s_ok = {0} | {int(v) for v in np.unique(p.cells) if v}
    f_ok = {int(m.row_feed), int(m.hop_feed), int(p.feed)}
    if p.row_feeds is not None:
        f_ok |= {int(v) for v in np.unique(p.row_feeds) if v}
    return s_ok, f_ok


def verify_dwell(job: JobPlan, p: PassPlan, cmds=None, travel_margin: float = 30.0) -> dict:
    """Burn-in-place pass rules: the laser is off (M5) on every move; each spot is exactly travel, M3 S<n>, one
    G4 P<s>, M5 S0, at a planned spot with its planned power and time; spots inside the usable area; only
    laser-off waits otherwise; starts and ends laser off."""
    from .planner import COOL_MAX_S, DWELL_MAX_S
    cmds = p.commands if cmds is None else cmds
    g = job.geom
    spots = list(p.spots or [])
    problems = []

    def bad(msg):
        if len(problems) < 25:
            problems.append(msg)

    s_ok = {int(sp["s"]) for sp in spots}
    f_ok = {int(p.feed), int(job.material.row_feed)}
    if not cmds or cmds[0] != "M5 S0" or cmds[-1] != "M5 S0":
        bad("pass must start and end with M5 S0 (laser off)")
    px0, py0, px1, py1 = g.piece_rect
    ux0, uy0, ux1, uy1 = g.usable_rect
    want = np.zeros((g.rows, g.cols), np.int16)
    x = y = None
    done = 0
    dwell_s = 0.0
    tx0 = ty0 = float("inf")
    tx1 = ty1 = float("-inf")
    i = 0
    n = len(cmds)
    while i < n:
        c = cmds[i]
        if c == "M5 S0":
            i += 1
            continue
        mo, m3, dw = MOVE.fullmatch(c), M3.fullmatch(c), DWELL.fullmatch(c)
        if mo:
            nx, ny, f, s = float(mo[1]), float(mo[2]), int(mo[3]), int(mo[4])
            if s != 0:
                bad(f"command {i + 1}: a move with the laser on (burn-in-place moves must be S0)")
            if f not in f_ok:
                bad(f"command {i + 1}: speed F{f} not allowed")
            if not (px0 - travel_margin <= nx <= px1 + travel_margin and py0 - travel_margin <= ny <= py1 + travel_margin):
                bad(f"command {i + 1}: move to {nx},{ny} is far outside the piece")
            tx0, tx1, ty0, ty1 = min(tx0, nx), max(tx1, nx), min(ty0, ny), max(ty1, ny)
            x, y = nx, ny
            i += 1
        elif m3:
            s = int(m3[1])
            if i + 2 >= n or not DWELL.fullmatch(cmds[i + 1]) or cmds[i + 2] != "M5 S0":
                bad(f"command {i + 1}: M3 must be followed by exactly one G4 P<seconds> and then M5 S0")
                i += 1
                continue
            sec = float(DWELL.fullmatch(cmds[i + 1])[1])
            if done >= len(spots):
                bad(f"command {i + 1}: more spots burned than planned")
            else:
                sp = spots[done]
                if x is None or abs(x - sp["x"]) > 0.00051 or abs(y - sp["y"]) > 0.00051:
                    bad(f"command {i + 1}: spot {done + 1} burns at {x},{y}, planned {sp['x']},{sp['y']}")
                if s != int(sp["s"]) or abs(sec - float(sp["seconds"])) > 1e-9:
                    bad(f"command {i + 1}: spot {done + 1} is S{s} for {sec:g} s, planned S{sp['s']} for "
                        f"{sp['seconds']:g} s")
            if s not in s_ok or s <= 0:
                bad(f"command {i + 1}: power S{s} not allowed")
            if not 0 < sec <= DWELL_MAX_S:
                bad(f"command {i + 1}: a {sec:g} s burn is over the {DWELL_MAX_S:g} s limit")
            if x is None or not (ux0 - 0.00051 <= x <= ux1 + 0.00051 and uy0 - 0.00051 <= y <= uy1 + 0.00051):
                bad(f"command {i + 1}: spot outside the usable area of the piece")
            else:
                r = int(np.floor((g.yt - y) / g.y_pitch))
                cc = int(np.floor((x - g.x0) / g.x_pitch))
                if not (0 <= r < g.rows and 0 <= cc < g.cols) or (job.allowed is not None and not job.allowed[r, cc]):
                    bad(f"command {i + 1}: spot outside the usable area of the piece")
                elif want[r, cc]:
                    bad(f"command {i + 1}: the same spot is burned twice")
                else:
                    want[r, cc] = s
            done += 1
            dwell_s += sec
            i += 3
        elif dw:
            sec = float(dw[1])
            if i == 0 or cmds[i - 1] != "M5 S0":
                bad(f"command {i + 1}: a wait is only allowed with the laser off (after M5 S0)")
            if not 0 < sec <= COOL_MAX_S:
                bad(f"command {i + 1}: a {sec:g} s wait is over the {COOL_MAX_S:g} s limit")
            i += 1
        else:
            bad(f"command {i + 1}: not allowed in a burn-in-place pass: {c!r}")
            i += 1
    if done != len(spots):
        bad(f"{len(spots)} spots planned, {done} burned")
    if not np.array_equal(want, p.cells):
        bad("the spots don't match the pass's planned dots")
    return dict(ok=not problems, problems=problems, cells=int((p.cells > 0).sum()), segments=done,
                travel=(tx0, ty0, tx1, ty1) if tx0 != float("inf") else None,
                s_values=sorted(s_ok), f_values=sorted(f_ok), spots=done, dwell_s=round(dwell_s, 3))


def verify_pass(job: JobPlan, p: PassPlan, cmds=None, travel_margin: float = 30.0) -> dict:
    if p.kind == "dwell":
        return verify_dwell(job, p, cmds, travel_margin)
    cmds = p.commands if cmds is None else cmds
    g = job.geom
    H, W = g.rows, g.cols
    s_ok, f_ok = allowed_values(job, p)
    problems = []

    def bad(msg):
        if len(problems) < 25:
            problems.append(msg)

    if not cmds:
        return dict(ok=not p.cells.any(), problems=[] if not p.cells.any() else ["no commands"], cells=0,
                    segments=0, travel=None)
    if cmds[0] != "M5 S0" or cmds[-1] != "M5 S0":
        bad("pass must start and end with M5 S0 (laser off)")
    px0, py0, px1, py1 = g.piece_rect
    ux0, uy0, ux1, uy1 = g.usable_rect
    counts = np.zeros((H, W), np.int16)
    power = np.zeros((H, W), np.int16)
    x = y = None
    armed = False
    segs = 0
    tx0 = ty0 = float("inf")
    tx1 = ty1 = float("-inf")
    for i, c in enumerate(cmds, 1):
        if c == "M5 S0":
            armed = False
            continue
        if c == "M4 S0":
            armed = True
            continue
        mo = MOVE.fullmatch(c)
        if not mo:
            bad(f"command {i}: not allowed: {c!r}")
            continue
        nx, ny, f, s = float(mo[1]), float(mo[2]), int(mo[3]), int(mo[4])
        if s not in s_ok:
            bad(f"command {i}: power S{s} not allowed")
        if f not in f_ok:
            bad(f"command {i}: speed F{f} not allowed")
        if not (px0 - travel_margin <= nx <= px1 + travel_margin and py0 - travel_margin <= ny <= py1 + travel_margin):
            bad(f"command {i}: move to {nx},{ny} is far outside the piece")
        tx0, tx1, ty0, ty1 = min(tx0, nx), max(tx1, nx), min(ty0, ny), max(ty1, ny)
        if s > 0:
            segs += 1
            if not armed:
                bad(f"command {i}: power without M4")
            if x is None or abs(ny - y) > 1e-6:
                bad(f"command {i}: powered move is not a horizontal row move")
            else:
                rf = (g.yt - ny) / g.y_pitch - 0.5
                r = int(round(rf))
                a, b = (min(x, nx) - g.x0) / g.x_pitch, (max(x, nx) - g.x0) / g.x_pitch
                ca, cb = int(round(a)), int(round(b))
                # The emitted coordinates have 0.001 mm precision.
                if (abs(rf - r) > 0.00051 / g.y_pitch or abs(a - ca) > 0.00051 / g.x_pitch
                        or abs(b - cb) > 0.00051 / g.x_pitch):
                    bad(f"command {i}: powered move is off the cell grid")
                elif not (0 <= r < H and 0 <= ca <= cb <= W):
                    bad(f"command {i}: powered move outside the artwork")
                else:
                    counts[r, ca:cb] += 1
                    power[r, ca:cb] = s
                if min(x, nx) < ux0 - 0.00051 or max(x, nx) > ux1 + 0.00051 or ny < uy0 - 0.00051 or ny > uy1 + 0.00051:
                    bad(f"command {i}: burn outside the usable area of the piece")
        x, y = nx, ny
    want = p.cells > 0
    dup = int((counts > 1).sum())
    missing = int((want & (counts == 0)).sum())
    extra = int((~want & (counts > 0)).sum())
    wrong = int((want & (counts == 1) & (power != p.cells)).sum())
    if dup:
        bad(f"{dup} cells would be burned more than once")
    if missing:
        bad(f"{missing} cells would be missed")
    if extra:
        bad(f"{extra} cells would be burned that shouldn't be")
    if wrong:
        bad(f"{wrong} cells at the wrong power")
    return dict(ok=not problems, problems=problems, cells=int(want.sum()), segments=segs,
                travel=(tx0, ty0, tx1, ty1) if segs or tx0 != float("inf") else None,
                s_values=sorted(s_ok - {0}), f_values=sorted(f_ok))


def verify_job(job: JobPlan) -> dict:
    results = [verify_pass(job, p) for p in job.passes]
    ok = all(r["ok"] for r in results)
    travel = [r["travel"] for r in results if r.get("travel")]
    tb = None
    if travel:
        tb = (min(t[0] for t in travel), min(t[1] for t in travel), max(t[2] for t in travel), max(t[3] for t in travel))
    px0, py0, px1, py1 = job.geom.piece_rect
    notes = []
    if tb and (tb[0] < px0 - 1e-6 or tb[2] > px1 + 1e-6 or tb[1] < py0 - 1e-6 or tb[3] > py1 + 1e-6):
        notes.append("Laser-off run-ups travel up to "
                     f"{max(px0 - tb[0], tb[2] - px1, py0 - tb[1], tb[3] - py1, 0):.1f} mm past the piece edge "
                     "(no burning there). Make sure the head has room.")
    return dict(ok=ok, passes=results, travel=tb, notes=notes,
                cells=sum(r["cells"] for r in results), segments=sum(r["segments"] for r in results))


def summary_text(report: dict) -> str:
    if report["ok"]:
        s = (f"Checked: {report['cells']:,} dots, each burned exactly once at its planned power; "
             f"only allowed powers/speeds; laser off at every start and end.")
        spots = sum(r.get("spots", 0) for r in report["passes"])
        if spots:
            s += (f" Includes {spots} burn-in-place spot{'s' if spots != 1 else ''} "
                  f"({sum(r.get('dwell_s', 0) for r in report['passes']):g} s laser-on standing still, laser off "
                  "on every move).")
    else:
        probs = [p for r in report["passes"] for p in r["problems"]]
        s = "PROBLEM: " + "; ".join(probs[:4])
    if report.get("notes"):
        s += "\n" + "\n".join(report["notes"])
    return s
