"""Preview pictures: what the finished piece should roughly look like, and a colour map of what each pass burns."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .planner import JobPlan
from .presets import LOOKS

PASS_COLOURS = {"L1": (235, 150, 40), "L2": (215, 70, 40), "L3": (130, 20, 20), "L4": (90, 10, 60),
                "L1thin": (40, 100, 230), "LABELS": (40, 100, 230)}


def _blur(a: np.ndarray, radius: float) -> np.ndarray:
    if radius <= 0:
        return a
    im = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius)), np.float64) / 255.0


def appearance(job: JobPlan, passes=None) -> Image.Image:
    """Rough look of the finished burn on the material (char spread blurs wood marks ~0.1-0.2 mm)."""
    g = job.geom
    m = job.material
    base, mark = (np.array(c, np.float64) for c in LOOKS.get(m.look, LOOKS["pine"]))
    chosen = [p for p in job.passes if passes is None or p.key in passes]
    energy = np.zeros((g.rows, g.cols))
    woody = m.look in ("pine", "lightwood", "darkwood", "leather", "cardboard")
    for p in chosen:
        feed = np.full(g.rows, float(p.feed)) if p.row_feeds is None else p.row_feeds.astype(float)
        feed[feed <= 0] = float(p.feed)
        s = p.cells.astype(np.float64)
        if woody:
            energy += (s / 1000.0) * (2250.0 / feed[:, None]) * 2.9
        else:
            ref = max(1.0, float(m.power))
            energy += np.clip(s / ref, 0, 1.2)
    if woody:
        spread = 0.12 / g.pitch
        dark = 1.0 - np.exp(-1.7 * _blur(np.clip(energy, 0, 3) / 3.0, spread) * 3.0)
    else:
        dark = np.clip(_blur(np.clip(energy, 0, 1), 0.35), 0, 1)
    rgb = base[None, None, :] + (mark - base)[None, None, :] * dark[:, :, None]
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def spot_label(sp) -> str:
    return f"{float(sp['seconds']):g}s" + chr(10) + f"{int(sp['s']) / 10:g}%"


def mark_spots(im: Image.Image, job: JobPlan, passes=None) -> Image.Image:
    """Burn-in-place spots are single dots, too small to see: ring each one and label its time and power.
    `im` is a picture at the job's dot resolution (one pixel per cell), as appearance() and burn_map() make."""
    spots = [sp for p in job.passes if p.kind == "dwell" and (passes is None or p.key in passes) for sp in p.spots or []]
    if not spots:
        return im
    g = job.geom
    out = im.convert("RGB").resize((im.width * 4, im.height * 4), Image.Resampling.NEAREST)   # room for labels
    d = ImageDraw.Draw(out)
    px = 4 / g.pitch                                            # output pixels per mm
    try:
        font = ImageFont.truetype("arial.ttf", max(10, int(0.75 * px)))
    except OSError:
        font = ImageFont.load_default()
    r = max(6, 0.5 * px)
    for sp in spots:
        x, y = (sp["x"] - g.x0) * px, (g.yt - sp["y"]) * px
        d.ellipse((x - r, y - r, x + r, y + r), outline=(200, 0, 0), width=max(2, int(r / 5)))
        d.multiline_text((x, y + r + 2), spot_label(sp), fill=(200, 0, 0), font=font, anchor="ma", align="center")
    return out


def burn_map(job: JobPlan, passes=None) -> Image.Image:
    """White background; each pass in its own colour (later passes drawn on top)."""
    g = job.geom
    out = np.full((g.rows, g.cols, 3), 255, np.uint8)
    if job.allowed is not None:
        out[~job.allowed] = (236, 225, 225)
    for p in job.passes:
        if passes is not None and p.key not in passes:
            continue
        col = PASS_COLOURS.get(p.key, (25, 25, 25))
        out[p.cells > 0] = col
    return Image.fromarray(out, "RGB")


def edge_burn(job: JobPlan, width_mm: float = 0.5) -> float:
    """Share (0-1) of the art box's outer edge that the picture marks as 'burn' (dark after Negative). Near 1 means
    the picture's background burns too, so a logo or sticker comes out as a filled rectangle. Only a plain, even
    edge counts: a photo that runs to its edges has varied tones there and returns 0."""
    if job.gray is None:
        return 0.0
    a = job.gray
    H, W = a.shape
    n = max(1, int(round(width_mm / job.geom.pitch)))
    if H <= 2 * n or W <= 2 * n:
        return 0.0
    ring = np.ones((H, W), bool)
    ring[n:-n, n:-n] = False
    if job.allowed is not None:
        ring &= job.allowed
    if not ring.any() or a[ring].std() > 20:
        return 0.0
    return float((a[ring] < 160).mean())


def source_view(job: JobPlan) -> Image.Image:
    g = job.gray if job.gray is not None else np.full((job.geom.rows, job.geom.cols), 255.0)
    return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "L").convert("RGB")


LASERGRBL_BG = (23, 30, 38)        # LaserGRBL default "CAD Dark" theme: PreviewBackColor
LASERGRBL_LINE = (220, 220, 220)   # PreviewLaserPower; brightness follows S relative to the file's strongest S


def _power_sum(job: JobPlan, passes=None):
    g = job.geom
    acc = np.zeros((g.rows, g.cols))
    smax = 1.0
    for p in job.passes:
        smax = max(smax, float(p.cells.max()) if p.cells.size else 0.0)
    for p in job.passes:
        if passes is None or p.key in passes:
            acc += p.cells / smax
    return np.clip(acc, 0, 1)


def lasergrbl_view(job: JobPlan, passes=None) -> Image.Image:
    """How LaserGRBL's preview draws the .nc: light lines where the laser fires on a dark background.
    It does not invert anything - wood jobs simply look like negatives there."""
    a = _power_sum(job, passes)
    bg, fg = np.array(LASERGRBL_BG, float), np.array(LASERGRBL_LINE, float)
    rgb = bg[None, None, :] + (fg - bg)[None, None, :] * a[:, :, None]
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def laser_input(job: JobPlan) -> Image.Image:
    """Black = the laser fires (darker = more power), white = untouched. Same convention as LaserGRBL's picture
    import and the project's *-IMPORT.png files. 1 pixel = 1 dot."""
    a = _power_sum(job)
    return Image.fromarray((255 - a * 255).astype(np.uint8), "L")
