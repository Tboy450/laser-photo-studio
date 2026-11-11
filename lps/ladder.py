"""Wide-range power x speed ladder on a round piece (a 2 in lid): solid patches packed into a safe circle.

Each speed is its own pass, so a pass burns at one speed and its patches can sit anywhere on the lid. Passes run
fastest first and slowest (hottest) last; 'Pause after each pass' lets the operator stop before the slow rows.
Patches carry no engraved labels (they wouldn't fit): a printable map says which is which, and one small
orientation mark burns at the top."""
from __future__ import annotations

import math
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import imaging
from .planner import JobPlan, PassPlan, Placement, allowed_cells, layout
from .presets import Material, auto_runup

LID_MATERIALS = ["Reflective tin lid", "Black aluminum 1 oz tin", "Other (write it in the job name)"]
PRESETS = {
    "A": dict(powers=[50, 60, 70, 80, 90, 100], speeds=[50, 100, 200, 400, 800, 1600, 3200, 6000]),
    "B": dict(powers=[50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100], speeds=[50, 100, 200, 400, 800, 1600, 3200, 6000]),
}
PATCH_SIZES = (6.0, 5.0, 4.0, 3.0, 2.5, 2.0)     # mm, tried largest first
MARK = 1.2                                       # orientation mark, mm square
STRONGEST_SO_FAR = (100.0, 600.0)                # %, mm/min: strongest lid patch burned before this ladder


def lid_piece(diameter: float = 50.8, safe: float = 45.72) -> dict:
    m = round((diameter - safe) / 2, 3)
    return dict(name=f"Lid {diameter / 25.4:g} in circle (ladder)", shape="circle", w=diameter, h=diameter,
                origin="center", margins=(m, m, m, m), corner=0.0, keepouts=[])


def log_speeds(lo: float, hi: float, n: int) -> list:
    """n speeds from lo to hi, evenly spaced on a log scale, rounded to 2 significant figures."""
    if n < 2:
        return [int(lo)]
    out = []
    for k in range(n):
        v = lo * (hi / lo) ** (k / (n - 1))
        d = 10 ** (len(str(int(v))) - 2)
        out.append(int(round(v / d) * d))
    out[0], out[-1] = int(lo), int(hi)
    return sorted(set(out))


