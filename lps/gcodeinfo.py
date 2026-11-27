"""Read compatible G-code to locate its burn area for laser-off perimeter checks."""
from __future__ import annotations

import re
import math
from pathlib import Path

import numpy as np

WORD = re.compile(r"([A-Za-z])\s*([-+]?\d*\.?\d+)")
PICTURE_BOX = re.compile(r"; Picture box \[mm\]: X([-\d.]+) Y([-\d.]+) W([-\d.]+) H([-\d.]+)")
GRID = re.compile(r'; Burn grid: C(\d+) R(\d+) DX([\d.]+) DY([\d.]+)')


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
    linear_xy = True
    segs = []          # burning moves, for telling filled rows from traced outlines
    boxes = set()
    grids = set()
    for raw in Path(path).read_text(encoding="ascii", errors="replace").splitlines():
        box_match = PICTURE_BOX.fullmatch(raw.strip())
        if box_match:
            try:
                boxes.add(tuple(float(v) for v in box_match.groups()))
            except ValueError:
                pass
        grid_match=GRID.fullmatch(raw.strip())
        if grid_match:
            grids.add(tuple(float(v) for v in grid_match.groups()))
        line = raw.split(";")[0]
        line = re.sub(r"\(.*?\)", "", line).strip().upper()
        if not line:
            continue
        lines += 1
        if line.startswith("$"):
            linear_xy = False
            if line.startswith("$H"):
                warnings.append("contains a homing command ($H) - don't run it on this machine")
            continue
        words = WORD.findall(line)
        # An approximate preview can still be displayed for other files. Only frame a travel
        # envelope on the machine when the file is a supported, millimeter XY program.
        if (WORD.sub("", line).strip() or any(
                k not in "GMXYFS" or (k == "G" and float(v) not in (0, 1, 21, 54, 90, 91, 94))
                or (k == "M" and float(v) not in (3, 4, 5)) for k, v in words)):
            linear_xy = False
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
    picture_bbox = None
    if len(boxes) == 1:
        bx, by, bw, bh = next(iter(boxes))
        if (all(math.isfinite(v) for v in (bx,by,bw,bh)) and bw>0 and bh>0 and
                (not ok or (bx-0.002<=burn[0] and by-0.002<=burn[1] and
                            bx+bw+0.002>=burn[2] and by+bh+0.002>=burn[3]))):
            picture_bbox = tuple(round(v,3) for v in (bx,by,bx+bw,by+bh))
        else:
            warnings.append("picture-box metadata does not contain the burn; checking burned marks instead")
    elif len(boxes)>1:
        warnings.append("conflicting picture boxes; checking burned marks instead")
    traces=None
    if picture_bbox and len(grids)==1:
        cols,rows,dx,dy=next(iter(grids))
        if (0<cols*rows<=10000000 and dx>0 and dy>0 and
                abs(cols*dx-(picture_bbox[2]-picture_bbox[0]))<.002 and
                abs(rows*dy-(picture_bbox[3]-picture_bbox[1]))<.002):
            mask=np.zeros((int(rows),int(cols)),bool)
            for ax,ay,bx,by in segs:
                r=(picture_bbox[3]-ay)/dy-.5
                left=(min(ax,bx)-picture_bbox[0])/dx
                right=(max(ax,bx)-picture_bbox[0])/dx
                ri,a,b=round(r),round(left),round(right)
                if (abs(ay-by)>.001 or abs(r-ri)*dy>.0011 or abs(left-a)*dx>.0011 or
                        abs(right-b)*dx>.0011 or not(0<=ri<rows and 0<=a<=b<=cols)):
                    break
                mask[ri,a:b]=True
            else:
                from .outlines import exterior_contours
                traces = exterior_contours(mask, picture_bbox[0], picture_bbox[3], dx, dy)
    return dict(lines=lines, burn_bbox=tuple(round(v, 3) for v in burn) if ok else None,
                picture_bbox=picture_bbox,
                trace_paths=traces, linear_xy=linear_xy,
                travel_bbox=tuple(round(v, 3) for v in travel) if travel[0] != float("inf") else None,
                max_s=smax, feeds=sorted(feeds), warnings=sorted(set(warnings)), **fill_or_outline(segs))


def frame_bbox(info):
    """Keep this app's declared image box; external files without one can only expose mark bounds."""
    return info.get("picture_bbox") or info.get("burn_bbox")


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
        return ("OUTLINES ONLY: this file traces edges or centerlines, "
                "so shapes come out as lines, not filled in. For solid shapes use a picture import "
                "(line to line) or this app.", True)
    return ("", False)
