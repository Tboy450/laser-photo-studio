"""Material presets, print styles and workpieces, with plain-English explanations.

Three kinds of settings, always labelled in the app:
  PROVEN  - burned on this Tronxy U20 and judged by the operator (LASER-AUTOMATION-BRIEF.md,
            WOOD-ENGRAVING-REFERENCE.md, LID-ETCHING-REFERENCE.md, outputs/anodized-cards-2026-11-01).
  START   - published starting points for ~20 W diode lasers (Snapmaker's tested 20 W table, community charts).
            Not tested on this machine: this U20 needed about 3x Snapmaker's energy on pine, so run a test grid.
  MINE    - presets you saved yourself (usually from a test grid).
Power is in Grbl S units: S1000 = 100% because the controller is set to $30=1000.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
DATA_DIR = Path(os.environ.get("LASER_PHOTO_STUDIO_DATA_DIR") or LOCAL_APP_DATA / "Laser Photo Studio")

# ---------------------------------------------------------------------------------------------------------------
# Print styles: how a picture becomes laser marks.
STYLES = {
    "layers": dict(
        name="Layered shading (wood)",
        what="Builds tone in thin, shrinking passes on interlaced rows instead of one heavy pass.",
        why="Each row cools before its neighbour burns and later layers stay inside the shapes, so darks don't "
            "turn into scorched blobs and edges stay sharp. This is the dragon test 12 / North Pole recipe.",
        best="Pine and other woods where power shades all burn about the same."),
    "floyd": dict(
        name="Classic dots (Floyd-Steinberg)",
        what="Turns tones into tiny dots; more dots = darker.",
        why="The standard photo dot pattern with good detail. Proven on your black anodized card.",
        best="Anodized aluminum, slate, tile, cardboard, general photos."),
    "jarvis": dict(
        name="Smooth dots (Jarvis)",
        what="Dots spread over a wider area for smoother tones.",
        why="Less grainy than classic dots; skin and skies look softer.",
        best="Photos on light woods (basswood, maple, birch), slate, anodized aluminum."),
    "stucki": dict(
        name="Crisp dots (Stucki)",
        what="Like smooth dots but slightly sharper.",
        why="Keeps faces and edges defined while still blending tones.",
        best="Portraits on slate, tile, leather and wood."),
    "atkinson": dict(
        name="Bright dots (Atkinson)",
        what="Fewer dots in light areas, punchy contrast.",
        why="Leaves more bare material so marks that spread don't fill in; gives a retro look.",
        best="Materials where burns spread (dark woods, leather) or high-contrast pictures."),
    "bayer": dict(
        name="Grid dots (ordered)",
        what="An even, regular cross-hatch dot pattern.",
        why="Spreads heat evenly and is very predictable, but looks mechanical on photos.",
        best="Graphics, simple shading, materials with uneven grain."),
    "halftone": dict(
        name="Halftone (newspaper dots)",
        what="Round dots on a fixed grid that grow bigger as the picture gets darker.",
        why="Single tiny dots may not mark at all while solid areas bloom; bigger spaced dots sit in between.",
        best="Coated steel lids, glass, tile, comic/vintage looks."),
    "grayscale": dict(
        name="Grayscale power",
        what="One pass where laser power follows the darkness of each spot.",
        why="Smoothest tones when the material darkens evenly with power. On your pine the shades S200-S350 "
            "burned nearly alike, which is why the layered method exists.",
        best="Basswood, maple, birch plywood, leather, cardboard."),
    "threshold": dict(
        name="Black & white",
        what="Every spot is fully on or off; no dots.",
        why="Clean solid marks; no photo tones.",
        best="Logos, text, line art, silhouettes."),
    "centerline": dict(
        name="Thin lines (centerlines)",
        what="Thins dark strokes to a 1-cell skeleton, then engraves it in horizontal raster rows.",
        why="Proven for lettering on the pine plank (max S300). This is not a continuous vector trace; "
            "the physical line width depends on focus, material and exposure.",
        best="Lettering, signatures, line drawings on wood."),
    "sketch": dict(
        name="Pencil sketch",
        what="Turns a photo into drawn outline strokes.",
        why="Keeps the shapes and edges, drops flat areas: fast, bold and forgiving.",
        best="Most materials; a good first look at a new photo."),
}

LOOKS = {  # preview colours: (bare material RGB, fully marked RGB)
    "pine": ((233, 203, 156), (66, 38, 22)),
    "lightwood": ((240, 220, 182), (78, 48, 28)),
    "darkwood": ((150, 100, 64), (40, 24, 14)),
    "anodized": ((26, 26, 30), (206, 206, 212)),
    "steel": ((200, 182, 128), (110, 110, 112)),
    "slate": ((54, 57, 61), (178, 180, 182)),
    "leather": ((196, 150, 104), (64, 36, 18)),
    "cardboard": ((196, 166, 124), (60, 40, 24)),
    "tile": ((242, 242, 238), (28, 28, 28)),
    "glass": ((210, 222, 222), (40, 44, 44)),
    "acrylic": ((16, 16, 18), (150, 150, 152)),
    "tin": ((214, 216, 220), (110, 100, 92)),          # reflective tin lid: bright silver, grey-brown marks
    "blacktin": ((30, 30, 33), (196, 196, 202)),       # black aluminum tin: marks come out light
}


@dataclass
class Material:
    key: str
    name: str
    badge: str                      # PROVEN | START | EXPERIMENTAL | MINE
    style: str                      # key of STYLES
    look: str                       # key of LOOKS
    summary: str                    # one plain sentence
    notes: list = field(default_factory=list)
    pitch: float = 0.15             # row spacing / dot size, mm. Tristan's standard is 0.15 (Nov 18-20); 0.10 = high density
    feed: int = 2250                # burn speed, mm/min
    power: int = 500                # S for dot/line styles; grayscale maximum
    power_min: int = 0              # grayscale minimum (lightest burned tone)
    tone_power: tuple = (250, 300, 350)       # layers: light / mid / dark
    tone_cuts: tuple = (110, 78, 48)          # lightness cut points: bare | light | mid | dark
    layer_rule: tuple = ((1, 0), (1, 1), (3, 2))   # per layer: (lightest tone burned, shrink in cells)
    interlace: int = 5              # layers: row groups; other styles: 1 = in order, 5 = cooler row order
    widen_gaps: bool = True
    thin_pass: bool = True
    thin_cap: int = 300
    halftone_cell: float = 0.5
    negative: bool = False
    sharpen: int = 0
    contrast: int = 0
    brightness: int = 0
    gamma: float = 1.0
    autolevel: bool = False
    black_point: int = 0
    white_point: int = 255
    runup: float = 4.0              # laser-off run-up/out at each row end, mm (raised automatically for speed)
    feature_runup: float = 1.0
    row_feed: int = 600             # laser-off move to the next row
    hop_feed: int = 3000            # laser-off hops and parking
    passes: int = 1
    test_power: tuple = (40, 80)    # suggested test-grid range, %
    test_speed: tuple = (3000, 6000)
    piece: str = ""                 # suggested workpiece
    based_on: str = ""              # my presets: the built-in preset they were saved from (for its photos)
    scan_direction: str = "alternating"  # forward = every marked row left to right; return moves stay off
    fast_blank_gaps: bool = False   # opt-in: long internal S0 gaps travel faster (see blank_guard_mm)
    blank_feed: int = 6000          # fast gaps: Blank travel speed, its own setting (not the rewind/return speed)
    blank_guard_mm: float = 2.0     # fast gaps: laser-off distance kept at engraving speed on EACH side of a gap
    blank_min_fast_mm: float = 2.0  # fast gaps: shortest fast middle worth it; shorter gaps stay at engraving speed

    def __post_init__(self):
        if self.scan_direction not in ("alternating", "forward"):
            raise ValueError("Scan direction must be alternating or forward.")
        if type(self.fast_blank_gaps) is not bool:
            raise ValueError("Fast blank gaps must be true or false.")
        if not 1 <= int(self.blank_feed) <= 6000:
            raise ValueError("Blank travel speed must be 1-6000 mm/min (6000 is the controller's maximum, $110).")
        if not 0.5 <= float(self.blank_guard_mm) <= 20.0:
            raise ValueError("Fast blank gaps: the slow-down / speed-up offset each side must be 0.5-20 mm.")
        if not 0.0 <= float(self.blank_min_fast_mm) <= 100.0:
            raise ValueError("Fast blank gaps: the shortest fast part must be 0-100 mm.")

    def copy(self, **changes) -> "Material":
        d = asdict(self)
        d.update(changes)
        return Material(**d)

    @staticmethod
    def from_dict(d: dict) -> "Material":
        names = {f.name for f in fields(Material)}
        clean = {k: (tuple(tuple(x) if isinstance(x, list) else x for x in v) if isinstance(v, list)
                     and k in ("tone_power", "tone_cuts", "layer_rule", "test_power", "test_speed") else v)
                 for k, v in d.items() if k in names}
        return Material(**clean)


BUILTIN = [
    # ---------------------------------------------------------------- proven on this machine
    Material(
        key="pine-layers", name="Pine plank - layered photo", badge="PROVEN", style="layers", look="pine",
        summary="Your best wood result: 3 shrinking layers at 25/30/35% power, 2250 mm/min, 0.1 mm rows.",
        notes=["Proven on dragon test 12 and the North Pole plank.",
               "Lightest tones stay bare wood; white gaps are widened 0.1 mm so char doesn't close them.",
               "Layer 1 burns every 5th row over all tones, layer 2 the next rows 0.1 mm smaller, "
               "layer 3 only the darks 0.2 mm smaller.",
               "Thin lettering is burned as centerlines, max 30%.",
               "Don't add a heavy line pass over dark areas: it only adds scorch (test 7).",
               "Take a photo after each layer; the app pauses for it."],
        sharpen=70, piece="plank76"),
    Material(
        key="pine-layer-count", name="Pine plank - tone by layer count", badge="PROVEN", style="layers",
        look="pine",
        summary="Same proven recipe, but light = 1 layer, mid = 2, dark = 3 (as written in the brief).",
        notes=["Slightly lighter overall than the plank recipe: light tones get a single row in five.",
               "Use it when the plank recipe looks too dark on a lighter photo."],
        layer_rule=((1, 0), (2, 1), (3, 2)), sharpen=70, piece="plank76"),
    Material(
        key="pine-lettering", name="Pine - lettering & line art", badge="PROVEN", style="centerline", look="pine",
        summary="Text and drawings as 1-cell centerlines at 30% power, 2250 mm/min.",
        notes=["Proven on the North Pole sign letters (centerlines, capped at S300).",
               "For black-on-white artwork, not photos."],
        power=300, feed=2250, piece="plank76"),
    Material(
        key="pine-sketch", name="Pine - sketch outlines", badge="PROVEN", style="sketch", look="pine",
        summary="A photo as drawn outlines at 40% power, 3000 mm/min.",
        notes=["A lone thin line at 3000 mm/min only showed at 40% on pine; below 25% it is faint.",
               "Outlines over already-dark shading add scorch; use on bare wood."],
        power=400, feed=3000, runup=4.0, piece="plank76"),
    Material(
        key="anodized-dots", name="Black anodized aluminum - photo dots", badge="PROVEN", style="floyd",
        look="anodized",
        summary="Silver dots on black: 50% power, 2500 mm/min, 0.1 mm rows, one pass.",
        notes=["Good result on the heart card (Floyd-Steinberg dots, 1.8 mm run-up). The engineering card's "
               "recorded trial took 10 min 37 s, with 0 errors.",
               "The laser makes LIGHT marks, so photos are engraved as a negative to look right. Turn Negative "
               "off for black-on-white artwork that should be marked exactly as drawn.",
               "Marks too dim or grey? This is only 50% power: raise power first (60-75%), or slow down "
               "(about 1800 mm/min). Extra passes are the last resort - they blur the dots.",
               "Too much energy makes dots bloom together and can turn the coating grey/brown.",
               "Coatings vary between suppliers; try a spare card or a test grid first."],
        power=500, feed=2500, runup=1.8, negative=True, interlace=1, piece="card-portrait",
        test_power=(30, 70), test_speed=(2000, 4000)),
    Material(
        key="anodized-crisp", name="Black anodized aluminum - crisp dots", badge="START", style="stucki",
        look="anodized",
        summary="Proven 50% / 2500 mm/min energy with sharper Stucki dots for faces and small text.",
        notes=["Same power and speed as the proven card; only the dot pattern changes.",
               "Community 20 W charts suggest Stucki or Atkinson for anodized photos."],
        power=500, feed=2500, runup=1.8, negative=True, interlace=1, piece="card-portrait",
        test_power=(30, 70), test_speed=(2000, 4000)),
    Material(
        key="lid-halftone", name="Coated steel jar lid - halftone", badge="EXPERIMENTAL", style="halftone",
        look="steel",
        summary="Bigger spaced dots (0.5 mm grid) at 100% power, 2500 mm/min. Untested: run a test grid first.",
        notes=["Lid findings: lone 0.1 mm dots barely mark at 2500 mm/min, and dense dot areas bloom to "
               "0.25-0.3 mm and merge into a frosted silhouette.",
               "Halftone keeps dots large and spaced so they mark without merging.",
               "Keep raster art inside the 49 mm flat face. Focus matters more than speed on lids.",
               "Proven lid LINE setting (vector, not photos): S570 at 300 mm/min. Etched lids are decorative only."],
        power=1000, feed=2500, runup=1.8, halftone_cell=0.5, interlace=1, piece="lid76",
        test_power=(60, 100), test_speed=(1000, 2500)),
    # ---------------------------------------------------------------- published starting points
    Material(
        key="basswood-gray", name="Basswood / birch plywood - grayscale", badge="START", style="grayscale",
        look="lightwood",
        summary="Smooth one-pass shading: 0-35% power at 4000 mm/min.",
        notes=["Snapmaker's tested 20 W fill on basswood plywood is 20% at 4200 mm/min, 0.1 mm lines.",
               "Light, even woods darken smoothly with power, so grayscale works where pine didn't.",
               "Test 20-50%: your U20 needed about 3x Snapmaker's energy on pine."],
        power=350, power_min=0, feed=4000, runup=6.0, sharpen=40, interlace=1, piece="square100",
        test_power=(20, 60), test_speed=(3000, 6000)),
    Material(
        key="basswood-dots", name="Basswood / maple / birch - smooth dots", badge="START", style="jarvis",
        look="lightwood",
        summary="Photo dots at 35% power, 3500 mm/min.",
        notes=["Jarvis dots give smooth skin tones on light woods.",
               "Sand to ~220 grit; species matter (maple and birch hold detail best, oak grain breaks it up)."],
        power=350, feed=3500, runup=5.0, sharpen=40, interlace=1, piece="square100",
        test_power=(20, 60), test_speed=(3000, 6000)),
    Material(
        key="slate", name="Slate coaster - photo", badge="START", style="stucki", look="slate",
        summary="Light marks on dark stone: 50% power, 3500 mm/min, engraved as a negative.",
        notes=["Community 20 W charts: 40-60% at 3500-4000 mm/min, Stucki or Jarvis dots.",
               "Slate turns pale grey where lasered, so Negative is on.",
               "Wipe off dust afterwards; a light oil makes the dark areas richer."],
        power=500, feed=3500, runup=5.0, negative=True, sharpen=30, interlace=1, piece="coaster100",
        test_power=(30, 70), test_speed=(3000, 5000)),
    Material(
        key="leather", name="Leather (real veg-tan) - photo", badge="START", style="stucki", look="leather",
        summary="35% power at 4500 mm/min with crisp dots.",
        notes=["Community 20 W charts: 30-40% at 4000-5000 mm/min.",
               "Real leather only. Never laser PVC or faux leather: it releases chlorine gas.",
               "Leather scorches easily: keep air assist on and test on an offcut."],
        power=350, feed=4500, runup=6.0, sharpen=30, interlace=1, piece="square100",
        test_power=(20, 50), test_speed=(3000, 6000)),
    Material(
        key="cardboard", name="Cardboard / paper - photo", badge="START", style="floyd", look="cardboard",
        summary="Light touch: 20% power at 6000 mm/min.",
        notes=["Community 20 W charts: 15-30% at 5000-6000 mm/min.",
               "Catches fire easily. Never leave it running and keep air assist on."],
        power=200, feed=6000, runup=11.0, interlace=1, piece="square100",
        test_power=(10, 40), test_speed=(4000, 6000)),
    Material(
        key="tile", name="White tile (Norton paint method) - photo", badge="START", style="stucki", look="tile",
        summary="Paint a white tile black, engrave at 90% / 2500 mm/min, then wash the loose paint off.",
        notes=["The laser fuses the paint into the glaze where it marks; the rest washes away.",
               "Community 20 W charts: 80-100% at 2000-3000 mm/min, Stucki or Jarvis dots."],
        power=900, feed=2500, runup=4.0, interlace=1, piece="tile108",
        test_power=(60, 100), test_speed=(1500, 3500)),
    Material(
        key="glass", name="Glass (painted or taped) - photo", badge="START", style="halftone", look="glass",
        summary="90% at 3000 mm/min through a coat of paint or masking; bigger dots mark more reliably.",
        notes=["Diode light passes straight through clear glass: coat it (tempera paint or tape) first.",
               "Community 20 W charts: 80-100% at 2500-3500 mm/min."],
        power=900, feed=3000, runup=5.0, halftone_cell=0.4, interlace=1, piece="square100",
        test_power=(60, 100), test_speed=(2000, 4000)),
    Material(
        key="stainless", name="Stainless steel (with marking spray)", badge="START", style="floyd",
        look="steel",
        summary="90% at 1200 mm/min with a marking spray for dark, permanent marks.",
        notes=["Snapmaker's tested 20 W fill on stainless is 90% at 1200 mm/min, 0.1 mm lines.",
               "Bare stainless barely marks with a diode; a marking spray bonds dark marks."],
        power=900, feed=1200, runup=2.0, interlace=1, piece="card-landscape",
        test_power=(70, 100), test_speed=(800, 2000)),
    Material(
        key="acrylic-black", name="Black cast acrylic - photo", badge="START", style="floyd", look="acrylic",
        summary="50% at 4000 mm/min; marks come out light, so Negative is on.",
        notes=["Clear or blue acrylic doesn't absorb diode light; black or opaque cast acrylic does.",
               "Ventilate: acrylic smells strongly when engraved."],
        power=500, feed=4000, runup=6.0, negative=True, interlace=1, piece="square100",
        test_power=(30, 70), test_speed=(3000, 6000)),
    Material(
        key="logo-wood", name="Logo / text on light wood (black & white)", badge="START", style="threshold",
        look="lightwood",
        summary="Solid black-and-white artwork at 40% power, 3000 mm/min.",
        notes=["For crisp logos and signs. Photos look harsh in this style."],
        power=400, feed=3000, runup=4.0, interlace=1, piece="square100",
        test_power=(20, 60), test_speed=(2000, 5000)),
]

# Standard row spacing is now 0.15 mm. The PROVEN recipes were proven at 0.10 mm: say so instead of hiding it.
for _m in BUILTIN:
    if _m.badge == "PROVEN":
        _m.notes = list(_m.notes) + ["Proven at 0.10 mm rows. Studio's standard is now 0.15 mm; set Row spacing to "
                                     "0.10 for the original proven density."]

def lid_piece(diameter: float = 50.8, safe: float = 45.72, name: str | None = None) -> dict:
    """The one round-lid geometry: outside diameter, usable face, centre origin. Step 3's 2 in tin template and
    the lid ladders both use this, so the same lid is never defined twice."""
    m = round((diameter - safe) / 2, 3)
    return dict(name=name or f"Round lid {diameter / 25.4:g} in ({safe:g} mm face, centre zero)", shape="circle",
                w=diameter, h=diameter, origin="center", margins=(m, m, m, m), corner=0.0, keepouts=[])


PIECES = {
    "plank76": dict(name="Pine plank 7 x 6 in (twine holes at top)", shape="rect", w=177.8, h=152.4,
                    origin="lower-left", margins=(6.0, 6.0, 6.0, 16.0), corner=0.0,
                    keepouts=[dict(kind="circle", x=44.45, y=144.4, r=5.0),
                              dict(kind="circle", x=133.35, y=144.4, r=5.0)]),
    "card-portrait": dict(name="Card 2 x 4 in, portrait", shape="rect", w=50.8, h=101.6, origin="lower-left",
                          margins=(2.0, 2.0, 2.0, 2.0), corner=0.0, keepouts=[]),
    "card-landscape": dict(name="Card 4 x 2 in, landscape", shape="rect", w=101.6, h=50.8, origin="lower-left",
                           margins=(4.0, 2.0, 4.0, 2.0), corner=0.0, keepouts=[]),
    "lid76": dict(name="Jar lid 3 in (flat face 49 mm)", shape="circle", w=76.2, h=76.2, origin="center",
                  margins=(13.6, 13.6, 13.6, 13.6), corner=0.0, keepouts=[]),
    "tin50": lid_piece(50.8, 45.72, "Reflective tin lid 2 in (45.72 mm face, centre zero)"),
    "tin51face": dict(lid_piece(52.3875, 51.0, "Tin lid 2 1/16 in (51 mm modeled face, centre zero)"),
                      margins=((52.3875 - 51.0) / 2,) * 4),
    "coaster100": dict(name="Square 100.6 x 100.6 mm (slate)", shape="rect", w=100.6, h=100.6,
                       origin="lower-left", margins=(5.8, 5.8, 5.8, 5.8), corner=0.0, keepouts=[]),
    "tile108": dict(name="Tile 4.25 in (108 mm)", shape="rect", w=108.0, h=108.0, origin="lower-left",
                    margins=(5.0, 5.0, 5.0, 5.0), corner=0.0, keepouts=[]),
    "square100": dict(name="Square 100 x 100 mm (generic; 3 mm margins)", shape="rect", w=100.0, h=100.0, origin="lower-left",
                      margins=(3.0, 3.0, 3.0, 3.0), corner=0.0, keepouts=[]),
    "custom": dict(name="Custom size", shape="rect", w=100.0, h=100.0, origin="lower-left",
                   margins=(3.0, 3.0, 3.0, 3.0), corner=0.0, keepouts=[]),
}

# Toy cars (1:64 die-cast, Hot Wheels size), seen from above. Window positions are fractions of the car's length
# measured from the FRONT, so they scale with the length you enter. They're starting points: measure your own car
# (calipers or a ruler) and adjust them in the 'Toy car' window. Widths are the window's width across the car.
CAR_BODIES = {
    "mustang": dict(name="Your yellow Mustang (86.4 x 30.5 mm as measured)", length=86.36, width=30.48,
                    windshield=(0.30, 0.42), rear=(0.60, 0.80), window_w=22.0, corner=5.0),
    "coupe": dict(name="Coupe / muscle car", length=75.0, width=30.0,
                  windshield=(0.33, 0.44), rear=(0.58, 0.68), window_w=22.0, corner=5.0),
    "fastback": dict(name="Fastback (long sloping rear window)", length=76.0, width=30.0,
                     windshield=(0.30, 0.42), rear=(0.58, 0.80), window_w=22.0, corner=5.0),
    "sports": dict(name="Low sports car", length=74.0, width=31.0,
                   windshield=(0.30, 0.46), rear=(0.58, 0.66), window_w=21.0, corner=6.0),
    "pickup": dict(name="Pickup truck", length=78.0, width=30.0,
                   windshield=(0.28, 0.38), rear=(0.50, 0.53), window_w=23.0, corner=4.0),
    "van": dict(name="Van / SUV (no rear window on top)", length=72.0, width=30.0,
                windshield=(0.16, 0.28), rear=None, window_w=24.0, corner=4.0),
}
CAR_STARTS = {"windshield": "Front edge of the windshield, on the centerline",
              "roof": "Middle of the roof",
              "nose": "Front tip of the car, on the centerline"}


def car_values(body: str, length: float | None = None) -> dict:
    """The body type's numbers in mm for a car of this length (its own length if not given)."""
    b = CAR_BODIES[body]
    L = float(length or b["length"])
    ws, rear = b["windshield"], b["rear"]
    return dict(body=body, length=L, width=b["width"], front="right", ws_from=round(ws[0] * L, 1),
                ws_len=round((ws[1] - ws[0]) * L, 1), rear_from=round(rear[0] * L, 1) if rear else 0.0,
                rear_len=round((rear[1] - rear[0]) * L, 1) if rear else 0.0, window_w=b["window_w"],
                clearance=1.0, corner=b["corner"], start="windshield")


