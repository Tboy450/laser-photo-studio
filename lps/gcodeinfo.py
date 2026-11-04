"""Read any G-code project file (ours, LaserGRBL's, older project jobs) to find where it burns, for perimeter checks."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

WORD = re.compile(r"([A-Za-z])\s*([-+]?\d*\.?\d+)")


def analyse(path) -> dict:
    x = y = 0.0
    absolute = True
    motion = 0
    spindle = 5
    s = 0.0
    burn = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    travel = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    lines = 0
    smax = 0.0
    feeds = set()
    warnings = []
    segs = []          # burning moves, for telling filled rows from traced outlines
    for raw in Path(path).read_text(encoding="ascii", errors="replace").splitlines():
        line = raw.split(";")[0]
        line = re.sub(r"\(.*?\)", "", line).strip().upper()
        if not line:
            continue
        lines += 1
        if line.startswith("$"):
            if line.startswith("$H"):
                warnings.append("contains a homing command ($H) - don't run it on this machine")
            continue
        words = WORD.findall(line)
        nx, ny = x, y
        for k, v in words:
            v = float(v)
            if k == "G":
                g = int(round(v))
                if g in (0, 1, 2, 3):
                    motion = g
                elif g == 90:
                    absolute = True
                elif g == 91:
                    absolute = False
                elif g in (28, 30, 92):
                    warnings.append(f"uses G{g}")
            elif k == "M" and int(v) in (3, 4, 5):
                spindle = int(v)
            elif k == "S":
                s = v
                smax = max(smax, v)
            elif k == "F":
                feeds.add(int(v))
            elif k == "X":
                nx = v if absolute else x + v
            elif k == "Y":
                ny = v if absolute else y + v
        if (nx, ny) != (x, y):
            for px, py in ((x, y), (nx, ny)):
                travel = [min(travel[0], px), min(travel[1], py), max(travel[2], px), max(travel[3], py)]
            if motion in (1, 2, 3) and spindle in (3, 4) and s > 0:
                for px, py in ((x, y), (nx, ny)):
                    burn = [min(burn[0], px), min(burn[1], py), max(burn[2], px), max(burn[3], py)]
                segs.append((x, y, nx, ny))
            x, y = nx, ny
    ok = burn[0] != float("inf")
    return dict(lines=lines, burn_bbox=tuple(round(v, 3) for v in burn) if ok else None,
                travel_bbox=tuple(round(v, 3) for v in travel) if travel[0] != float("inf") else None,
                max_s=smax, feeds=sorted(feeds), warnings=sorted(set(warnings)), **fill_or_outline(segs))


def fill_or_outline(segs) -> dict:
    """Does the file fill shapes in (many close, parallel rows, like a picture import or this app's jobs) or only
    trace their edges (Vectorize / Centerline)? kind = 'fill', 'outline' or 'mixed'; row_pitch in mm."""
    if not segs:
        return dict(kind=None, row_pitch=None, fill_share=0.0)
    a = np.asarray(segs, float)
    dx, dy = a[:, 2] - a[:, 0], a[:, 3] - a[:, 1]
    length = np.hypot(dx, dy)
    bins = np.round(np.degrees(np.arctan2(dy, dx)) % 180).astype(int) % 180
    k = int(np.bincount(bins, weights=length, minlength=180).argmax())
    near = np.minimum((bins - k) % 180, (k - bins) % 180) <= 1      # segments running the main direction
    t = np.radians(k)
    offsets = np.unique(np.round(a[near, 0] * -np.sin(t) + a[near, 1] * np.cos(t), 3))
    gaps = np.diff(offsets)
    gaps = gaps[gaps > 0.005]
    pitch = float(np.median(gaps)) if len(gaps) else None
    share = float(length[near].sum() / max(1e-9, length.sum()))
    if len(offsets) < 10 or pitch is None or pitch > 1.0 or share < 0.5:
        # a few long edges (a stripe's outline) aren't rows, nor are a traced photo's many edges in all directions
        return dict(kind="outline", row_pitch=None, fill_share=0.0)
    return dict(kind="fill" if share >= 0.85 else "mixed", row_pitch=round(pitch, 3), fill_share=round(share, 3))


def describe_fill(info) -> tuple:
    """(plain sentence, is_warning) about how the file burns its shapes."""
    kind, pitch = info.get("kind"), info.get("row_pitch")
    if kind == "fill":
        return (f"Fills shapes in: burns rows {pitch:.2f} mm apart ({25.4 / pitch:.0f} lines/inch).", False)
    if kind == "mixed":
        return (f"Fills and outlines: about {100 * info['fill_share']:.0f}% of the burning is filled rows "
                f"{pitch:.2f} mm apart; the rest traces edges.", False)
    if kind == "outline":
        return ("OUTLINES ONLY: this file traces the edges of shapes (like LaserGRBL's Vectorize or Centerline), "
                "so shapes come out as lines, not filled in. For solid shapes use a picture import "
                "(line to line) or this app.", True)
    return ("", False)
