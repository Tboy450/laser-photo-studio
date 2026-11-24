"""Job planner: picture + material + placement -> passes of laser commands. Pure computation, no machine access.

Command forms (the only ones a job may contain, checked again by verify.py before anything is saved or sent):
  M5 S0            laser off (start/end of every row and every pass)
  M4 S0            dynamic laser mode armed at zero power
  G1 Xx Yy Ff Ss   every move, including laser-off travel (G0 is never used)
Burn-in-place ("dwell") and crawl passes only, checked by their own rules in verify.py:
  M3 Sn            constant power: at a chosen spot standing still (dwell), or along one planned line (crawl)
  G4 Ps            wait s seconds (the burn, a crawl step's pause, or a laser-off cool-down after M5 S0)
Rows run serpentine with laser-off run-ups so the head is at speed before the first mark (as in the proven
run_xmas_pass / anodized card jobs).
"""
from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image, ImageFilter

from . import imaging
from .presets import STYLES, Material, auto_runup

ACCEL = 500.0          # mm/s^2 ($120/$121 on the U20)
MAX_FEED = 6000        # mm/min ($110/$111)
DWELL_MAX_S = 60.0     # longest single burn-in-place spot
COOL_MAX_S = 300.0     # longest laser-off wait between spots
SPOT_GAP_MIN = 1.0     # mm between burn-in-place spot centres: each spot is its own burn, never stacked in one place
CRAWL_MIN_FEED = 30    # crawl moves run at or above this (the controller ignores feeds below about 24 mm/min)
CRAWL_QUANTUM_S = 0.05 # Grbl 1.1h rounds every G4 up to a whole number of 50 ms steps
CRAWL_MAX_PAUSE_S = 2.0
CRAWL_MIN_AVG = 0.5    # slowest crawl average, mm/min


def fmt(v: float) -> str:
    s = f"{v:.3f}"
    return "0.000" if s == "-0.000" else s


# --------------------------------------------------------------------------------------------- geometry
@dataclass
class Placement:
    piece: dict
    art_w: float | None = None      # requested image or mark width, mm (None = largest that fits)
    fit: str = "whole"              # whole | fill (crop) | exact (legacy image box) | art-exact | marks
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
    cell_w: float | None = None     # exact sizing can adjust sampling, never the requested box
    cell_h: float | None = None

    @property
    def x_pitch(self):
        return self.pitch if self.cell_w is None else self.cell_w

    @property
    def y_pitch(self):
        return self.pitch if self.cell_h is None else self.cell_h

    @property
    def x1(self):
        return self.x0 + self.cols * self.x_pitch

    @property
    def y0(self):
        return self.yt - self.rows * self.y_pitch

    @property
    def art_w(self):
        return self.cols * self.x_pitch

    @property
    def art_h(self):
        return self.rows * self.y_pitch

    def col_x(self, c):
        return self.x0 + c * self.x_pitch

    def row_y(self, r):
        return self.yt - (r + 0.5) * self.y_pitch


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
    if placement.fit == "exact":
        rect = piece_rect(placement.piece)
        x0, y0, x1, yt = rect
        aw, ah = x1 - x0, yt - y0
        if not all(math.isfinite(v) and v > 0 for v in (aw, ah, pitch)):
            raise ValueError("Width, height and row spacing must be positive finite numbers.")
        cols, rows = max(1, round(aw / pitch)), max(1, round(ah / pitch))
        # Changing resolution must not shrink the physical picture or shift its corner.
        return Geometry(pitch, cols, rows, x0, yt, None, rect, rect, aw / cols, ah / rows)
    ux0, uy0, ux1, uy1 = usable_rect(placement.piece)
    uw, uh = max(1.0, ux1 - ux0), max(1.0, uy1 - uy0)
    if placement.fit == "art-exact":
        aw = min(placement.art_w or uw, uw, uh * aspect)
        ah = aw / aspect
        if not all(math.isfinite(v) and v > 0 for v in (aw, ah, pitch)):
            raise ValueError("Width, height and row spacing must be positive finite numbers.")
        cols, rows = max(1, round(aw / pitch)), max(1, round(ah / pitch))
        x0 = (ux0 + ux1 - aw) / 2 + placement.dx
        yt = (uy0 + uy1 + ah) / 2 + placement.dy
        return Geometry(pitch, cols, rows, x0, yt, None, piece_rect(placement.piece),
                        (ux0, uy0, ux1, uy1), aw / cols, ah / rows)
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
        if placement.fit == "whole":
            aw = min(aw, uw, uh * aspect)
        ah = aw / aspect
    cols, rows = max(1, int(round(aw / pitch))), max(1, int(round(ah / pitch)))
    if cols * pitch > uw + 1e-9:     # rounding up mustn't push the art past the usable area (e.g. 84.36 mm wide)
        cols = max(1, int(uw / pitch + 1e-9))
    if rows * pitch > uh + 1e-9:
        rows = max(1, int(uh / pitch + 1e-9))
    cx = (ux0 + ux1) / 2 + placement.dx
    cy = (uy0 + uy1) / 2 + placement.dy
    x0 = round(cx - cols * pitch / 2, 2)
    yt = round(cy + rows * pitch / 2, 2)
    return Geometry(pitch, cols, rows, x0, yt, crop, piece_rect(placement.piece), (ux0, uy0, ux1, uy1))