def car_piece(v: dict) -> dict:
    """A piece (top view of a toy car) with no-burn zones over the windshield and rear window and the start point
    on a spot you can find on the real car. x runs along the car, y across it."""
    L, W, c = float(v["length"]), float(v["width"]), float(v.get("clearance", 1.0))
    right = v.get("front", "right") == "right"

    def x_from_front(d):
        return L - d if right else d

    def window(d0, n):
        xa, xb = sorted((x_from_front(d0 - c), x_from_front(d0 + n + c)))
        xa, xb = max(0.0, xa), min(L, xb)
        ww = min(W, float(v["window_w"]) + 2 * c)
        return dict(kind="rect", x=round(xa, 2), y=round((W - ww) / 2, 2), w=round(xb - xa, 2), h=round(ww, 2))

    keepouts = [window(float(v["ws_from"]), float(v["ws_len"]))]
    if float(v.get("rear_len") or 0) > 0:
        keepouts.append(window(float(v["rear_from"]), float(v["rear_len"])))
    start = v.get("start", "windshield")
    if start == "roof" and float(v.get("rear_len") or 0) > 0:
        d = (float(v["ws_from"]) + float(v["ws_len"]) + float(v["rear_from"])) / 2
    elif start == "roof":
        d = float(v["ws_from"]) + float(v["ws_len"]) + 10.0
    elif start == "nose":
        d = 0.0
    else:
        d = float(v["ws_from"])
    name = CAR_BODIES.get(v.get("body"), {}).get("name", "Toy car")
    return dict(name=f"Toy car: {name}", shape="rect", w=round(L, 2), h=round(W, 2), origin="spot",
                spot=[round(x_from_front(d), 2), round(W / 2, 2)], margins=(1.0, 1.0, 1.0, 1.0),
                corner=float(v.get("corner", 4.0)), keepouts=keepouts, car=dict(v))


