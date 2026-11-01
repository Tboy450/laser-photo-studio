"""Build the sample photos shown under 'About this setting' (step 2).

Copies trimmed, upright, smaller versions of the project's test charts, test photos and finished pieces into
assets/samples/ and writes assets/samples/index.json (captions + which presets show which photos, in order).
Run again after adding photos to the lists below:   python tools/make_samples.py
Sources that have gone missing keep their existing copy."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from lps.imaging import load_color  # noqa: E402

OUTPUTS = APP.parents[1] / "outputs"
OUT = APP / "assets" / "samples"
MAX_SIDE = 1400
Image.MAX_IMAGE_PIXELS = None

# id: source (relative to the project's outputs folder, or absolute), kind, date, title, caption,
#     optional crop (left, top, right, bottom as fractions) and rotate (quarter turns anticlockwise).
SAMPLES = {
    "pine-ladder": dict(
        src="goku-pine-plaque-7x6/pine-ladder-results-reference.png", kind="test", date="2026-10-28",
        title="Ladder test on pine",
        caption="Six 3 mm swatches at 3000 mm/min, from 2% up to 40% (labelled on the photo). 2-10% left no mark, "
                "20% barely, 30% light brown, 40% the darkest - and the only one where a lone thin line showed."),
    "pine-grid-chart": dict(
        src="goku-pine-plaque-7x6/box7-power-speed-grid-reference.png", kind="chart", date="2026-10-29",
        title="Power x speed chart",
        caption="The plan for the grid test: 25, 30, 35 and 40% across, 3000, 2250 and 1500 mm/min down. Each cell "
                "is a small swatch plus a short line; the names G11-G34 match the result photo."),
    "pine-grid": dict(
        src="goku-pine-plaque-7x6/latest-grid-result-numbered.png", kind="test", date="2026-10-29",
        title="Power x speed result",
        caption="Slower rows mark fuller and darker: at 3000 mm/min the marks are light and incomplete, at 1500 "
                "every power fills in and short lines show clearly. Neighbouring powers look alike - power alone "
                "gives little shading on pine, which is why the layered style was developed."),
    "dragon-chart": dict(
        src="goku-pine-plaque-7x6/backside-mural/dragon-retest-52mm/twelve-test-reference.png", kind="chart",
        date="2026-10-30", title="12 ways to burn one dragon",
        caption="After the mural's dragon filled in, the same 52 mm dragon was prepared 12 ways: pauses, row order, "
                "separated tiles, a lighter tone map, no outlines over darks, interlaced layers and shrinking "
                "layers. The thumbnails show what each one burns."),
    "dragon-compare": dict(
        src="goku-pine-plaque-7x6/backside-mural/dragon-retest-52mm/comparison-so-far.png", kind="test",
        date="2026-10-30", title="Dragon tests side by side",
        caption="Burned on pine. The one-pass versions (tests 6 and 7) come out dark and heavy; the interlaced "
                "layers (tests 4 and 10) build the tone gradually and keep more detail. You liked the layered ones "
                "best."),
    "dragon-source": dict(
        src="goku-pine-plaque-7x6/backside-mural/dragon-retest-52mm/dragon-original-size.png", kind="source",
        date="2026-10-29", title="Original dragon art",
        caption="The 52 mm square cut from the mural art. Every test used it unchanged, so only the burning method "
                "changed."),
    "dragon-test12": dict(
        src="goku-pine-plaque-7x6/backside-mural/dragon-retest-52mm/photos/timelapse-test12/03-after-layer3.jpg",
        kind="test", date="2026-10-30", crop=(0.23, 0.26, 0.66, 0.84),
        title="Winner: shrinking layers",
        caption="Test 12 after 3 layers - 'pretty freaking good'. Each layer burns every 5th row and the same "
                "shapes 0.1 mm smaller, so the insides get darker while the edges stay sharp. This became the pine "
                "recipe. (The strip along the top is an older test.)"),
    "mural-whole": dict(
        src="goku-pine-plaque-7x6/backside-mural/result-20261029/1000047295.jpg", kind="result", date="2026-10-29",
        title="Goku mural (pine backside)",
        caption="Shading at 20-35% / 2250 mm/min, one pass per section, plus outline passes at 40% / 3000 mm/min. "
                "Overall a success; the dragon (top right) lost its detail."),
    "mural-lesson": dict(
        src="goku-pine-plaque-7x6/backside-mural/result-20261029/1000047297.png", kind="lesson",
        date="2026-10-29", crop=(0.55, 0.0, 1.0, 0.56),
        title="What went wrong: the dragon",
        caption="All shades in one pass plus 40% outlines on top: the dark areas filled in and the dragon's detail "
                "disappeared. That's why the layered style burns thin interlaced layers and never adds heavy lines "
                "over dark areas."),
    "np-source": dict(
        src="north-pole-mural/operator-design.webp", kind="source", date="2026-10-30",
        title="North Pole art",
        caption="The picture used for the plank. The 'Pine plank - layered photo' preset rebuilds the plank's exact "
                "layer plan from it."),
    "np-l1": dict(
        src="north-pole-mural/photos/timelapse/01-after-L1.jpg", kind="result", date="2026-10-30",
        title="After layer 1",
        caption="Layer 1 burns every 5th row over all tones. Light, but the whole picture already reads: 'this "
                "looks awesome so far'."),
    "np-l2": dict(
        src="north-pole-mural/photos/timelapse/02-after-L2.jpg", kind="result", date="2026-10-30",
        title="After layer 2",
        caption="Layer 2 burns the next rows over the same shapes, 0.1 mm smaller: darker, without blurring the "
                "edges."),
    "np-final": dict(
        src="north-pole-mural/photos/20261031_020709.jpg", kind="result", date="2026-10-31",
        crop=(0.05, 0.0, 0.995, 1.0), title="Finished North Pole plank",
        caption="Layered shading, the lettering pass, snowflakes and the scroll border. 165.8 x 110.5 mm of art on "
                "a 7 x 6 in pine plank."),
    "np-sign": dict(
        src="north-pole-mural/finishing-review/photos/1000047419.jpg", kind="result", date="2026-10-30",
        title="Close-up: sign and trees",
        caption="Sign letters burned as 1-dot centerlines (max 30%) stay readable next to the layered shading. Close "
                "up you can see the fine rows; softening them is on the ideas list."),
    "card-eng-source": dict(
        src="anodized-cards-2026-11-01/engineering-kab-IMPORT.png", kind="source", date="2026-11-01",
        title="Card artwork (laser input)",
        caption="Black-on-white art: black = where the laser fires and makes silver. It's already 'marked as "
                "drawn', so Negative stays off."),
    "card-eng": dict(
        src=r"C:\Users\Heemi\Downloads\Mobile Devices\20261101_050846.heic", kind="result", date="2026-11-01",
        crop=(0.09, 0.0, 0.81, 1.0), rotate=1, title="Engineering card, 4 x 2 in",
        caption="Classic dots, 50% (S500), 2500 mm/min, 10 lines/mm, one pass - converted in LaserGRBL with exactly "
                "these settings, 10 min 37 s. Bright silver on black."),
    "card-heart": dict(
        src="anodized-cards-2026-11-01/recovery/20261101_033016.jpg", kind="result", date="2026-11-01",
        title="Heart card while engraving",
        caption="Same settings on the 2 x 4 in heart card: the script and fine dots come out bright silver. (Taken "
                "during the resumed run after a USB dropout.)"),
    "lid-ladder-chart": dict(
        src="saiyan-can/fullbody-aura-v7/selected-ladder300-preview.png", kind="chart", date="2026-10-27",
        title="Lid line ladder",
        caption="Before the full lid: short strokes at 40, 60 and 80% at 300 mm/min (red, bottom). Orange marks are "
                "earlier tests."),
    "lid-test-marks": dict(
        src="saiyan-can/fullbody-aura-v7/operator-photo-2026-10-27-test-marks.jpg", kind="test", date="2026-10-27",
        title="Line tests on the lid",
        caption="At 300 mm/min: 40% a tad light, 57-60% fine and visible, 80% browning. The brown oval is a slow "
                "95% test that blistered the inside coating. 57% became the line setting."),
    "lid-raster-swatches": dict(
        src="saiyan-can/raster-test-5/photos/left-end-labelled.jpg", kind="test", date="2026-10-28",
        title="Photo-dot swatches on a lid",
        caption="2 mm dot swatches at 2500 mm/min: 50% barely marks, 55% a thin strip, 60% a full light square. "
                "Below about 80% the result changed from spot to spot (focus)."),
    "lid-raster-lesson": dict(
        src="saiyan-can/raster-job-F1-ink-39/photos/print-vs-preview.jpg", kind="lesson", date="2026-10-28",
        title="What went wrong: first lid photo",
        caption="Dense 0.1 mm dots at 100% / 2500 mm/min merged into a frosted silhouette (left) and lost all the "
                "detail of the preview (right). That's why the lid photo preset uses bigger, spaced halftone dots - "
                "and why it needs a test first."),
    "lid-source": dict(
        src="saiyan-can/fullbody-aura-v7/full-job/full-job-preview.png", kind="source", date="2026-10-27",
        title="Goku + Vegeta line art",
        caption="Line art with power tiers at 300 mm/min: aura 60%, characters 57%, lightning 50% (blue). Marks "
                "already tested were skipped (orange)."),
    "lid-gv": dict(
        src="saiyan-can/fullbody-aura-v7/full-job/finished-lid-photo-2026-10-27-lighting.jpg", kind="result",
        date="2026-10-27", title="Goku + Vegeta lid",
        caption="Vector lines at 300 mm/min, about 8 minutes - still the best line work so far. Made with LINE "
                "settings, not this preset's halftone photo style."),
    "lid-kame": dict(
        src="saiyan-can/goku-kamehameha-lid/photos/1000047168.jpg", kind="result", date="2026-10-28",
        title="Kamehameha lid",
        caption="Lines at 45-57%: a tad light, and one side of the 45% border didn't etch fully. 45% has little "
                "margin above the 'too light' point."),
}

SETS = {
    "pine-layers": dict(
        items=["pine-ladder", "pine-grid", "dragon-chart", "dragon-test12", "np-source", "np-final", "np-l1",
               "np-l2", "np-sign", "pine-grid-chart", "dragon-compare", "dragon-source", "mural-lesson"],
        note="The ladder and grid tests, the dragon tests that led to this recipe, and the North Pole plank made "
             "with it."),
    "pine-layer-count": dict(
        items=["pine-ladder", "pine-grid", "dragon-chart", "dragon-compare", "dragon-test12", "pine-grid-chart",
               "dragon-source"],
        note="The tests behind the layered recipe. No full piece has been burned with this exact variation yet; "
             "the North Pole plank used the plank recipe."),
    "pine-lettering": dict(
        items=["np-sign", "np-final", "np-source", "pine-ladder", "pine-grid"],
        note="The North Pole sign lettering was burned with this setting."),
    "pine-sketch": dict(
        items=["pine-ladder", "pine-grid", "pine-grid-chart", "mural-whole", "mural-lesson"],
        note="Outlines at 40% / 3000 mm/min were the line passes on the Goku mural."),
    "anodized-dots": dict(
        items=["card-eng-source", "card-eng", "card-heart"],
        note="No ladder test on anodized yet: these settings come from the card jobs. Try a spare card or a test "
             "grid before changing them."),
    "anodized-crisp": dict(
        items=["card-eng", "card-heart"],
        note="These show the proven classic dots at the same power and speed. Crisp (Stucki) dots haven't been "
             "burned yet."),
    "lid-halftone": dict(
        items=["lid-raster-swatches", "lid-raster-lesson", "lid-ladder-chart", "lid-test-marks", "lid-source",
               "lid-gv", "lid-kame"],
        note="Photo halftones on lids are untested. These are the lid tests and the line-art lids (made with LINE "
             "settings)."),
}


def build_one(sid: str, spec: dict) -> str | None:
    src = Path(spec["src"])
    if not src.is_absolute():
        src = OUTPUTS / src
    old = [OUT / f"{sid}{e}" for e in (".png", ".jpg") if (OUT / f"{sid}{e}").exists()]
    if not src.exists():
        if old:
            print(f"  {sid}: source missing, keeping the existing copy")
            return old[0].name
        print(f"  {sid}: SKIPPED, source missing ({src})")
        return None
    im = load_color(src)
    if spec.get("crop"):
        l, t, r, b = spec["crop"]
        im = im.crop((round(l * im.width), round(t * im.height), round(r * im.width), round(b * im.height)))
    for _ in range(spec.get("rotate", 0) % 4):
        im = im.transpose(Image.Transpose.ROTATE_90)
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    for f in old:
        f.unlink()
    # Charts stay PNG (sharp text) unless that gets big; photos are JPEG.
    dest = OUT / f"{sid}.png"
    if spec["kind"] == "chart":
        im.save(dest, optimize=True)
        if dest.stat().st_size > 400_000:
            dest.unlink()
            dest = OUT / f"{sid}.jpg"
            im.save(dest, quality=90, optimize=True, progressive=True)
    else:
        dest = OUT / f"{sid}.jpg"
        im.save(dest, quality=85, optimize=True, progressive=True)
    print(f"  {sid}: {im.width}x{im.height}, {dest.stat().st_size // 1024} KB")
    return dest.name


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    samples = {}
    for sid, spec in SAMPLES.items():
        name = build_one(sid, spec)
        if name:
            samples[sid] = dict(file=name, kind=spec["kind"], title=spec["title"], caption=spec["caption"],
                                date=spec["date"], source=str(spec["src"]).replace("\\", "/"))
    sets = {key: dict(items=[i for i in s["items"] if i in samples], note=s.get("note", ""))
            for key, s in SETS.items()}
    unused = sorted(set(samples) - {i for s in sets.values() for i in s["items"]})
    if unused:
        print("  not shown by any preset:", ", ".join(unused))
    keep = {s["file"] for s in samples.values()}
    for f in OUT.iterdir():
        if f.suffix.lower() in (".jpg", ".png") and f.name not in keep:
            f.unlink()
            print(f"  removed old {f.name}")
    index = dict(version=1, built=dt.date.today().isoformat(), samples=samples, sets=sets)
    (OUT / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"{len(samples)} samples for {len(sets)} presets, {total / 1e6:.1f} MB -> {OUT}")


if __name__ == "__main__":
    main()
