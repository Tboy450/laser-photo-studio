"""Read compatible G-code to locate its burn area for laser-off perimeter checks."""
from __future__ import annotations

import re
from pathlib import Path

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
            x, y = nx, ny
    ok = burn[0] != float("inf")
    return dict(lines=lines, burn_bbox=tuple(round(v, 3) for v in burn) if ok else None,
                travel_bbox=tuple(round(v, 3) for v in travel) if travel[0] != float("inf") else None,
                max_s=smax, feeds=sorted(feeds), warnings=sorted(set(warnings)))
