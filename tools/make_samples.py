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
LASER = Path.home() / "Documents" / "01 Projects" / "Laser & CNC"   # phone photos sorted by day, finished pieces
HOT_WHEELS = LASER / "Hot Wheels (what not to do)"
PHONE_ARCHIVE = Path.home() / "Documents" / "04 Phone Uploads Archive"   # originals from the phone, by month
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
        src=str(LASER / "Phone Photos" / "2026-11-01" / "20261101_050846.heic"), kind="result", date="2026-11-01",
        crop=(0.09, 0.0, 0.81, 1.0), rotate=1, title="Engineering card, 4 x 2 in",
        caption="Classic dots, 50% (S500), 2500 mm/min, 10 lines/mm, one pass - converted in LaserGRBL with exactly "
                "these settings, 10 min 37 s. Bright silver on black."),
    "card-heart": dict(
        src="anodized-cards-2026-11-01/recovery/20261101_033016.jpg", kind="result", date="2026-11-01",
        title="Heart card while engraving",
        caption="Same settings on the 2 x 4 in heart card: the script and fine dots come out bright silver. (Taken "
                "during the resumed run after a USB dropout.)"),
    "card-goku": dict(
        src=str(LASER / "Finished Pieces" / "Goku Kamehameha anodized card 20261101_201127.heic"), kind="result",
        date="2026-11-01", title="Goku 'Kamehameha' card",
        caption="Run from this app: Classic dots, 60% (S600), 2400 mm/min, 0.1 mm rows, one pass, Negative on. "
                "93 x 46.5 mm of art, 17 minutes, no errors. Even, bright silver with the fine hair and beam lines "
                "kept. (Made with your own copy of this preset, 'Black anodized aluminum - photo dots'. The G-code "
                "is 'goku black card.nc' in Documents\\01 Projects\\Laser & CNC.)"),
    "hw-art": dict(
        src=str(HOT_WHEELS / "grok_1793609202885.jpg"), kind="source", date="2026-11-02",
        crop=(0.1, 0.48, 0.93, 0.72), title="Hot Wheels roof art",
        caption="Two racing stripes and the running horse for a yellow Mustang roof, 82.55 x 26.5 mm. The stripes "
                "were meant to be FILLED, with gaps left for the windshield and rear window. Those gaps only work "
                "if the art is lined up with the car's centerline and windows."),
    "hw-setup": dict(
        src=str(HOT_WHEELS / "20261103_005544.heic"), kind="lesson", date="2026-11-03",
        crop=(0.38, 0.25, 0.78, 0.62), title="What went wrong: lining up a car",
        caption="The car under the laser head. A small, curved, painted roof is hard to line up by eye, and "
                "LaserGRBL's Frame only traces the outer box of the job - it doesn't show where the windows or the "
                "car's centerline are. Check those points with the 1% dot before burning."),
    "hw-top": dict(
        src=str(HOT_WHEELS / "20261103_015041.heic"), kind="lesson", date="2026-11-03",
        crop=(0.15, 0.27, 0.85, 0.82), title="What went wrong: outlines, off-centre",
        caption="Only the OUTLINES burned: LaserGRBL's Vectorize turns shapes into their edges, so the stripes "
                "never filled. The stripes sit to one side of the centerline and at an angle, and lines run across "
                "the windshield and rear window. Placement was lost when the job was regenerated, and 'Image "
                "Proportion' was unlocked, so the size could change too."),
    "hw-front": dict(
        src=str(HOT_WHEELS / "20261103_015035.heic"), kind="lesson", date="2026-11-03",
        crop=(0.1, 0.25, 0.72, 0.9), title="What went wrong: horse on the nose",
        caption="The horse landed too far forward, onto the nose of the car, and it is outlines only. Before this, "
                "a raster (picture) import had burned the whole rectangle around the art. The app's own job for "
                "this car used the BLACK ANODIZED preset (wrong material: paint marks dark, not silver) and was "
                "stopped after 22 seconds; the marks on the car came from LaserGRBL."),
    "hw-side": dict(
        src=str(HOT_WHEELS / "20261103_015020.heic"), kind="lesson", date="2026-11-03",
        crop=(0.13, 0.2, 0.65, 0.62), title="What went wrong: side view",
        caption="From the side: thin outline strokes over the bonnet and roof instead of solid stripes. On a painted "
                "car the laser takes the paint off as dark lines; solid stripes need a job that scans rows across "
                "the shape (a fill), not one that traces its edges."),
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

