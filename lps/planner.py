"""Job planner: picture + material + placement -> passes of laser commands. Pure computation, no machine access.

Command forms (the only ones a job may contain, checked again by verify.py before anything is saved or sent):
  M5 S0            laser off (start/end of every row and every pass)
  M4 S0            dynamic laser mode armed at zero power
  G1 Xx Yy Ff Ss   every move, including laser-off travel (G0 is never used)
Rows run serpentine with laser-off run-ups so the head is at speed before the first mark (as in the proven
run_xmas_pass / anodized card jobs).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter

from . import imaging
from .presets import STYLES, Material, auto_runup

ACCEL = 500.0          # mm/s^2 ($120/$121 on the U20)
MAX_FEED = 6000        # mm/min ($110/$111)


def fmt(v: float) -> str:
    s = f"{v:.3f}"
    return "0.000" if s == "-0.000" else s


# --------------------------------------------------------------------------------------------- geometry
@dataclass
class Placement:
    piece: dict
    art_w: float | None = None      # requested art width, mm (None = as large as fits)
    fit: str = "whole"              # whole = keep the whole picture | fill = fill the area, crop edges
    dx: float = 0.0                 # nudge from centred, mm (+ = right)
    dy: float = 0.0                 # (+ = up / away from you)


@dataclass
class Geometry:
    pitch: float
    cols: int
    rows: int
    x0: float                       # art left edge, work mm
    yt: float                       # art top edge, work mm
    crop: tuple | None
    piece_rect: tuple
    usable_rect: tuple

    @property
    def x1(self):
        return self.x0 + self.cols * self.pitch

    @property
    def y0(self):
        return self.yt - self.rows * self.pitch

    @property
    def art_w(self):
        return self.cols * self.pitch

    @property
    def art_h(self):
        return self.rows * self.pitch

    def col_x(self, c):
        return self.x0 + c * self.pitch

    def row_y(self, r):
        return self.yt - (r + 0.5) * self.pitch


def piece_rect(piece: dict) -> tuple:
    w, h = float(piece["w"]), float(piece["h"])
    if piece.get("origin") == "center":
        return (-w / 2, -h / 2, w / 2, h / 2)
    if piece.get("origin") == "spot":      # a spot the user picked, measured from the piece's lower-left corner
        ax, ay = (float(v) for v in piece.get("spot") or (0.0, 0.0))
        return (-ax, -ay, w - ax, h - ay)
    return (0.0, 0.0, w, h)


def usable_rect(piece: dict) -> tuple:
    px0, py0, px1, py1 = piece_rect(piece)
    l, b, r, t = piece.get("margins", (0, 0, 0, 0))
    return (px0 + l, py0 + b, px1 - r, py1 - t)


def layout(img_size: tuple, placement: Placement, pitch: float) -> Geometry:
    pw, ph = img_size
    aspect = pw / max(1, ph)
    ux0, uy0, ux1, uy1 = usable_rect(placement.piece)
    uw, uh = max(1.0, ux1 - ux0), max(1.0, uy1 - uy0)
    crop = None
    if placement.fit == "fill":
        aw, ah = uw, uh
        target = uw / uh
        if aspect > target:
            cw = ph * target
            crop = ((pw - cw) / 2, 0, (pw + cw) / 2, ph)
        else:
            ch = pw / target
            crop = (0, (ph - ch) / 2, pw, (ph + ch) / 2)
    else:
        aw = placement.art_w or min(uw, uh * aspect)
        ah = aw / aspect
    cols, rows = max(1, int(round(aw / pitch))), max(1, int(round(ah / pitch)))
    cx = (ux0 + ux1) / 2 + placement.dx
    cy = (uy0 + uy1) / 2 + placement.dy
    x0 = round(cx - cols * pitch / 2, 2)
    yt = round(cy + rows * pitch / 2, 2)
    return Geometry(pitch, cols, rows, x0, yt, crop, piece_rect(placement.piece), (ux0, uy0, ux1, uy1))


def allowed_cells(geom: Geometry, piece: dict) -> np.ndarray:
    """Cells whose centre lies in the usable area and outside every keep-out zone."""
    xs = geom.x0 + (np.arange(geom.cols) + 0.5) * geom.pitch
    ys = geom.yt - (np.arange(geom.rows) + 0.5) * geom.pitch
    X, Y = np.meshgrid(xs, ys)
    px0, py0, px1, py1 = geom.piece_rect
    ux0, uy0, ux1, uy1 = geom.usable_rect
    if piece.get("shape") == "circle":
        cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
        rad = (px1 - px0) / 2 - float(piece.get("margins", (0,))[0])
        ok = (X - cx) ** 2 + (Y - cy) ** 2 <= rad * rad
    else:
        ok = (X >= ux0) & (X <= ux1) & (Y >= uy0) & (Y <= uy1)
        rc = max(0.0, float(piece.get("corner", 0.0)) - min(piece.get("margins", (0, 0, 0, 0))))
        if rc > 0:
            for ccx, ccy in ((ux0 + rc, uy0 + rc), (ux1 - rc, uy0 + rc), (ux0 + rc, uy1 - rc), (ux1 - rc, uy1 - rc)):
                corner = (np.abs(X - ccx) <= rc) & (np.abs(Y - ccy) <= rc) & \
                         (np.sign(X - ccx) == np.sign(ccx - (ux0 + ux1) / 2)) & \
                         (np.sign(Y - ccy) == np.sign(ccy - (uy0 + uy1) / 2))
                ok &= ~(corner & ((X - ccx) ** 2 + (Y - ccy) ** 2 > rc * rc))
    for k in piece.get("keepouts", []):
        kx, ky = px0 + float(k["x"]), py0 + float(k["y"])
        if k.get("kind") == "circle":
            ok &= (X - kx) ** 2 + (Y - ky) ** 2 > float(k["r"]) ** 2
        else:
            w, h = float(k.get("w", 0)), float(k.get("h", 0))
            ok &= ~((X >= kx) & (X <= kx + w) & (Y >= ky) & (Y <= ky + h))
    return ok


# --------------------------------------------------------------------------------------------- dot styles
KERNELS = {  # error diffusion: same-row weights (x+1, x+2) and next rows {dy: [(dx, w), ...]}, divisor
    "jarvis": ((7, 5), {1: [(-2, 3), (-1, 5), (0, 7), (1, 5), (2, 3)], 2: [(-2, 1), (-1, 3), (0, 5), (1, 3), (2, 1)]}, 48),
    "stucki": ((8, 4), {1: [(-2, 2), (-1, 4), (0, 8), (1, 4), (2, 2)], 2: [(-2, 1), (-1, 2), (0, 4), (1, 2), (2, 1)]}, 42),
    "atkinson": ((1, 1), {1: [(-1, 1), (0, 1), (1, 1)], 2: [(0, 1)]}, 8),
}


def error_diffusion(a: np.ndarray, kind: str) -> np.ndarray:
    """Serpentine error diffusion; True = burn. Row loop in Python, next-row spreading in NumPy."""
    (w1, w2), below, div = KERNELS[kind]
    img = a.astype(np.float64).copy()
    H, W = img.shape
    out = np.zeros((H, W), bool)
    w1, w2 = w1 / div, w2 / div
    below = {dy: [(dx, w / div) for dx, w in lst] for dy, lst in below.items()}
    for y in range(H):
        rev = y % 2 == 1
        row = (img[y, ::-1] if rev else img[y]).tolist()
        err = [0.0] * W
        burn = [False] * W
        c1 = c2 = 0.0
        for x in range(W):
            v = row[x] + c1
            c1, c2 = c2, 0.0
            if v < 128.0:
                burn[x] = True
                e = v
            else:
                e = v - 255.0
            err[x] = e
            c1 += e * w1
            c2 += e * w2
        e_arr = np.asarray(err)
        b_arr = np.asarray(burn)
        if rev:
            e_arr, b_arr = e_arr[::-1], b_arr[::-1]
        out[y] = b_arr
        for dy, lst in below.items():
            if y + dy >= H:
                continue
            tgt = img[y + dy]
            for dx, w in lst:
                dx = -dx if rev else dx
                if dx >= 0:
                    tgt[dx:] += e_arr[:W - dx] * w
                else:
                    tgt[:W + dx] += e_arr[-dx:] * w
    return out


BAYER8 = None


def ordered_dots(a: np.ndarray) -> np.ndarray:
    global BAYER8
    if BAYER8 is None:
        m = np.array([[0, 2], [3, 1]])
        for _ in range(2):
            m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
        BAYER8 = (m + 0.5) / 64.0
    H, W = a.shape
    t = np.tile(BAYER8, (H // 8 + 1, W // 8 + 1))[:H, :W]
    return (1.0 - a / 255.0) > t


def halftone_dots(a: np.ndarray, cell_cells: float) -> np.ndarray:
    """Round dots on a 45-degree screen that grow with darkness (cosine spot function)."""
    H, W = a.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    period = max(2.0, cell_cells)
    u = (xx + yy) / (math.sqrt(2) * period)
    v = (xx - yy) / (math.sqrt(2) * period)
    spot = (1.0 - (np.cos(2 * math.pi * u) + np.cos(2 * math.pi * v)) / 2.0) / 2.0
    return (1.0 - a / 255.0) > spot


def sketch_lines(a: np.ndarray, pitch: float) -> np.ndarray:
    """Colour-dodge pencil sketch, then keep the drawn strokes."""
    g = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
    inv = Image.fromarray(255 - np.asarray(g), "L").filter(ImageFilter.GaussianBlur(max(1.0, 0.4 / pitch)))
    gi, bi = np.asarray(g, np.float64), np.asarray(inv, np.float64)
    dodge = np.clip(gi * 255.0 / np.maximum(1.0, 255.0 - bi), 0, 255)
    lines = dodge < 205
    lone = lines & ~(np.roll(lines, 1, 0) | np.roll(lines, -1, 0) | np.roll(lines, 1, 1) | np.roll(lines, -1, 1))
    return lines & ~lone


# --------------------------------------------------------------------------------------------- passes
@dataclass
class PassPlan:
    key: str
    title: str
    explain: str
    kind: str                         # rows | features
    cells: np.ndarray                 # int16 power per cell, 0 = not burned in this pass
    order: list | None = None         # row order (rows passes)
    feed: int = 2250
    row_feeds: np.ndarray | None = None   # per-row burn feed (test grids)
    commands: list = field(default_factory=list)
    est_s: float = 0.0


@dataclass
class JobPlan:
    name: str
    material: Material
    geom: Geometry
    piece: dict
    passes: list
    gray: np.ndarray | None = None
    levels: np.ndarray | None = None
    allowed: np.ndarray | None = None
    labels: np.ndarray | None = None
    compiled: bool = False

    @property
    def burn_cells(self) -> int:
        return int(sum((p.cells > 0).sum() for p in self.passes))

    def burn_bbox(self):
        any_burn = np.zeros((self.geom.rows, self.geom.cols), bool)
        for p in self.passes:
            any_burn |= p.cells > 0
        if not any_burn.any():
            return None
        rr = np.flatnonzero(any_burn.any(axis=1))
        cc = np.flatnonzero(any_burn.any(axis=0))
        g = self.geom
        return (round(g.col_x(cc[0]), 3), round(g.yt - (rr[-1] + 1) * g.pitch, 3),
                round(g.col_x(cc[-1] + 1), 3), round(g.yt - rr[0] * g.pitch, 3))

    @property
    def est_s(self) -> float:
        return sum(p.est_s for p in self.passes)


def _tone_words(min_tone: int) -> str:
    return {1: "all tones", 2: "mid and dark tones", 3: "dark tones only"}.get(min_tone, "all tones")


def plan_cells(gray: np.ndarray, mat: Material, geom: Geometry, allowed: np.ndarray, name: str = "job",
               piece: dict | None = None) -> JobPlan:
    """Decide which cells burn in which pass (fast; used for previews)."""
    H, W = gray.shape
    passes: list[PassPlan] = []
    levels = labels = None
    style = mat.style
    if style == "layers":
        levels = imaging.tone_levels(gray, mat.tone_cuts, mat.widen_gaps)
        levels[~allowed] = 0
        shade = np.zeros((H, W), np.int16)
        for t in (1, 2, 3):
            shade[levels == t] = mat.tone_power[t - 1]
        burn = levels > 0
        thin = None
        if mat.thin_pass:
            thin, labels = imaging.thin_features(burn)
        n = max(1, mat.interlace)
        for k, (min_tone, shrink) in enumerate(mat.layer_rule):
            m = imaging.erode_n(burn & (levels >= min_tone), int(shrink))
            group = k % n
            rows = [r for r in range(H) if r % n == group]
            sel = np.zeros(H, bool)
            sel[rows] = True
            cells = np.where(m & sel[:, None], shade, 0).astype(np.int16)
            smaller = f", {shrink * mat.pitch:.1f} mm smaller" if shrink else ""
            passes.append(PassPlan(
                f"L{k + 1}", f"Layer {k + 1}",
                f"Every {n}th row (group {group + 1}), {_tone_words(min_tone)}{smaller}", "rows", cells, rows,
                mat.feed))
            if k == 0 and thin is not None and thin.any():
                center = imaging.skeleton(thin)
                tcells = np.where(center & (cells == 0), np.minimum(shade, mat.thin_cap), 0).astype(np.int16)
                if tcells.any():
                    passes.append(PassPlan("L1thin", "Thin lines",
                                           f"Lettering and fine lines as centerlines (max {mat.thin_cap / 10:.0f}%)",
                                           "features", tcells, None, mat.feed))
    else:
        if style == "floyd":
            dots = imaging.fs_dots(gray)
        elif style in KERNELS:
            dots = error_diffusion(gray, style)
        elif style == "bayer":
            dots = ordered_dots(gray)
        elif style == "halftone":
            dots = halftone_dots(gray, mat.halftone_cell / mat.pitch)
        elif style == "threshold":
            dots = gray < 128
        elif style == "centerline":
            dots = imaging.skeleton(gray < 128)
        elif style == "sketch":
            dots = sketch_lines(gray, mat.pitch)
        elif style == "grayscale":
            dots = None
        else:
            raise ValueError(f"unknown style {style}")
        if dots is None:
            dark = 1.0 - gray / 255.0
            q = np.round(dark * 15.0) / 15.0
            cells = np.where((q > 0) & allowed,
                             np.round(mat.power_min + q * (mat.power - mat.power_min)), 0).astype(np.int16)
        else:
            cells = np.where(dots & allowed, mat.power, 0).astype(np.int16)
        n = max(1, mat.interlace)
        order = [r for g in range(n) for r in range(H) if r % n == g]
        info = STYLES[style]["name"]
        explain = info + (f", rows in {n} cooling groups" if n > 1 else "")
        for k in range(max(1, mat.passes)):
            title = "Engrave" if mat.passes <= 1 else f"Pass {k + 1}"
            passes.append(PassPlan(f"P{k + 1}", title, explain, "rows", cells, order, mat.feed))
    return JobPlan(name, mat, geom, piece or {}, passes, gray, levels, allowed, labels)


# --------------------------------------------------------------------------------------------- commands
def raster_commands(cells: np.ndarray, order, geom: Geometry, feed: int, row_feed: int, runup: float,
                    row_feeds=None, accel: float = ACCEL) -> list:
    cmds = []
    flip = False
    for r in order if order is not None else range(cells.shape[0]):
        row = cells[r]
        nz = np.flatnonzero(row)
        if not len(nz):
            continue
        f = int(row_feeds[r]) if row_feeds is not None else int(feed)
        ru = max(runup, auto_runup(f, accel))
        a0, a1 = int(nz[0]), int(nz[-1]) + 1
        seg = row[a0:a1]
        cuts = np.r_[0, np.flatnonzero(np.diff(seg)) + 1, len(seg)]
        xs = [geom.col_x(a0 + c) for c in cuts]
        powers = [int(seg[c]) for c in cuts[:-1]]
        if flip:
            start, ends, pw, d = xs[-1], xs[-2::-1], powers[::-1], -1
        else:
            start, ends, pw, d = xs[0], xs[1:], powers, 1
        y = fmt(geom.row_y(r))
        cmds += ["M5 S0", f"G1 X{fmt(start - d * ru)} Y{y} F{row_feed} S0", "M4 S0",
                 f"G1 X{fmt(start)} Y{y} F{f} S0"]
        cmds += [f"G1 X{fmt(e)} Y{y} F{f} S{s}" for e, s in zip(ends, pw)]
        cmds += [f"G1 X{fmt(ends[-1] + d * ru)} Y{y} F{f} S0", "M5 S0"]
        flip = not flip
    return cmds


def feature_commands(cells: np.ndarray, labels: np.ndarray, geom: Geometry, feed: int, hop_feed: int,
                     runup: float, start=(0.0, 0.0)) -> list:
    """Thin features one at a time (nearest next), each as a tiny serpentine raster with short run-ups."""
    lab = np.where(cells > 0, labels, 0)
    ids = [int(i) for i in np.unique(lab) if i]
    if not ids:
        return []
    rr, cc = np.nonzero(lab)
    li = lab[rr, cc]
    order = np.argsort(li, kind="stable")
    rr, cc, li = rr[order], cc[order], li[order]
    bounds = np.flatnonzero(np.diff(li)) + 1
    groups = np.split(np.arange(len(li)), bounds)
    bbox = {}
    for g in groups:
        i = int(li[g[0]])
        bbox[i] = (int(rr[g].min()), int(cc[g].min()), int(rr[g].max()), int(cc[g].max()))
    cen = {i: (geom.col_x((b[1] + b[3] + 1) / 2), geom.row_y((b[0] + b[2]) / 2)) for i, b in bbox.items()}
    id_arr = np.array(sorted(bbox))
    cx = np.array([cen[i][0] for i in id_arr])
    cy = np.array([cen[i][1] for i in id_arr])
    alive = np.ones(len(id_arr), bool)
    cmds, pos = [], start
    for _ in range(len(id_arr)):
        dist = (cx - pos[0]) ** 2 + (cy - pos[1]) ** 2
        dist[~alive] = np.inf
        j = int(np.argmin(dist))
        alive[j] = False
        i = int(id_arr[j])
        r0, c0, r1, c1 = bbox[i]
        sub = np.where(lab[r0:r1 + 1, c0:c1 + 1] == i, cells[r0:r1 + 1, c0:c1 + 1], 0)
        flip = False
        for k in range(sub.shape[0]):
            row = sub[k]
            nz = np.flatnonzero(row)
            if not len(nz):
                continue
            a0, a1 = int(nz[0]), int(nz[-1]) + 1
            seg = row[a0:a1]
            cuts = np.r_[0, np.flatnonzero(np.diff(seg)) + 1, len(seg)]
            xs = [geom.col_x(c0 + a0 + c) for c in cuts]
            powers = [int(seg[c]) for c in cuts[:-1]]
            if flip:
                st, ends, pw, d = xs[-1], xs[-2::-1], powers[::-1], -1
            else:
                st, ends, pw, d = xs[0], xs[1:], powers, 1
            y = fmt(geom.row_y(r0 + k))
            cmds += ["M5 S0", f"G1 X{fmt(st - d * runup)} Y{y} F{hop_feed} S0", "M4 S0",
                     f"G1 X{fmt(st)} Y{y} F{feed} S0"]
            cmds += [f"G1 X{fmt(e)} Y{y} F{feed} S{s}" for e, s in zip(ends, pw)]
            cmds += [f"G1 X{fmt(ends[-1] + d * runup)} Y{y} F{feed} S0", "M5 S0"]
            flip = not flip
        pos = cen[i]
    return cmds


def estimate_seconds(cmds, accel: float = ACCEL, per_command: float = 0.003) -> float:
    x = y = 0.0
    t = 0.0
    for c in cmds:
        if c[0] != "G":
            if c.startswith("M4"):
                t += 0.05
            continue
        parts = c.split()
        nx, ny, f = float(parts[1][1:]), float(parts[2][1:]), float(parts[3][1:])
        d = math.hypot(nx - x, ny - y)
        v = f / 60.0
        t += d / v + (v / accel if d > 0 and abs(ny - y) > 1e-9 else 0.0)
        x, y = nx, ny
    return t + per_command * len(cmds)


def compile_job(job: JobPlan, start=(0.0, 0.0)) -> JobPlan:
    """Generate the command lists for every pass (slower than plan_cells)."""
    m = job.material
    pos = start
    for p in job.passes:
        if p.kind == "features":
            p.commands = feature_commands(p.cells, job.labels, job.geom, p.feed, m.hop_feed, m.feature_runup, pos)
        else:
            p.commands = raster_commands(p.cells, p.order, job.geom, p.feed, m.row_feed, m.runup, p.row_feeds)
        p.est_s = estimate_seconds(p.commands)
        for c in reversed(p.commands):
            if c.startswith("G1"):
                parts = c.split()
                pos = (float(parts[1][1:]), float(parts[2][1:]))
                break
    job.compiled = True
    return job


def build_job(picture: Image.Image, mat: Material, placement: Placement, look: dict | None = None,
              name: str = "job") -> JobPlan:
    """Picture -> JobPlan with cells decided (call compile_job for commands)."""
    look = dict(look or {})
    geom = layout(picture.size, placement, mat.pitch)
    gray = imaging.to_grid(
        picture, geom.cols, geom.rows, geom.crop,
        autolevel=look.get("autolevel", mat.autolevel), brightness=look.get("brightness", mat.brightness),
        contrast=look.get("contrast", mat.contrast), gamma=look.get("gamma", mat.gamma),
        negative=look.get("negative", mat.negative), sharpen=look.get("sharpen", mat.sharpen))
    allowed = allowed_cells(geom, placement.piece)
    return plan_cells(gray, mat, geom, allowed, name, placement.piece)


# --------------------------------------------------------------------------------------------- test grid
def build_test_grid(mat: Material, placement: Placement, powers_pct, speeds, patch: float = 8.0,
                    gap: float = 4.0, content: str = "solid+ramp", name: str = "test-grid") -> JobPlan:
    """Larger labelled patches across power (columns) x speed (rows). Each raster line crosses a whole patch row
    at that row's speed. Labels (power % on top, speed on the left) burn in their own pass at a middle setting."""
    p = mat.pitch
    pc = int(round(patch / p))
    gc = int(round(gap / p))
    label_h = int(round(2.6 / p))
    left_w = int(round(9.0 / p))
    ncol, nrow = len(powers_pct), len(speeds)
    cols = left_w + ncol * pc + (ncol - 1) * gc
    rows = label_h + gc + nrow * pc + (nrow - 1) * gc
    cells = np.zeros((rows, cols), np.int16)
    feeds = np.zeros(rows, np.int32)
    ramp = None
    if content == "solid+ramp":
        grad = np.tile(np.linspace(235, 20, pc), (pc - pc // 2, 1))
        ramp = imaging.fs_dots(grad)
    for j, f in enumerate(speeds):
        r0 = label_h + gc + j * (pc + gc)
        feeds[r0:r0 + pc] = int(f)
        for i, pw in enumerate(powers_pct):
            c0 = left_w + i * (pc + gc)
            s = int(round(pw * 10))
            if ramp is None:
                cells[r0:r0 + pc, c0:c0 + pc] = s
            else:
                cells[r0:r0 + pc // 2, c0:c0 + pc] = s
                cells[r0 + pc // 2:r0 + pc, c0:c0 + pc] = np.where(ramp, s, 0)
    lab_s = int(round(sorted(powers_pct)[len(powers_pct) // 2] * 10))
    lab_f = int(sorted(speeds)[len(speeds) // 2])
    lcells = np.zeros_like(cells)
    lfeeds = np.full(rows, lab_f, np.int32)

    def stamp(text, r, c, h, max_w):
        mk = imaging.text_mask(text, h)
        hh, ww = mk.shape
        r, c = max(0, r), max(0, c)
        hh, ww = min(hh, rows - r), min(ww, cols - c, max_w)
        lcells[r:r + hh, c:c + ww] = np.where(mk[:hh, :ww], lab_s, lcells[r:r + hh, c:c + ww]).astype(np.int16)

    for i, pw in enumerate(powers_pct):
        stamp(f"{pw:g}", 0, left_w + i * (pc + gc) + pc // 4, label_h - 2, pc + gc)
    for j, f in enumerate(speeds):
        stamp(f"{f / 1000:g}k", label_h + gc + j * (pc + gc) + pc // 3, 0, int(label_h * 0.8), left_w - 2)
    pl = Placement(placement.piece, art_w=cols * p, fit="whole", dx=placement.dx, dy=placement.dy)
    geom = layout((cols, rows), pl, p)
    geom.cols, geom.rows = cols, rows
    allowed = allowed_cells(geom, placement.piece)
    cells[~allowed] = 0
    lcells[~allowed] = 0
    g = mat.copy(style="threshold")
    order = list(range(rows))
    passes = [PassPlan("GRID", "Test patches", "Power % across, speed down; each patch: solid top, dot ramp below",
                       "rows", cells, order, int(max(speeds)), feeds),
              PassPlan("LABELS", "Labels", f"Settings text at {lab_s / 10:g}% / {lab_f} mm/min", "rows",
                       lcells, order, lab_f, lfeeds)]
    return JobPlan(name, g, geom, placement.piece, passes, None, None, allowed)


def perimeter_points(bbox, spacing: float | None = None) -> list:
    """Corners (and optional points every `spacing` mm) around the burn area, starting lower-left, anticlockwise."""
    x0, y0, x1, y1 = bbox
    corners = [(x0, y0, "lower-left"), (x1, y0, "lower-right"), (x1, y1, "upper-right"), (x0, y1, "upper-left")]
    if not spacing:
        return corners
    pts = []
    for (ax, ay, an), (bx, by, _) in zip(corners, corners[1:] + corners[:1]):
        pts.append((ax, ay, an))
        d = math.hypot(bx - ax, by - ay)
        n = int(d // spacing)
        for k in range(1, n):
            t = k * spacing / d
            if d - k * spacing > spacing * 0.4:
                pts.append((round(ax + (bx - ax) * t, 3), round(ay + (by - ay) * t, 3), "edge"))
    return pts