# The toy car shows up in step 3's piece list (just before 'Custom size'); 'Toy car...' adjusts it.
PIECES = {**{k: v for k, v in PIECES.items() if k != "custom"},
          "car": dict(car_piece(car_values("mustang")), name="Toy car, top view (Hot Wheels size)"),
          "custom": PIECES["custom"]}


BADGES = {
    "PROVEN": "Proven on your U20",
    "START": "Starting point - test first",
    "EXPERIMENTAL": "Experimental - test first",
    "MINE": "My preset",
}


def user_presets_path() -> Path:
    return DATA_DIR / "my-presets.json"


def describe_recipe(m: Material, pass_count: int) -> str:
    if m.style == "layers":
        power = "/".join(f"{value / 10:g}" for value in m.tone_power) + "% by layer"
    elif m.style == "grayscale":
        power = f"{m.power_min / 10:g}–{m.power / 10:g}%"
    else:
        power = f"{m.power / 10:g}%"
    direction = "left to right" if m.scan_direction == "forward" else "alternating"
    return (f"Effective power and speed: {power} at {m.feed:g} mm/min. "
            f"{STYLES[m.style]['name']}, {direction}, {pass_count} pass(es).")


def matching_recipe(material: Material, materials: list) -> Material | None:
    """Reuse a stored recipe without confusing picture adjustments with material settings."""
    separate = {'key', 'name', 'badge', 'summary', 'notes', 'based_on', 'piece', 'test_power', 'test_speed',
                'brightness', 'contrast', 'gamma', 'sharpen', 'autolevel', 'negative', 'black_point', 'white_point'}
    recipe = {f.name: getattr(material, f.name) for f in fields(Material) if f.name not in separate}
    matches = [m for m in materials if all(getattr(m, k) == v for k, v in recipe.items())]
    return next((m for m in matches if m.key == material.key), matches[0] if matches else None)