def allowed_cells(geom: Geometry, piece: dict) -> np.ndarray:
    """Cells whose centre lies in the usable area and outside every keep-out zone."""
    xs = geom.x0 + (np.arange(geom.cols) + 0.5) * geom.x_pitch
    ys = geom.yt - (np.arange(geom.rows) + 0.5) * geom.y_pitch
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
    if piece.get("outline"):
        ok &= outline_mask(geom, piece)
    for k in piece.get("keepouts", []):
        kx, ky = px0 + float(k["x"]), py0 + float(k["y"])
        if k.get("kind") == "circle":
            ok &= (X - kx) ** 2 + (Y - ky) ** 2 > float(k["r"]) ** 2
        else:
            w, h = float(k.get("w", 0)), float(k.get("h", 0))
            ok &= ~((X >= kx) & (X <= kx + w) & (Y >= ky) & (Y <= ky + h))
    return ok


def outline_path(piece: dict, piece_rect_xy) -> list:
    """A shaped piece's outline (piece mm from its lower-left corner) in work mm, closed."""
    px0, py0 = piece_rect_xy
    pts = [(round(px0 + float(x), 3), round(py0 + float(y), 3)) for x, y in piece["outline"]]
    return pts + pts[:1] if pts and pts[0] != pts[-1] else pts