SAMPLES["red-hill-speed-floor"] = {'src': str(Path.home() / "Documents" / "Codex" / "pine salve - red hill" /
        "tests" / "speed-floor-lines-2026-11-13" / "photos" / "speed-floor-20261113_050422.jpg"),
 'source_label': 'speed-floor-lines-2026-11-13/photos/speed-floor-20261113_050422.jpg',
 'kind': 'test',
 'date': '2026-11-13',
 'title': 'Reflective lid: commanded speed versus timing',
 'caption': '14 speed-test stripes on a used reflective lid. The recorded low-feed plateau is '
            'inferred from controller telemetry/timing. Exact coating and wipe state are unknown; '
            'see Test record.',
 'evidence': {'state': 'Physical test',
              'basis': 'Saved job timing/status trace plus operator photo; timing interpretation '
                       'is an inference.',
              'job': '2026-11-13_043712_red-hill-speed-floor-lines; '
                     'tests/speed-floor-lines-2026-11-13/RESULTS-2026-11-13.md',
              'substrate': 'Reflective scrap lid, previously used for a ladder; exact '
                           'alloy/coating/thickness unconfirmed.',
              'surface': 'Wipe state and sanding for this photo not recorded.',
              'focus': '',
              'power_pct': '100%; S1000 scale',
              'commanded_feed': '50, 44, 33; then 22 through 12',
              'motion_evidence': 'Saved timing/position reports suggest ~23.6 mm/min floor for the '
                                 'slow rows; not independent motion measurement. Fast references '
                                 'approximately follow commanded feeds.',
              'row_pitch': '0.10 mm (~254 lines/in); visible stripes are 1 mm apart',
              'mode': 'M4; positive-X raster rows',
              'passes': '14 passes, one stripe per pass; each stripe contains two scan rows',
              'dwell': 'N/A: raster moves',
              'result': 'Operator reported even gold-bronze lines that looked similar. Slow passes '
                        'took about 116.34-116.36 seconds.',
              'limitations': 'Physical test of one used lid, not a repeatable production recipe or '
                             'firmware diagnosis. Wipe state unknown.'}}

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
        items=["card-eng-source", "card-eng", "card-goku", "card-heart", "hw-top", "hw-front", "hw-art",
               "hw-setup", "hw-side"],
        note="No ladder test on anodized yet: these settings come from the card jobs. Try a spare card or a test "
             "grid before changing them. The Hot Wheels photos show a job from this preset made for a painted "
             "car - the wrong material - and what went wrong there."),
    "anodized-crisp": dict(
        items=["card-eng", "card-goku", "card-heart"],
        note="These show the proven classic dots at the same power and speed. Crisp (Stucki) dots haven't been "
             "burned yet."),
    "lid-halftone": dict(
        items=["lid-raster-swatches", "lid-raster-lesson", "lid-ladder-chart", "lid-test-marks", "lid-source",
               "lid-gv", "lid-kame", "hw-top", "hw-front"],
        note="Photo halftones on lids are untested. These are the lid tests and the line-art lids (made with LINE "
             "settings). The Hot Wheels car is painted metal like the lids: see what went wrong there."),
}


SETS["lid-halftone"]["items"].append("red-hill-speed-floor")
SETS["lid-halftone"]["note"] += " The reflective-lid speed test is different stock and is not evidence for this halftone recipe."

def build_one(sid: str, spec: dict) -> str | None:
    src = Path(spec["src"])
    if not src.is_absolute():
        src = OUTPUTS / src
    old = [OUT / f"{sid}{e}" for e in (".png", ".jpg") if (OUT / f"{sid}{e}").exists()]
    if not src.exists() and PHONE_ARCHIVE.exists():   # project folders hold copies; the phone original is kept here
        src = next(PHONE_ARCHIVE.rglob(src.name), src)
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
                                date=spec["date"], source=spec.get("source_label", Path(spec["src"]).name if Path(spec["src"]).is_absolute() else str(spec["src"]).replace("\\", "/")), evidence=spec.get("evidence", {}))
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