def print_settings(m: Material) -> dict:
    """Operator-facing values used by the current picture style; omit inactive settings."""
    power = f"{m.power / 10:g}%"
    if m.style == "layers":
        power = "/".join(f"{p / 10:g}" for p in m.tone_power) + "%"
    elif m.style == "grayscale":
        power = f"{m.power_min / 10:g}–{power}"
    values = {"Style": STYLES[m.style]["name"], "Power": power, "Speed": f"{m.feed:g} mm/min",
              "Row spacing": f"{m.pitch:g} mm",
              "Direction": "Left to right" if m.scan_direction == "forward" else "Alternating",
              "Return": f"{m.row_feed:g} mm/min", "Run-up": f"{m.runup:g} mm",
              "Row groups": str(m.interlace), "Fast blank gaps": "Off"}
    if m.fast_blank_gaps:
        values["Fast blank gaps"] = (f"{m.blank_feed:g} mm/min, {m.blank_guard_mm:g} mm each side, "
                                     f"{m.blank_min_fast_mm:g} mm minimum middle")
    if m.style == "layers":
        values.update({"Layer rule": str(m.layer_rule), "Tone cuts": str(m.tone_cuts),
                       "Widen white gaps": "On" if m.widen_gaps else "Off",
                       "Thin line pass": "Off"})
        if m.thin_pass:
            values["Thin line pass"] = (f"{m.thin_cap / 10:g}% cap, "
                                        f"{m.hop_feed:g} mm/min travel, {m.feature_runup:g} mm run-up")
    else:
        values["Passes"] = str(m.passes)
    if m.style == "halftone":
        values["Halftone spacing"] = f"{m.halftone_cell:g} mm"
    return values