def outline_mask(geom: Geometry, piece: dict) -> np.ndarray:
    """Cells whose centre is inside the piece's outline polygon (a cross, a shield...)."""
    from PIL import ImageDraw
    px0, py0 = geom.piece_rect[0], geom.piece_rect[1]
    poly = [((px0 + float(x) - geom.x0) / geom.x_pitch - 0.5, (geom.yt - (py0 + float(y))) / geom.y_pitch - 0.5)
            for x, y in piece["outline"]]
    im = Image.new("1", (geom.cols, geom.rows), 0)
    d = ImageDraw.Draw(im)
    d.polygon(poly, fill=1)
    d.line(poly + poly[:1], fill=0, width=1)        # conservative: cells the edge touches are left unburned
    return np.asarray(im, dtype=bool)


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
    kind: str                         # rows | features | dwell
    cells: np.ndarray                 # int16 power per cell, 0 = not burned in this pass (dwell: the spot cells)
    order: list | None = None         # row order (rows passes)
    feed: int = 2250                  # burn feed (dwell: the laser-off travel feed)
    row_feeds: np.ndarray | None = None   # per-row burn feed (test grids)
    commands: list = field(default_factory=list)
    est_s: float = 0.0
    spots: list | None = None         # dwell: [dict(x, y, s, seconds)] on cell centres, burned in this order
    cool_s: float = 0.0               # dwell: laser-off wait after each spot (not after the last)
    lines: list | None = None         # crawl: [dict(x0, x1, y, s, step, steps, feed, pause, v_avg, v_target)]


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
    _outlines: dict = field(default_factory=dict, repr=False)
    _outline_key: str | None = field(default=None,repr=False)
    sizing_note: str = ""

    def trace_paths(self, pass_keys=None):
        if pass_keys not in self._outlines:
            from .outlines import exterior_contours
            g = self.geom
            mask = np.zeros((g.rows, g.cols), bool)
            for p in self.passes:
                if pass_keys is None or p.key in pass_keys:
                    mask |= p.cells > 0
            if pass_keys is None:
                self._outline_key = hashlib.sha256(mask.tobytes()).hexdigest()
            self._outlines[pass_keys] = exterior_contours(mask, g.x0, g.yt, g.x_pitch, g.y_pitch)
        return self._outlines[pass_keys]

    def outline_key(self):
        self.trace_paths()
        g=self.geom
        return (g.x0,g.y0,g.x1,g.yt,self._outline_key)

    @property
    def burn_cells(self) -> int:
        return int(sum((p.cells > 0).sum() for p in self.passes))

    def powered_cell_bounds(self):
        any_burn = np.zeros((self.geom.rows, self.geom.cols), bool)
        for p in self.passes:
            any_burn |= p.cells > 0
        rr = np.flatnonzero(any_burn.any(axis=1))
        cc = np.flatnonzero(any_burn.any(axis=0))
        return (int(cc[0]), int(rr[0]), int(cc[-1]) + 1, int(rr[-1]) + 1) if len(cc) else None

    def burn_bbox(self):
        bounds = self.powered_cell_bounds()
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        g = self.geom
        return (round(g.col_x(left), 3), round(g.yt - bottom * g.y_pitch, 3),
                round(g.col_x(right), 3), round(g.yt - top * g.y_pitch, 3))

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
def blank_gap_moves(x0: float, x1: float, burn_feed: int, fast_feed: int, guard: float = 2.0,
                    min_fast: float = 2.0, accel: float = ACCEL) -> list:
    """Laser-off moves across one blank gap inside a scan row: [(x_end, feed), ...].
    Keeps `guard` mm at the engraving feed on each side (the user's slow-down / speed-up zones), and only speeds up
    the middle if it is at least `min_fast` long. The fast feed is capped so the head can reach it and slow back
    down within the middle at `accel` (Grbl also brakes before a slower block), so no mark is entered too fast.
    Gaps too short for any of this stay one move at the engraving feed."""
    d = 1.0 if x1 >= x0 else -1.0
    # Work from the coordinates exactly as the G-code will carry them (0.001 mm), so the verifier measures the same
    # fast length the speed was planned for.
    xa, xb = round(x0 + d * guard, 3), round(x1 - d * guard, 3)
    mid = (xb - xa) * d
    if fast_feed <= burn_feed or mid <= 0 or mid < min_fast:
        return [(x1, burn_feed)]
    vb = burn_feed / 60.0
    reach = math.sqrt(vb * vb + accel * mid)               # accelerate over half the middle, brake over the other half
    f = int(min(fast_feed, math.floor(reach * 60.0) - 1))   # the highest whole feed it can really reach and brake from
    if f < burn_feed * 1.25:                               # not worth a speed change
        return [(x1, burn_feed)]
    out = [(xa, burn_feed)] if guard > 0 else []
    out += [(xb, f)]
    out += [(x1, burn_feed)] if guard > 0 else []
    return out


