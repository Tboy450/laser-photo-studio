"""Picture -> burn-grid helpers (Pillow + NumPy only).

The wood steps follow outputs/north-pole-mural/RECIPE.md and work/make_christmas_plank.py:
tone levels with the lightest tones left bare, white gaps widened one 0.1 mm row, 4-neighbour erosion for
shrinking layers, thin-feature detection by connected components, and Zhang-Suen centerlines.
"""
from __future__ import annotations

import os
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

PICTURE_TYPES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".heic", ".heif")


def _wic_to_png(path: Path) -> Path:
    """Decode formats Pillow can't read (HEIC phone photos) with Windows' own codecs."""
    out = Path(tempfile.gettempdir()) / f"lps-{os.getpid()}-{abs(hash(str(path)))}.png"
    src = str(path).replace("'", "''")
    dst = str(out).replace("'", "''")
    script = (
        "Add-Type -AssemblyName PresentationCore;"
        f"$i=[IO.File]::OpenRead('{src}');"
        "try{$d=[Windows.Media.Imaging.BitmapDecoder]::Create($i,"
        "[Windows.Media.Imaging.BitmapCreateOptions]::PreservePixelFormat,"
        "[Windows.Media.Imaging.BitmapCacheOption]::OnLoad);"
        "$e=[Windows.Media.Imaging.PngBitmapEncoder]::new();$e.Frames.Add($d.Frames[0]);"
        f"$o=[IO.File]::Create('{dst}');try{{$e.Save($o)}}finally{{$o.Dispose()}}}}finally{{$i.Dispose()}}"
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   check=True, capture_output=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out


def _open_any(path) -> Image.Image:
    """Open any picture (HEIC via Windows' codecs), turned upright using the phone's EXIF rotation."""
    path = Path(path)
    try:
        im = Image.open(path)
        im.load()
    except Exception:
        if path.suffix.lower() not in (".heic", ".heif"):
            raise
        im = Image.open(_wic_to_png(path))
        im.load()
    return ImageOps.exif_transpose(im)


def _on_white(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return im


def load_picture(path) -> Image.Image:
    """Open any picture as 8-bit grayscale on a white background, honouring the phone's EXIF rotation."""
    return _on_white(_open_any(path)).convert("L")


def load_color(path) -> Image.Image:
    """Open any picture in colour (RGB on white), honouring the phone's EXIF rotation."""
    return _on_white(_open_any(path)).convert("RGB")


def orient(im: Image.Image, rotate: int = 0, mirror: bool = False) -> Image.Image:
    """rotate: clockwise quarter turns (0..3)."""
    rotate %= 4
    if rotate:
        im = im.transpose({1: Image.Transpose.ROTATE_270, 2: Image.Transpose.ROTATE_180,
                           3: Image.Transpose.ROTATE_90}[rotate])
    if mirror:
        im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return im


def tone_lut(brightness: float = 0, contrast: float = 0, gamma: float = 1.0, negative: bool = False):
    """brightness/contrast in -100..100, gamma > 0 (above 1 lightens mid-tones)."""
    v = np.arange(256, dtype=np.float64)
    v = (v - 128.0) * max(0.0, (100.0 + contrast) / 100.0) + 128.0
    v = v + brightness * 1.28
    v = 255.0 * (np.clip(v, 0, 255) / 255.0) ** (1.0 / max(0.05, gamma))
    if negative:
        v = 255.0 - v
    return [int(round(x)) for x in np.clip(v, 0, 255)]


def saved_size_mm(path) -> tuple | None:
    """The real size stored in a picture file (from its DPI), or None. 72 and 96 are just screen defaults."""
    try:
        with Image.open(path) as im:
            dpi, (w, h) = im.info.get("dpi"), im.size
            orientation = im.getexif().get(274, 1)
        # PNG stores integer pixels/metre, so an ordinary 96 DPI tag can decode as 96.012.
        if not dpi or len(dpi) < 2 or not all(math.isfinite(v) and v > 96.1 for v in dpi[:2]):
            return None
        size = round(w / float(dpi[0]) * 25.4, 2), round(h / float(dpi[1]) * 25.4, 2)
        return size[::-1] if orientation in (5, 6, 7, 8) else size
    except Exception:
        return None


def auto_level_points(im: Image.Image, crop=None):
    if crop is not None:
        im = im.crop(tuple(int(round(c)) for c in crop))
    hist = np.asarray(im.convert('L').histogram(), dtype=np.int64)
    cut = int(hist.sum() // 100)
    lo = int(np.searchsorted(hist.cumsum(), cut, side='right'))
    hi = 255 - int(np.searchsorted(hist[::-1].cumsum(), cut, side='right'))
    return (lo, hi) if hi > lo else (0, 255)


def to_grid(im: Image.Image, cols: int, rows: int, crop=None, *, autolevel=False, brightness=0, contrast=0,
            gamma=1.0, negative=False, sharpen=0, black_point=0, white_point=255) -> np.ndarray:
    """Resize the picture to the burn grid (one cell per row/column pitch) and apply the look settings.
    Returns float32 lightness 0 (black) .. 255 (white)."""
    if crop is not None:
        im = im.crop(tuple(int(round(c)) for c in crop))
    if autolevel:
        im = ImageOps.autocontrast(im, cutoff=1)
    if not 0 <= black_point < white_point <= 255:
        raise ValueError('Black point must be below White point (0..255).')
    if (black_point, white_point) != (0, 255):
        scale = 255.0 / (white_point - black_point)
        offset = -black_point * scale
        im = im.point([max(0, min(255, int(x * scale + offset))) for x in range(256)])
    im = im.point(tone_lut(brightness, contrast, gamma, False))
    im = im.resize((max(1, cols), max(1, rows)), Image.Resampling.LANCZOS)
    if sharpen > 0:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(sharpen), threshold=2))
    a = np.asarray(im, dtype=np.float32)
    return 255.0 - a if negative else a


def tone_levels(a: np.ndarray, cuts=(110, 78, 48), widen_gaps: bool = True) -> np.ndarray:
    """Lightness -> 0 bare, 1 light, 2 mid, 3 dark. The lightest tones stay bare wood. Widening: every cell to
    the right of or below a bare cell is cleared, so each white gap grows one 0.1 mm row on one side and survives
    the 0.1-0.2 mm char spread."""
    c0, c1, c2 = cuts
    lev = np.select([a >= c0, a >= c1, a >= c2], [0, 1, 2], 3).astype(np.uint8)
    if widen_gaps:
        bare = lev == 0
        clear = np.zeros_like(bare)
        clear[:, 1:] |= bare[:, :-1]
        clear[1:] |= bare[:-1]
        lev[clear & ~bare] = 0
    return lev


def fs_dots(a: np.ndarray) -> np.ndarray:
    """Floyd-Steinberg 1-bit dots (Pillow's), True = burn (dark)."""
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L")
    return ~np.asarray(im.convert("1", dither=Image.Dither.FLOYDSTEINBERG), dtype=bool)


def erode(m: np.ndarray) -> np.ndarray:
    """4-neighbour erosion by one cell (0.1 mm). The picture border doesn't erode (as in the proven scripts)."""
    e = m.copy()
    e[1:] &= m[:-1]
    e[:-1] &= m[1:]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return e


def erode_n(m: np.ndarray, n: int) -> np.ndarray:
    for _ in range(max(0, n)):
        m = erode(m)
    return m


def label_components(mask: np.ndarray):
    """4-connected component labels (1..n, 0 = background), vectorised: row runs are linked to the runs they
    overlap in the row above, then merged by min-label hooking with pointer jumping."""
    mask = np.asarray(mask, dtype=bool)
    H, W = mask.shape
    lab = np.zeros(H * W, np.int32)
    if not mask.any():
        return lab.reshape(H, W), 0
    padded = np.zeros((H, W + 2), np.int8)
    padded[:, 1:-1] = mask
    d = np.diff(padded, axis=1)
    rs, cs = np.nonzero(d == 1)
    _, ce = np.nonzero(d == -1)
    n = len(rs)
    stride = W + 2
    gs = rs.astype(np.int64) * stride + cs
    ge = rs.astype(np.int64) * stride + ce
    lo = np.searchsorted(ge, gs - stride, side="right")
    hi = np.searchsorted(gs, ge - stride, side="left")
    cnt = np.maximum(hi - lo, 0)
    parent = np.arange(n)
    if cnt.sum():
        u = np.repeat(np.arange(n), cnt)
        v = np.repeat(lo, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
        while True:
            pu, pv = parent[u], parent[v]
            diff = pu != pv
            if not diff.any():
                break
            np.minimum.at(parent, np.maximum(pu[diff], pv[diff]), np.minimum(pu[diff], pv[diff]))
            while True:
                pp = parent[parent]
                if np.array_equal(pp, parent):
                    break
                parent = pp
    _, comp = np.unique(parent, return_inverse=True)
    comp = comp.astype(np.int32) + 1
    lens = ce - cs
    idx = np.repeat(rs * W + cs - (np.cumsum(lens) - lens), lens) + np.arange(lens.sum())
    lab[idx] = np.repeat(comp, lens)
    return lab.reshape(H, W), int(comp.max())


def thin_features(mask: np.ndarray):
    """Features too thin for interlaced layers (lettering, figures, fine lines): connected shapes whose cells
    mostly vanish after one 0.1 mm erosion. Returns (thin mask, labels)."""
    lab, n = label_components(mask)
    if n == 0:
        return np.zeros_like(mask, dtype=bool), lab
    size = np.bincount(lab.ravel(), minlength=n + 1)
    core = np.bincount(lab.ravel(), weights=erode(mask).ravel(), minlength=n + 1)
    thin = (size > 0) & (core < 0.5 * size)
    thin[0] = False
    return thin[lab], lab


def skeleton(mask: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning to 1-cell centerlines (char spreads ~0.1 mm per side, so a centerline grows back to
    about the feature's true width instead of smearing)."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return mask.copy()
    rr, cc = np.nonzero(mask)
    r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
    mm = np.pad(mask[r0:r1, c0:c1].astype(np.uint8), 1)
    order = ((1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1))
    while True:
        changed = False
        for step in (0, 1):
            nb = [np.roll(np.roll(mm, dy, 0), dx, 1) for dy, dx in order]
            p2, p3, p4, p5, p6, p7, p8, p9 = nb
            b = sum(x.astype(np.int16) for x in nb)
            a = sum(((nb[i] == 0) & (nb[(i + 1) % 8] == 1)).astype(np.int16) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            kill = (mm == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if kill.any():
                mm[kill] = 0
                changed = True
        if not changed:
            break
    out = np.zeros_like(mask)
    out[r0:r1, c0:c1] = mm[1:-1, 1:-1].astype(bool)
    return out


def text_mask(text: str, height_cells: int) -> np.ndarray:
    """Render a short label (test grids) as a bool mask, about `height_cells` tall."""
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arialbd.ttf", max(6, int(height_cells * 1.25)))
    except OSError:
        font = ImageFont.load_default()
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0] + 2, box[3] - box[1] + 2
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((1 - box[0], 1 - box[1]), text, fill=255, font=font)
    return np.asarray(im) > 127