def exposure_settings(current: Material, target: Material) -> dict:
    """Copy only compatible exposure values, preserving which tones can fire."""
    def channels(m):
        if m.style == "layers":
            return ("tone_power", "thin_cap")
        if m.style == "grayscale":
            return ("power_min", "power")
        return ("power",)
    changes = {"feed": target.feed}
    keys = channels(current)
    if keys != channels(target):
        return changes
    for key in keys:
        a, b = getattr(current, key), getattr(target, key)
        old = a if isinstance(a, (tuple, list)) else (a,)
        new = b if isinstance(b, (tuple, list)) else (b,)
        if [v > 0 for v in old] != [v > 0 for v in new]:
            return changes
    if current.style == "grayscale":
        # The planner rounds fifteen power levels to integer S values.
        for level in range(1, 16):
            def fires(m):
                return round(m.power_min + level / 15 * (m.power - m.power_min)) > 0
            if fires(current) != fires(target):
                return changes
    changes.update({key: getattr(target, key) for key in keys})
    return changes


def settings_changes(before: dict, after: dict) -> list[str]:
    """Return effective changes in display order, including style-specific controls."""
    return [f"{key}: {before.get(key, 'unused')} → {after.get(key, 'unused')}"
            for key in dict.fromkeys((*before, *after)) if before.get(key) != after.get(key)]