def raster_commands(cells: np.ndarray, order, geom: Geometry, feed: int, row_feed: int, runup: float,
                    row_feeds=None, accel: float = ACCEL, *, bidirectional: bool = True,
                    fast_blank_gaps: bool = False, blank_guard: float = 2.0, blank_min_fast: float = 2.0,
                    blank_feed: int | None = None) -> list:
    cmds = []
    flip = False
    for r in order if order is not None else range(cells.shape[0]):
        row = cells[r]
        nz = np.flatnonzero(row)
        if not len(nz):
            continue
        f = int(row_feeds[r]) if row_feeds is not None else int(feed)
        ru = max(runup, auto_runup(f, accel, minimum=min(1.0, runup)))   # ladders ask for less than 1 mm when slow
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
        previous = start
        for e, s in zip(ends, pw):
            if fast_blank_gaps and s == 0:
                cmds += [f"G1 X{fmt(xe)} Y{y} F{fe} S0"
                         for xe, fe in blank_gap_moves(previous, e, f, blank_feed or row_feed, blank_guard,
                                                       blank_min_fast, accel)]
            else:
                cmds.append(f"G1 X{fmt(e)} Y{y} F{f} S{s}")
            previous = e
        cmds += [f"G1 X{fmt(ends[-1] + d * ru)} Y{y} F{f} S0", "M5 S0"]
        flip = not flip if bidirectional else False
    return cmds


def feature_commands(cells: np.ndarray, labels: np.ndarray, geom: Geometry, feed: int, hop_feed: int,
                     runup: float, start=(0.0, 0.0), *, bidirectional: bool = True) -> list:
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
            flip = not flip if bidirectional else False
        pos = cen[i]
    return cmds


def dwell_pass(geom: Geometry, allowed: np.ndarray, spots, key: str = "D", title: str = "Burn in place",
               explain: str = "Laser on, standing still, only at the chosen spots", travel_feed: int = 3000,
               cool_s: float = 0.0) -> PassPlan:
    """A burn-in-place pass: the head travels with the laser off to each spot, then burns there standing still
    (M3 + G4) for its own time, then the laser goes off. spots: dicts with x, y (mm from job zero), power (%) or s,
    and seconds. Each spot snaps to the nearest dot centre (at most half a dot away)."""
    out = []
    cells = np.zeros((geom.rows, geom.cols), np.int16)
    for sp in spots:
        s = int(sp["s"]) if "s" in sp else int(round(float(sp["power"]) * 10))
        sec = float(sp["seconds"])
        if not 0 < s <= 1000:
            raise ValueError(f"Spot power S{s} must be 1-1000.")
        if not 0 < sec <= DWELL_MAX_S:
            raise ValueError(f"Spot time {sec:g} s must be more than 0 and at most {DWELL_MAX_S:g} s.")
        c = int(math.floor((float(sp["x"]) - geom.x0) / geom.x_pitch))
        r = int(math.floor((geom.yt - float(sp["y"])) / geom.y_pitch))
        if not (0 <= r < geom.rows and 0 <= c < geom.cols) or not allowed[r, c]:
            raise ValueError(f"Spot at X{sp['x']} Y{sp['y']} is outside the usable area.")
        x, y = round(geom.col_x(c + 0.5), 3), round(geom.row_y(r), 3)
        near = next((o for o in out if math.hypot(o["x"] - x, o["y"] - y) < SPOT_GAP_MIN - 1e-9), None)
        if near is not None:
            raise ValueError(f"Spots at X{sp['x']} Y{sp['y']} and X{near['x']} Y{near['y']} are closer than "
                             f"{SPOT_GAP_MIN:g} mm: each spot must be its own burn.")
        cells[r, c] = s
        out.append(dict(x=x, y=y, s=s, seconds=sec))
    if not 0 <= cool_s <= COOL_MAX_S:
        raise ValueError(f"Cool-down {cool_s:g} s must be 0-{COOL_MAX_S:g} s.")
    return PassPlan(key, title, explain, "dwell", cells, None, int(travel_feed), spots=out, cool_s=float(cool_s))


def dwell_commands(spots, travel_feed: int, cool_s: float = 0.0) -> list:
    """Per spot: laser off, travel there (laser off), on for the spot's time standing still, off."""
    cmds = [] if spots else ["M5 S0"]
    for k, sp in enumerate(spots):
        cmds += ["M5 S0", f"G1 X{fmt(sp['x'])} Y{fmt(sp['y'])} F{int(travel_feed)} S0", f"M3 S{int(sp['s'])}",
                 f"G4 P{float(sp['seconds']):g}", "M5 S0"]
        if cool_s > 0 and k < len(spots) - 1:
            cmds.append(f"G4 P{float(cool_s):g}")
    return cmds


