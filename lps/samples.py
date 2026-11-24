"""Sample photos for presets: test charts, test results and finished pieces from the project (built in, see
tools/make_samples.py), plus photos the user adds to any preset in the app."""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

from .presets import BUILTIN, DATA_DIR

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "samples"
USER_DIR = DATA_DIR / "samples"
MAX_SIDE = 1400
KINDS = {  # kind: (label, background, text colour)
    "chart": ("Test chart", "#dbeafe", "#1e40af"),
    "test": ("Test result", "#fef3c7", "#92400e"),
    "source": ("Original art", "#e5e7eb", "#374151"),
    "result": ("Finished piece", "#dcfce7", "#166534"),
    "lesson": ("What went wrong", "#fee2e2", "#991b1b"),
}


@dataclass
class Sample:
    path: Path
    kind: str
    title: str
    caption: str
    date: str = ""
    source: str = ""
    user: bool = False
    owner: str = ""
    evidence: dict = field(default_factory=dict)

    @property
    def kind_label(self) -> str:
        return KINDS.get(self.kind, KINDS["test"])[0]


_index = None


def builtin_index() -> dict:
    global _index
    if _index is None:
        try:
            _index = json.loads((ASSETS / "index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _index = dict(samples={}, sets={})
    return _index


def _builtin(key: str) -> tuple:
    idx = builtin_index()
    s = idx.get("sets", {}).get(key)
    if not s:
        return [], ""
    out = []
    for sid in s.get("items", []):
        d = idx.get("samples", {}).get(sid)
        if d and (ASSETS / d["file"]).exists():
            out.append(Sample(ASSETS / d["file"], d["kind"], d["title"], d["caption"], d.get("date", ""),
                              d.get("source", ""), evidence=d.get("evidence", {})))
    return out, s.get("note", "")


def _user_list(key: str) -> Path:
    return USER_DIR / key / "photos.json"


def user_samples(key: str) -> list:
    p = _user_list(key)
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for d in items:
        f = p.parent / d.get("file", "")
        if d.get("file") and f.exists():
            out.append(Sample(f, d.get("kind", "test"), d.get("title", f.stem), d.get("caption", ""),
                              d.get("date", ""), d.get("source", ""), True, key, d.get("evidence", {})))
    return out


def for_material(mat) -> tuple:
    """(photos, note) for a preset: the built-in ones (its own, or those of the preset it was saved from), then
    the user's own photos."""
    items, note = _builtin(mat.key)
    based_on = getattr(mat, "based_on", "")
    parent = next((m for m in BUILTIN if m.key == based_on), None)
    if not items and parent is not None and parent.look == mat.look:
        items, _ = _builtin(based_on)
        if items:
            note = f"Photos from '{parent.name}', the preset this one was saved from."
    return items + user_samples(mat.key), note


def add_user_photo(key: str, src, title: str, kind: str = "test", caption: str = "") -> Sample:
    """Copy a (smaller) JPEG of the photo into the user's samples folder for this preset."""
    from .imaging import load_color
    folder = USER_DIR / key
    folder.mkdir(parents=True, exist_ok=True)
    im = load_color(src)
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", title).strip().replace(" ", "-")[:40] or "photo"
    dest = folder / f"{stem}.jpg"
    n = 2
    while dest.exists():
        dest = folder / f"{stem}-{n}.jpg"
        n += 1
    im.save(dest, quality=88, optimize=True)
    p = _user_list(key)
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    items.append(dict(file=dest.name, kind=kind if kind in KINDS else "test", title=title, caption=caption,
                      date=dt.date.today().isoformat(), source=str(src)))
    p.write_text(json.dumps(items, indent=1), encoding="utf-8")
    return Sample(dest, kind, title, caption, items[-1]["date"], str(src), True, key)


EVIDENCE_STATES = ("Not recorded", "Proposed", "Prepared - not run", "Operator report", "Physical test", "Repeated physical tests")
EVIDENCE_GROUPS = {
    "Evidence": (("state", "Evidence status"), ("basis", "Evidence / source record"), ("job", "Saved job / source file"),
                 ("result", "Observed result"), ("limitations", "Unknowns / limits / cleanup")),
    "Surface": (("machine", "Machine / lens / controller profile"), ("substrate", "Actual substrate / supplier"), ("surface", "Sanding / coating / preparation"),
                ("focus", "Focus / spacer / work height")),
    "Settings": (("power_pct", "Power (%) / controller scale"), ("commanded_feed", "Commanded feed (mm/min)"),
                 ("motion_evidence", "Measured / inferred speed and method"), ("row_pitch", "Raster row pitch (mm), or N/A"),
                 ("mode", "M3 / M4 and drawing style"), ("passes", "Pass count / order"), ("dwell", "Stationary dwell (seconds)")),
}


def evidence_state(sample):
    value = sample.evidence.get("state", "Not recorded")
    return value if value in EVIDENCE_STATES else "Not recorded"


def update_user_evidence(sample: Sample, values: dict) -> None:
    """Update the existing photo record, retaining caption, source and unrelated fields."""
    if not sample.user:
        raise ValueError("Built-in test records are maintained with the app's source evidence.")
    if values.get("state", "Not recorded") not in EVIDENCE_STATES:
        raise ValueError("Choose a listed evidence status.")
    keys = {key for group in EVIDENCE_GROUPS.values() for key, _ in group}
    if any(key not in keys or not isinstance(value, str) for key, value in values.items()):
        raise ValueError("Test-record fields must be text from the listed fields.")
    p = _user_list(sample.owner)
    items = json.loads(p.read_text(encoding="utf-8"))
    item = next((d for d in items if d.get("file") == sample.path.name), None)
    if item is None:
        raise ValueError("Photo record no longer exists. Reopen the photo list.")
    updated = dict(item.get("evidence", {}), **values)
    item["evidence"] = updated
    from .jobs import write_json
    write_json(p, items)
    sample.evidence = updated


def remove_user_photo(sample: Sample) -> None:
    if not sample.user:
        return
    p = _user_list(sample.owner)
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    p.write_text(json.dumps([d for d in items if d.get("file") != sample.path.name], indent=1), encoding="utf-8")
    try:
        sample.path.unlink()
    except OSError:
        pass


_thumbs = {}


def thumbnail(path: Path, box: tuple) -> Image.Image:
    """Small RGB copy that fits in `box`, cached."""
    path = Path(path)
    key = (str(path), tuple(box), path.stat().st_mtime)
    if key not in _thumbs:
        im = Image.open(path)
        im.draft("RGB", (box[0] * 2, box[1] * 2))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail(box, Image.Resampling.LANCZOS)
        _thumbs[key] = im
    return _thumbs[key]