def matching_piece_key(piece: dict) -> str | None:
    """Match full saved geometry, allowing JSON's lists in place of template tuples."""
    def geometry(p):
        return json.loads(json.dumps({k: v for k, v in p.items() if k != 'name'}))
    target = geometry(piece)
    return next((key for key, candidate in PIECES.items()
                 if key != 'custom' and geometry(candidate) == target), None)


def piece_choice_label(piece: dict) -> str:
    """Describe real geometry; a close nominal size must not claim an exact match."""
    key = matching_piece_key(piece)
    if key:
        return PIECES[key]['name']
    w, h = piece['w'], piece['h']
    if piece.get('outline'):
        return f'Shaped piece {w:g} x {h:g} mm (own outline)'
    if piece.get('shape') == 'circle':
        return f'Custom round lid ({w:g} mm outside diameter)'
    shape = 'square' if w == h else 'rectangle'
    return f'Custom {shape} {w:g} x {h:g} mm'


def piece_explanation(piece: dict, fit: str = "whole", loaded_job: bool = False) -> str:
    """What the size box means right now, and which setting wins. Shown under the template list."""
    key = matching_piece_key(piece)
    m = piece.get("margins", (0, 0, 0, 0))
    shape = "circle" if piece.get("shape") == "circle" else "rectangle"
    usable = (f"{piece['w'] - m[0] - m[2]:g} mm usable face" if shape == "circle"
              else f"{piece['w'] - m[0] - m[2]:g} x {piece['h'] - m[1] - m[3]:g} mm usable area")
    zero = {"center": "the centre", "lower-left": "the lower-left corner", "spot": "a picked spot"}.get(
        piece.get("origin"), piece.get("origin", "?"))
    what = f"Template '{PIECES[key]['name']}'" if key else "Custom size"
    if shape == "circle" and fit != "exact" and len(set(m)) == 1:
        lines = [f"{what}. Outside diameter: {piece['w']:g} mm ({piece['w'] / 25.4:g} in). "
                 f"Rim inset: {m[0]:g} mm per side. Artwork limit: {usable}. Job zero at {zero}."]
    else:
        lines = [f"{what}: {piece['w']:g} x {piece['h']:g} mm {shape}, {usable}, job zero at {zero}."]
    if piece.get("outline"):
        lines.append(f"Shaped piece: marks stay inside its own {len(piece['outline'])}-point outline, and Stock "
                     "perimeter traces that outline.")
    if fit == "exact":
        lines.append("Exact image size is on: the box is the image itself, margins are ignored.")
    elif fit == "art-exact":
        lines.append("Exact image size is on: the image keeps its proportions within the usable face.")
    if loaded_job:
        lines.append("The job opened with its saved piece. These are the current values. Selecting a size template "
                     "replaces them and rebuilds the job.")
    elif key:
        lines.append("Precedence: editing width, height, margins, corner or origin overrides the template and turns "
                     "it into a measured size; nothing else changes it behind your back.")
    else:
        lines.append("Precedence: these exact numbers are used as shown. Pick a template to replace them.")
    return " ".join(lines)