def crawl_timing(step: float, v_avg: float, min_feed: int = CRAWL_MIN_FEED, quantum: float = CRAWL_QUANTUM_S):
    """Move feed f and pause t per step so the average along the line is v_avg (mm/min), while every move runs at
    or above min_feed (the controller follows feeds above its floor) and every pause is a whole number of the
    firmware's dwell steps (Grbl 1.1h rounds G4 up to 50 ms). Picks the slowest move that works, so the burn is as
    even as possible. Returns (f, t, planned average)."""
    if not CRAWL_MIN_AVG <= v_avg <= min_feed:
        raise ValueError(f"Crawl average {v_avg:g} mm/min must be {CRAWL_MIN_AVG:g}-{min_feed} mm/min "
                         "(faster lines don't need crawling).")
    if not 0.005 <= step <= 1.0:
        raise ValueError(f"Crawl step {step:g} mm must be 0.005-1 mm.")
    for k in range(1, int(round(CRAWL_MAX_PAUSE_S / quantum)) + 1):
        t = round(k * quantum, 3)
        per_mm = 1.0 / v_avg - t / (60.0 * step)            # minutes per mm left for moving
        if per_mm <= 0:
            break
        f = int(round(1.0 / per_mm))
        if f < min_feed:
            continue
        if f > MAX_FEED:
            break
        v = step / (step / f + t / 60.0)
        if abs(v - v_avg) / v_avg <= 0.01:
            return f, t, v
    raise ValueError(f"A {step:g} mm step can't average {v_avg:g} mm/min with moves at {min_feed} mm/min or more and "
                     f"pauses in {quantum * 1000:g} ms steps (up to {CRAWL_MAX_PAUSE_S:g} s). Use a bigger step or a "
                     "lower minimum move speed.")


def crawl_pass(geom: Geometry, allowed: np.ndarray, lines, key: str = "C", title: str = "Crawl lines",
               explain: str = "Laser on along each line only: tiny steps, each followed by a short pause",
               travel_feed: int = 3000) -> PassPlan:
    """Lines burned at an average speed below the controller's floor. Per line: laser-off travel to its start, M3,
    then a tiny left-to-right step (G1 at feed f) and a pause (G4 t) repeated, then laser off. lines: dicts with x0,
    x1, y (mm from job zero), power (%) or s, v_avg (mm/min), step (mm), optional min_feed. y snaps to its row's
    centre and x0 to a dot edge; x1 becomes x0 + a whole number of steps."""
    out = []
    cells = np.zeros((geom.rows, geom.cols), np.int16)
    for ln in lines:
        s = int(ln["s"]) if "s" in ln else int(round(float(ln["power"]) * 10))
        if not 0 < s <= 1000:
            raise ValueError(f"Line power S{s} must be 1-1000.")
        step, v_target = float(ln["step"]), float(ln["v_avg"])
        f, t, v = crawl_timing(step, v_target, int(ln.get("min_feed", CRAWL_MIN_FEED)))
        r = int(math.floor((geom.yt - float(ln["y"])) / geom.y_pitch))
        c0 = int(round((float(ln["x0"]) - geom.x0) / geom.x_pitch))
        x0 = round(geom.col_x(c0), 3)
        n = int(round((float(ln["x1"]) - float(ln["x0"])) / step))
        if n < 1:
            raise ValueError("A crawl line must run left to right, at least one step long.")
        x1 = round(x0 + n * step, 3)
        c1 = int(math.ceil((x1 - geom.x0) / geom.x_pitch - 1e-6))
        if not (0 <= r < geom.rows and 0 <= c0 and c1 <= geom.cols) or not allowed[r, c0:c1].all():
            raise ValueError(f"Line at Y{ln['y']} from X{ln['x0']} to X{ln['x1']} leaves the usable area.")
        if cells[r, c0:c1].any():
            raise ValueError(f"Line at Y{ln['y']} overlaps another crawl line.")
        cells[r, c0:c1] = s
        out.append(dict(x0=x0, x1=x1, y=round(geom.row_y(r), 3), s=s, step=step, steps=n, feed=f, pause=t,
                        v_avg=round(v, 4), v_target=v_target))
    return PassPlan(key, title, explain, "crawl", cells, None, int(travel_feed), lines=out)


