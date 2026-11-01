"""Offline replay check of every job before it can be saved or sent (LASER-AUTOMATION-BRIEF.md):
only allowed power and speed values, inside the envelope, and every intended cell burned exactly once."""
from __future__ import annotations

import re

import numpy as np

from .planner import JobPlan, PassPlan

MOVE = re.compile(r"G1 X(-?\d+\.\d{3}) Y(-?\d+\.\d{3}) F(\d+) S(\d+)")
FORBIDDEN_HINT = ("G0", "$", "M3", "G10", "G92", "G28", "G30", "G53", "M2", "M30")


def allowed_values(job: JobPlan, p: PassPlan):
    m = job.material
    s_ok = {0} | {int(v) for v in np.unique(p.cells) if v}
    f_ok = {int(m.row_feed), int(m.hop_feed), int(p.feed)}
    if p.row_feeds is not None:
        f_ok |= {int(v) for v in np.unique(p.row_feeds) if v}
    return s_ok, f_ok


def verify_pass(job: JobPlan, p: PassPlan, cmds=None, travel_margin: float = 30.0) -> dict:
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
                rf = (g.yt - ny) / g.pitch - 0.5
                r = int(round(rf))
                a, b = (min(x, nx) - g.x0) / g.pitch, (max(x, nx) - g.x0) / g.pitch
                ca, cb = int(round(a)), int(round(b))
                if abs(rf - r) > 1e-3 or abs(a - ca) > 1e-3 or abs(b - cb) > 1e-3:
                    bad(f"command {i}: powered move is off the cell grid")
                elif not (0 <= r < H and 0 <= ca <= cb <= W):
                    bad(f"command {i}: powered move outside the artwork")
                else:
                    counts[r, ca:cb] += 1
                    power[r, ca:cb] = s
                if min(x, nx) < ux0 - 1e-6 or max(x, nx) > ux1 + 1e-6 or ny < uy0 - 1e-6 or ny > uy1 + 1e-6:
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
    else:
        probs = [p for r in report["passes"] for p in r["problems"]]
        s = "PROBLEM: " + "; ".join(probs[:4])
    if report.get("notes"):
        s += "\n" + "\n".join(report["notes"])
    return s