def load_materials() -> list:
    out = list(BUILTIN)
    p = user_presets_path()
    if p.exists():
        try:
            for d in json.loads(p.read_text(encoding="utf-8")):
                m = Material.from_dict(d)
                m.badge = "MINE"
                out.append(m)
        except Exception:
            pass
    return out


def save_user_material(m: Material) -> None:
    from .jobs import write_json
    p = user_presets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    items = []
    if p.exists():
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f"The existing preset library could not be read. It is still at {p}.") from exc
        if not isinstance(items, list) or not all(isinstance(item, dict) and item.get("key") for item in items):
            raise ValueError(f"The existing preset library has an unrecognized format. It is still at {p}.")
    items = [d for d in items if d.get("key") != m.key]
    d = asdict(m)
    d["badge"] = "MINE"
    items.append(d)
    write_json(p, items)


def delete_user_material(key: str) -> None:
    p = user_presets_path()
    if p.exists():
        items = [d for d in json.loads(p.read_text(encoding="utf-8")) if d.get("key") != key]
        p.write_text(json.dumps(items, indent=1), encoding="utf-8")


def auto_runup(feed: float, accel: float = 500.0, minimum: float = 1.0) -> float:
    """Laser-off distance the head needs to reach full speed (v^2 / 2a) plus margin, so row ends don't over-burn."""
    v = feed / 60.0
    return round(max(minimum, v * v / (2.0 * accel) * 1.1 + 0.2), 1)