def crawl_commands(lines, travel_feed: int) -> list:
    """Per line: laser off, travel to its start (laser off), M3, then step + pause repeated, then laser off."""
    cmds = [] if lines else ["M5 S0"]
    for ln in lines:
        y = fmt(ln["y"])
        cmds += ["M5 S0", f"G1 X{fmt(ln['x0'])} Y{y} F{int(travel_feed)} S0", f"M3 S{int(ln['s'])}"]
        for k in range(1, ln["steps"] + 1):
            cmds += [f"G1 X{fmt(ln['x0'] + k * ln['step'])} Y{y} F{int(ln['feed'])} S{int(ln['s'])}",
                     f"G4 P{float(ln['pause']):g}"]
        cmds.append("M5 S0")
    return cmds


def estimate_seconds(cmds, accel: float = ACCEL, per_command: float = 0.003) -> float:
    x = y = 0.0
    t = 0.0
    for c in cmds:
        if c.startswith("G4 P"):
            t += float(c[4:])
            continue
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
    if m.scan_direction not in ("alternating", "forward"):
        raise ValueError("Scan direction must be alternating or forward.")
    bidirectional = m.scan_direction == "alternating"
    pos = start
    for p in job.passes:
        if p.kind == "dwell":
            p.commands = dwell_commands(p.spots or [], p.feed, p.cool_s)
        elif p.kind == "crawl":
            p.commands = crawl_commands(p.lines or [], p.feed)
        elif p.kind == "features":
            p.commands = feature_commands(p.cells, job.labels, job.geom, p.feed, m.hop_feed, m.feature_runup, pos,
                                          bidirectional=bidirectional)
        else:
            p.commands = raster_commands(p.cells, p.order, job.geom, p.feed, m.row_feed, m.runup, p.row_feeds,
                                         bidirectional=bidirectional, fast_blank_gaps=m.fast_blank_gaps,
                                         blank_guard=float(m.blank_guard_mm), blank_min_fast=float(m.blank_min_fast_mm),
                                         blank_feed=int(m.blank_feed))
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
    def picture_grid(geom):
        return imaging.to_grid(
            picture, geom.cols, geom.rows, geom.crop,
            autolevel=look.get("autolevel", mat.autolevel), brightness=look.get("brightness", mat.brightness),
            contrast=look.get("contrast", mat.contrast), gamma=look.get("gamma", mat.gamma),
            negative=look.get("negative", mat.negative), sharpen=look.get("sharpen", mat.sharpen),
            black_point=look.get("black_point", mat.black_point), white_point=look.get("white_point", mat.white_point))

    if placement.fit == "marks":
        return build_mark_sized_job(picture.size, mat, placement, picture_grid, name)
    geom = layout(picture.size, placement, mat.pitch)
    gray = picture_grid(geom)
    allowed = allowed_cells(geom, placement.piece)
    return plan_cells(gray, mat, geom, allowed, name, placement.piece)