def cells_in_circle(radius: float, patch: float, gap: float) -> list:
    """Patch centres (mm from the centre) whose whole square lies inside the circle, rows top to bottom.
    Tries the lattice on and between the centre lines and keeps whichever fits most."""
    step = patch + gap
    best = []
    for ox in (0.0, step / 2):
        for oy in (0.0, step / 2):
            n = int(radius // step) + 2
            pts = []
            for j in range(n, -n - 1, -1):
                y = oy + j * step
                row = []
                for i in range(-n, n + 1):
                    x = ox + i * step
                    h = patch / 2
                    if all(math.hypot(x + sx * h, y + sy * h) <= radius for sx in (-1, 1) for sy in (-1, 1)):
                        row.append((round(x, 3), round(y, 3)))
                pts += row
            if len(pts) > len(best):
                best = pts
    return best


def lid_material(base: Material, note: str) -> Material:
    """The ladder's own material: the lid it really runs on (not whatever was picked in step 2), with a metal
    preview. Power and speed come from each patch; only row spacing and scan direction come from `base`."""
    black = "black" in note.lower()
    return base.copy(key="lid-ladder-test", name=f"{note or 'Lid'} - ladder test", badge="EXPERIMENTAL",
                     style="threshold", look="blacktin" if black else "tin", negative=False,
                     runup=0.3,       # at 10-50 mm/min the head is at speed at once; fast speeds still get auto_runup
                     summary="Test ladder: every patch has its own power and speed.",
                     notes=["Power and speed are set per patch; see the ladder map in the job folder."])


def patch_key(speed, power) -> str:
    return f"{int(speed)}:{float(power):g}"


def plan(powers, speeds, radius: float = 22.86, gap: float = 1.0, patch: float | None = None,
         spread: bool = False) -> dict:
    """Pick the largest patch that fits every power x speed (plus the orientation mark) on one lid, or use `patch`
    if given; if none fits, use the smallest and say how many lids it takes. `spread`: the widest gap that still fits,
    so the patches cover the whole lid instead of bunching at the top."""
    n = len(powers) * len(speeds)
    if patch and spread:
        for g in (8.0, 7.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5):
            cells = cells_in_circle(radius, patch, g)
            if len(cells) >= n + 1:
                return dict(patch=patch, gap=g, cells=cells, lids=1, per_lid=n)
    if patch:
        cells = cells_in_circle(radius, patch, gap)
        per = n if len(cells) >= n + 1 else max(len(powers), (len(cells) - 1) // len(powers) * len(powers))
        return dict(patch=patch, gap=gap, cells=cells, lids=math.ceil(n / per), per_lid=per)
    for size in PATCH_SIZES:
        cells = cells_in_circle(radius, size, gap)
        if len(cells) >= n + 1:
            return dict(patch=size, gap=gap, cells=cells, lids=1, per_lid=n)
    size = PATCH_SIZES[-1]
    cells = cells_in_circle(radius, size, gap)
    per = max(len(powers), (len(cells) - 1) // len(powers) * len(powers))     # whole speed sets per lid
    return dict(patch=size, gap=gap, cells=cells, lids=math.ceil(n / per), per_lid=per)


def assign(powers, speeds, cells, lid: int = 1, per_lid: int | None = None, scatter: bool = False) -> tuple:
    """(patches, mark): the orientation mark takes the top row's right-hand cell, then patches fill the other
    cells top to bottom, slowest speed first, powers left to right. `scatter` (for hottest-first ladders): the
    patches in burn order (most energy per mm first) go to cells far apart, so heat doesn't build in one spot."""
    combos = [(s, p) for s in sorted(speeds) for p in powers]
    per = per_lid or len(combos)
    combos = combos[(lid - 1) * per: lid * per]
    mark = max(cells, key=lambda c: (c[1], c[0])) if len(cells) > len(combos) else None
    rest = [c for c in cells if c != mark]
    if scatter and combos:
        combos = sorted(combos, key=lambda c: c[1] / c[0], reverse=True)
        n = len(rest)
        step = next(k for k in range(int(n * 0.38) or 1, n + 1) if math.gcd(k, n) == 1)   # far jumps, every cell once
        rest = [rest[(i * step) % n] for i in range(n)]
    patches = [dict(x=x, y=y, speed=int(s), power=float(p)) for (x, y), (s, p) in zip(rest, combos)]
    return patches, mark


def notes(powers, speeds, piece_radius: float, patches, patch: float, order: str = "fast") -> list:
    """Plain warnings for the operator: heat at slow speeds, run-ups past the lid edge, M4 at speed."""
    out = []
    e0 = STRONGEST_SO_FAR[0] / STRONGEST_SO_FAR[1]
    worst = max(p / s for p in powers for s in speeds)
    if worst > e0 * 1.5:
        out.append(f"Heat: the slowest, strongest patch puts {worst / e0:.0f}x the energy per mm into the lid of the "
                   f"strongest lid patch so far ({STRONGEST_SO_FAR[0]:g}% at {STRONGEST_SO_FAR[1]:g} mm/min). Expect "
                   "smoke, a hot lid and coating damage there. "
                   + ("Slow speeds burn last; with 'Pause after each pass' you can stop before them. " if order == "fast"
                      else "The hottest patches burn first here, while the lid is cool; with 'Pause after each pass' "
                           "you can let it cool between patches. ")
                   + "Stay with the machine and have ventilation on.")
    over = {q["speed"]: abs(q["x"]) + patch / 2 + auto_runup(q["speed"]) - piece_radius for q in patches}
    past = sorted(s for s, o in over.items() if o > 0)
    if past:
        out.append(f"Run-ups: at {', '.join(f'{s:g}' for s in past)} mm/min the head runs up to "
                   f"{max(over.values()):.1f} mm past the lid's edge with the laser off (it needs "
                   f"{auto_runup(max(past)):g} mm to reach full speed). Keep the jig and clamps clear of that path.")
    out.append("With M4 power follows the real speed. The run-ups get the head to full speed before each patch, so "
               "every patch tests its listed power and speed, not an acceleration ramp.")
    return out


ORDERS = {"fast": "Fastest speed first (coolest first)",
          "slow": "Slowest speed first",
          "hot": "Hottest first, one patch per pass: slowest speed at 100 %, then down"}


def build_lid_ladder(mat: Material, placement: Placement, powers, speeds, lid: int = 1,
                     material_note: str = "", name: str = "lid-ladder", *, skip_speeds=(), skip_patches=(),
                     done_rows=None, order: str = "fast", mark: bool = True, patch: float | None = None,
                     spread: bool = False, ramp: bool = False) -> JobPlan:
    """skip_speeds / skip_patches ([speed, power]) / done_rows ({"speed" or "speed:power": [row Y, ...]}) leave out
    what a stopped run already burned; patches keep the spots they had, so the first run's map still applies."""
    piece = placement.piece
    p = mat.pitch
    px = float(piece["w"]) / 2
    radius = px - float(piece.get("margins", (0,))[0])
    pl = plan(powers, speeds, radius, patch=patch, spread=spread)
    patches, mark_at = assign(powers, speeds, pl["cells"], lid, pl["per_lid"], scatter=spread)
    mark_pos, mark_at = mark_at, (mark_at if mark else None)
    skip = {int(s) for s in skip_speeds}
    skip_p = {patch_key(s, pw) for s, pw in skip_patches}
    done_rows = {str(k): v for k, v in (done_rows or {}).items()}
    is_done = lambda q: q["speed"] in skip or patch_key(q["speed"], q["power"]) in skip_p
    n = int(round(2 * radius / p))
    geom = layout((n, n), Placement(piece, art_w=n * p, fit="whole"), p)
    geom.cols, geom.rows = n, n
    allowed = allowed_cells(geom, piece)

    def span(cx, cy, size):
        c0 = int(round((cx - size / 2 - geom.x0) / p))
        r0 = int(round((geom.yt - (cy + size / 2)) / p))
        k = int(round(size / p))
        return slice(max(0, r0), min(n, r0 + k)), slice(max(0, c0), min(n, c0 + k))

    todo = [q for q in patches if not is_done(q)]
    if order == "hot":      # one patch per pass, most energy per mm first
        groups = [[q] for q in sorted(todo, key=lambda q: q["power"] / q["speed"], reverse=True)]
    else:
        speeds_left = sorted({q["speed"] for q in todo}, reverse=(order != "slow"))
        groups = [[q for q in todo if q["speed"] == s] for s in speeds_left]
    passes = []
    for k, group in enumerate(groups, 1):
        s = group[0]["speed"]
        cells = np.zeros((n, n), np.int16)
        for q in group:
            rs, cs = span(q["x"], q["y"], pl["patch"])
            s_val = int(round(q["power"] * 10))
            if ramp:    # solid upper half; lower half a Floyd-Steinberg dot ramp, light on the left, dark on the right
                h, w = rs.stop - rs.start, cs.stop - cs.start
                top = h // 2
                dots = imaging.fs_dots(np.tile(np.linspace(235, 20, w), (h - top, 1)))
                cells[rs.start:rs.start + top, cs] = s_val
                cells[rs.start + top:rs.stop, cs] = np.where(dots, s_val, 0)
            else:
                cells[rs, cs] = s_val
            q["order"] = k
        ys = done_rows.get(str(s), []) + (done_rows.get(patch_key(s, group[0]["power"]), []) if order == "hot" else [])
        for y in ys:                            # rows the stopped run already burned in this pass
            r = int(round((geom.yt - float(y)) / p - 0.5))
            if 0 <= r < n:
                cells[r, :] = 0
        if not passes and mark_at is not None:
            rs, cs = span(mark_at[0], mark_at[1], MARK)
            cells[rs, cs] = int(round(max(powers) * 10))
        cells[~allowed] = 0
        if not cells.any():
            continue
        what = ", ".join(f"{q['power']:g}" for q in group)
        title = f"{s:g} mm/min" if order != "hot" else f"{s:g} mm/min {group[0]['power']:g}%"
        passes.append(PassPlan(f"F{s}" if order != "hot" else f"F{s}P{group[0]['power']:g}", title,
                               f"Patches at {what} %" + (" + the orientation mark" if not passes and mark_at else ""),
                               "rows", cells, list(range(n)), int(s), None))
    # Run-ups: each speed's own (auto_runup), not the material's minimum: slow passes reach speed at once, and a
    # 4 mm wood minimum at 50 mm/min was most of a one-patch pass's time.
    job = JobPlan(name, lid_material(mat, material_note), geom, piece, passes, None, None, allowed)
    job.ladder = dict(patches=patches, mark=mark_pos, mark_burns=mark_at is not None, patch=pl["patch"],
                      gap=pl["gap"], lid=lid, lids=pl["lids"], material_note=material_note,
                      notes=notes(powers, speeds, px, todo or patches, pl["patch"], order),
                      skipped=sorted(skip), skipped_patches=sorted(skip_p), order=order, ramp=ramp)
    return job


def continuation(folder) -> dict:
    """What a stopped ladder job still has to burn: the speeds of its finished passes, and the rows of the pass it
    stopped in (from the runner's state, 'Stop after this row' keeps whole rows)."""
    import json
    import re
    from pathlib import Path
    folder = Path(folder)
    doc = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    st = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    grid = dict(doc["grid"])
    key = lambda meta: re.match(r"F(\d+)(?:P([\d.]+))?$", meta["key"])
    speeds, pats = set(grid.get("skip_speeds", [])), {tuple(x) for x in grid.get("skip_patches", [])}
    for i in st.get("completed", []):            # a finished pass: a whole speed, or one patch ("hottest first")
        m = key(doc["passes"][i])
        if m[2]:
            pats.add((int(m[1]), float(m[2])))
        else:
            speeds.add(int(m[1]))
    rows = {}
    res = st.get("resume") or {}
    if res.get("start_pass") is not None and res["start_pass"] < len(doc["passes"]):
        meta = doc["passes"][res["start_pass"]]
        lines = (folder / meta["file"]).read_text(encoding="ascii").splitlines()
        body = lines[next(i for i, l in enumerate(lines) if "BODY" in l) + 1:]
        body = [l for l in body if l and not l.startswith(";")][:int(res.get("start_index", 0))]
        ys = sorted({m[1] for l in body if (m := re.search(r"Y(-?[\d.]+) F\d+ S([1-9]\d*)", l))})
        m = key(meta)
        if ys:
            rows[patch_key(m[1], m[2]) if m[2] else str(int(m[1]))] = [float(y) for y in ys]
    return dict(grid, skip_speeds=sorted(speeds), skip_patches=sorted([s, p] for s, p in pats), done_rows=rows,
                mark=False, from_job=folder.name, phase=st.get("phase"))


def ladder_map(job: JobPlan, px_per_mm: int | None = None) -> Image.Image:
    """A printable map of the lid, seen from above as it sits on the bed: every patch's power and speed, the
    orientation mark, and the burn order."""
    lad = job.ladder
    px_per_mm = px_per_mm or max(20, int(round(66 / lad["patch"])))     # small patches: a bigger map, readable
    d = float(job.piece["w"])
    margin, header = 40, 120
    size = int(d * px_per_mm)
    lines = [w for n in lad["notes"] for w in textwrap.wrap(n, 120) + [""]]
    im = Image.new("RGB", (size + 2 * margin, size + 2 * margin + header + 22 * len(lines)), "white")
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        big = ImageFont.truetype("arialbd.ttf", 26)
    except OSError:
        font = big = ImageFont.load_default()
    cx, cy = margin + size / 2, header + margin + size / 2
    to = lambda x, y: (cx + x * px_per_mm, cy - y * px_per_mm)
    title = f"{job.name}  -  lid {lad['lid']} of {lad['lids']}" + (f"  -  {lad['material_note']}" if lad["material_note"] else "")
    dr.text((margin, 20), title, fill="black", font=big)
    dr.text((margin, 60), f"{len(lad['patches'])} patches of {lad['patch']:g} mm, {lad['gap']:g} mm gaps. Top line: "
                          "power %. Bottom: speed mm/min. Seen from above, mark at the top."
                          + (" Each patch: solid top half, dot ramp below (light left, dark right)." if lad.get("ramp") else ""), fill="black", font=font)
    order = " > ".join(p.title for p in job.passes)
    dr.text((margin, 84), f"Burn order: {order}"[:150], fill="black", font=font)
    if lad.get("skipped") or lad.get("skipped_patches"):
        dr.text((margin, 104), "Continuing a stopped ladder: red outlines = burning now, white = already burned "
                               "(same spots as the first map).", fill="red", font=font)
    dr.ellipse([cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2], outline="black", width=3)
    r = (d / 2 - float(job.piece["margins"][0])) * px_per_mm
    dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline="#999999", width=1)
    h = lad["patch"] / 2
    for q in lad["patches"]:
        (x0, y0), (x1, y1) = to(q["x"] - h, q["y"] + h), to(q["x"] + h, q["y"] - h)
        shade = int(235 - 150 * (q["power"] / 100) * min(1.0, 600 / q["speed"]))
        done = q["speed"] in lad.get("skipped", []) or patch_key(q["speed"], q["power"]) in lad.get("skipped_patches", [])
        dr.rectangle([x0, y0, x1, y1], fill=(shade, shade, shade) if not done else "white",
                     outline="black" if done else "red", width=1 if done else 3)
        if not done and lad.get("order") == "hot" and q.get("order"):
            tb = dr.textbbox((x0 + 3, y1 - 17), f"#{q['order']}", font=font)
            dr.rectangle([tb[0] - 1, tb[1] - 1, tb[2] + 1, tb[3] + 1], fill="white")
            dr.text((x0 + 3, y1 - 17), f"#{q['order']}", fill="red", font=font)
        for k, t in enumerate((f"{q['power']:g}%", f"{q['speed']:g}")):
            w = dr.textlength(t, font=font)
            dr.text(((x0 + x1) / 2 - w / 2, y0 + 3 + k * 16), t, fill="black", font=font)
    if lad["mark"]:
        mx, my = lad["mark"]
        (x0, y0), (x1, y1) = to(mx - MARK / 2, my + MARK / 2), to(mx + MARK / 2, my - MARK / 2)
        dr.rectangle([x0, y0, x1, y1], fill="black" if lad.get("mark_burns", True) else "white", outline="black")
        dr.text((x1 + 4, y0 - 4), "mark" if lad.get("mark_burns", True) else "mark (burned before)", fill="black",
                font=font)
    y = header + 2 * margin + size
    for line in lines:
        dr.text((margin, y), line, fill="black", font=font)
        y += 22
    return im