def energy(m: Material) -> float:
    """Relative laser energy per mm: power / speed x passes. More energy = darker, deeper marks."""
    power = m.tone_power[2] if m.style == "layers" else m.power
    return power / max(1, m.feed) * max(1, m.passes)




def gcode_settings_summary(m: Material) -> str:
    """Neutral machine-readable recipe summary; does not assert compatibility with other controllers."""
    if m.style == "layers":
        powers = "layer tone power " + "/".join(f"S{int(v)}" for v in m.tone_power)
        passes = "layered tone passes (plus thin detail where generated)"
    elif m.style == "grayscale":
        powers = f"power S{m.power_min}–S{m.power}"
        passes = f"{max(1, int(m.passes))} pass(es)"
    else:
        powers = f"power S{m.power}"
        passes = f"{max(1, int(m.passes))} pass(es)"
    pitch = max(float(m.pitch), 1e-6)
    return (f"{powers} ($30=1000 scale on the U20)  |  "
            f"feed F{int(m.feed)} mm/min  |  "
            f"row pitch {pitch:g} mm ({1.0 / pitch:.2f} lines/mm)  |  M4 dynamic power\n"
            f"{passes}  |  {max(1, int(m.interlace))} cooling row group(s)  |  "
            f"preset Negative default {'ON' if m.negative else 'OFF'} (may be overridden in step 4)")