def build_mark_sized_job(image_size, mat, placement, picture_grid, name):
    """Fit the powered artwork, budgeting resolution on the marks instead of the blank canvas."""
    stock = placement.piece
    ref = layout(image_size, replace(placement, fit="art-exact", art_w=None), mat.pitch)

    def unmasked(g):
        gray = picture_grid(g)
        return plan_cells(gray, mat, g, np.ones(gray.shape, dtype=bool), name, stock)

    reference = unmasked(ref).powered_cell_bounds()
    if reference is None:
        raise ValueError("The selected picture and settings produce no powered artwork to size.")
    left, top, right, bottom = reference
    iw, ih = image_size
    px, py = iw / ref.cols, ih / ref.rows
    # Sample again from the original, with a two-cell border around the reference marks.
    crop = (max(0, left - 2) * px, max(0, top - 2) * py,
            min(ref.cols, right + 2) * px, min(ref.rows, bottom + 2) * py)
    crop_w, crop_h = crop[2] - crop[0], crop[3] - crop[1]
    ux0, uy0, ux1, uy1 = ref.usable_rect
    uw, uh = ux1 - ux0, uy1 - uy0
    requested = placement.art_w or uw
    if min(uw, uh, requested) <= 0 or not math.isfinite(requested):
        raise ValueError("Enter a positive engraved width on a piece with a usable face.")
    provisional = min(requested / ((right - left) * px), uw / ((right - left) * px),
                      uh / ((bottom - top) * py))
    cols = max(1, round(crop_w * provisional / mat.pitch))
    rows = max(1, round(crop_h * provisional / mat.pitch))
    geom = replace(ref, cols=cols, rows=rows, crop=crop, cell_w=crop_w / cols, cell_h=crop_h / rows)
    job = unmasked(geom)
    bounds = job.powered_cell_bounds()
    if bounds is None:
        raise ValueError("The chosen size and processing leave no powered artwork.")
    left, top, right, bottom = bounds
    mark_w = (right - left) * geom.x_pitch
    mark_h = (bottom - top) * geom.y_pitch
    scale = min(requested / mark_w, uw / mark_w, uh / mark_h)
    limit = "usable face"
    centre_x, centre_y = (ux0 + ux1) / 2 + placement.dx, (uy0 + uy1) / 2 + placement.dy
    if stock.get("shape") == "circle":
        # Cap the uniform scale at the round rim before clipping. This keeps
        # the original powered shape when part of it is wider on a diagonal.
        px0, py0, px1, py1 = ref.piece_rect
        radius = (px1 - px0) / 2 - stock.get("margins", (0,))[0]
        dx, dy = centre_x - (px0 + px1) / 2, centre_y - (py0 + py1) / 2
        room = radius * radius - dx * dx - dy * dy
        if radius > 0 and room > 0:
            occupied = np.logical_or.reduce([p.cells > 0 for p in job.passes])
            rr, cc = np.nonzero(occupied)
            x = crop[0] - iw / 2 + (cc + 0.5) * geom.x_pitch
            y = ih / 2 - crop[1] - (rr + 0.5) * geom.y_pitch
            radii_sq = x*x + y*y
            dot = dx*x + dy*y
            moving = radii_sq > 0
            if np.any(moving):
                edge = (np.sqrt(dot[moving]**2 + radii_sq[moving]*room) - dot[moving]) / radii_sq[moving]
                rim_scale = float(edge.min()) * (1 - 1e-10)
                if rim_scale < scale:
                    scale = rim_scale
                    limit = "round usable face"
    # The source's centre stays over the same point on the stock, even with asymmetric padding.
    geom = replace(geom, x0=centre_x + (crop[0] - iw / 2) * scale,
                   yt=centre_y - (crop[1] - ih / 2) * scale,
                   cell_w=geom.x_pitch * scale, cell_h=geom.y_pitch * scale)
    job.geom = geom
    job.allowed = allowed_cells(geom, stock)
    clipped = False
    for p in job.passes:
        clipped |= bool(p.cells[~job.allowed].any())
        p.cells = np.where(job.allowed, p.cells, 0)
    if job.levels is not None:
        job.levels[~job.allowed] = 0
    if clipped:
        job.sizing_note = "The rim, outline, or no-burn zones clip some marks at this size and placement."
    if scale * mark_w + 1e-8 < requested:
        job.sizing_note = f"The {limit} limits the requested engraved width. " + job.sizing_note
        job.sizing_note = job.sizing_note.strip()
    return job


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
