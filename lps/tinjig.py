"""Software tin jig: one saved layout of round tins on the bed, one fixed job zero, per-tin nudges.

Tristan's request (Nov 19, via the mobile GPT handoffs 5835c8a / 837406a):
  * a saved layout, not a new fixture; one machine zero; per-tin XY nudges saved independently, and a group move
    never erases them;
  * trace the travel envelope or the true image path (a circle for a round tin) for one tin, a selection or all;
  * stop at a misaligned tin, nudge only that tin, retrace it, then continue the rest (never resume stale G-code);
  * preferred larger layout: "2 or 3 horizontal rows of 7 ... i have more cord freedom on x axis", flush 50.8 mm
    pitch on X and Y (editable); 20 tins = 7 + 7 + 6 with the last slot disabled; 6/9/12/16/18/24 kept.

Each tin is burned as its OWN checked job (the normal planner, verifier and runner), placed at its slot centre in the
shared job-zero frame. So a pause, a retrace or a nudge only ever touches that one tin, and a nudge makes that tin's
job stale (its fingerprint changes) so it must be rebuilt before it can run.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field

from . import imaging, planner

PITCH = 50.8                    # mm, flush 2 in tins centre to centre (editable)
CONTROLLER_TRAVEL = (420.0, 400.0)   # $130 / $131 read from this controller in the job logs (mm)

# name -> (columns, rows, enabled slot count or None for all). Slot 1 is top-left; rows run left to right.
PRESETS = {
    "42 (7 x 6)": (7, 6, None),
    "6 (2 x 3)": (2, 3, None),
    "7 x 3 (21)": (7, 3, None),
    "20 = 7 + 7 + 6 (last slot off)": (7, 3, 20),
    "18 = 7 + 7 + 4": (7, 3, 18),
    "16 = 7 + 7 + 2": (7, 3, 16),
    "7 x 2 (14)": (7, 2, None),
    "6 (3 x 2)": (3, 2, None),
    "9 (3 x 3)": (3, 3, None),
    "12 (4 x 3)": (4, 3, None),
    "16 (4 x 4)": (4, 4, None),
    "18 (6 x 3)": (6, 3, None),
    "20 (5 x 4)": (5, 4, None),
    "24 (6 x 4)": (6, 4, None),
}
ZERO_MODES = ("slot1", "centre")     # job zero at slot 1's centre, or at the layout's centre


@dataclass
class Slot:
    row: int
    col: int
    dx: float = 0.0                 # this tin's own nudge, mm (never changed by a group move)
    dy: float = 0.0
    enabled: bool = True
    done: bool = False              # burned in this layout run; a done tin can't be nudged
    rot: int = 0                    # this tin's own picture turn, quarter turns (separate from the scan direction)


@dataclass
class Layout:
    name: str
    cols: int
    rows: int
    pitch_x: float = PITCH
    pitch_y: float = PITCH
    zero: str = "slot1"
    group_dx: float = 0.0           # whole-layout shift, separate from every tin's own nudge
    group_dy: float = 0.0
    flip_alternate_rows: bool = False   # turn every second row's pictures half way (carton rows facing each other)
    slots: list = field(default_factory=list)
    stagger_x: float = 0.0          # shift odd-numbered row indices to match measured staggered pockets

    def __post_init__(self):
        if self.zero not in ZERO_MODES:
            raise ValueError(f"Layout zero must be one of {ZERO_MODES}.")
        if not (1 <= self.cols <= 12 and 1 <= self.rows <= 12):
            raise ValueError("A layout is 1-12 columns by 1-12 rows.")
        if not (10.0 <= self.pitch_x <= 200.0 and 10.0 <= self.pitch_y <= 200.0):
            raise ValueError("Tin pitch must be 10-200 mm.")
        if not self.slots:
            self.slots = [Slot(r, c) for r in range(self.rows) for c in range(self.cols)]
        if len(self.slots) != self.rows * self.cols:
            raise ValueError("The layout's slot list doesn't match its rows and columns.")
        positions = {(s.row, s.col) for s in self.slots}
        if positions != {(r, c) for r in range(self.rows) for c in range(self.cols)}:
            raise ValueError("Each pocket must occupy a distinct row and column in the layout.")
        if any(not math.isfinite(v) for v in (self.group_dx, self.group_dy, self.stagger_x,
                *(value for s in self.slots for value in (s.dx, s.dy)))):
            raise ValueError("Pocket and group offsets must be finite distances.")
        if any(type(s.rot) is not int or not 0 <= s.rot <= 3 for s in self.slots):
            raise ValueError("Picture orientation must be a quarter turn.")

    # ---------------------------------------------------------------- geometry
    def base(self, i: int) -> tuple:
        """Slot i's nominal centre (no nudges), relative to job zero."""
        s = self.slots[i]
        x, y = s.col * self.pitch_x + (self.stagger_x if s.row % 2 else 0), -s.row * self.pitch_y
        if self.zero == "centre":
            x -= (self.cols - 1) * self.pitch_x / 2
            if self.rows > 1:
                x -= self.stagger_x / 2
            y += (self.rows - 1) * self.pitch_y / 2
        return x, y

    def centre(self, i: int) -> tuple:
        s = self.slots[i]
        bx, by = self.base(i)
        return round(bx + self.group_dx + s.dx, 3), round(by + self.group_dy + s.dy, 3)

    def rotation(self, i: int) -> int:
        """Quarter turns for tin i's picture: its own turn, plus a half turn on alternate rows if flipped.
        This only turns the picture; rows are still burned the scan direction the material says."""
        s = self.slots[i]
        return (s.rot + (2 if self.flip_alternate_rows and s.row % 2 else 0)) % 4

    def enabled(self) -> list:
        return [i for i, s in enumerate(self.slots) if s.enabled]

    def queue(self, selected=None) -> list:
        """Tins still to burn, in order: enabled, not done, and in the selection if one is given."""
        pick = set(range(len(self.slots))) if selected is None else set(selected)
        return [i for i in self.enabled() if i in pick and not self.slots[i].done]

    # ---------------------------------------------------------------- edits
    def nudge(self, indices, dx: float = 0.0, dy: float = 0.0):
        selected = [self.slots[i] for i in dict.fromkeys(indices)]
        if not all(math.isfinite(n) for n in (dx, dy)):
            raise ValueError("Enter finite X and Y distances.")
        if any(s.done for s in selected):
            raise ValueError("A selected tin is already burned. Its position is locked.")
        for s in selected:
            s.dx, s.dy = round(s.dx + dx, 3), round(s.dy + dy, 3)

    def move_group(self, dx: float = 0.0, dy: float = 0.0):
        if any(s.done for s in self.slots):
            raise ValueError("Some tins are already burned; a group move now would shift the rest off them.")
        self.group_dx, self.group_dy = round(self.group_dx + dx, 3), round(self.group_dy + dy, 3)

    # ---------------------------------------------------------------- saving
    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Layout":
        known = {f.name for f in dataclasses.fields(Layout)}
        unknown = set(d) - known
        if unknown:
            raise ValueError("Unsupported layout settings; nothing was silently dropped: " + ", ".join(sorted(unknown)))
        slot_known = {f.name for f in dataclasses.fields(Slot)}
        slots = []
        for s in d.get("slots", []):
            bad = set(s) - slot_known
            if bad:
                raise ValueError("Unsupported tin settings: " + ", ".join(sorted(bad)))
            slots.append(Slot(**s))
        return Layout(**{**{k: v for k, v in d.items() if k != "slots"}, "slots": slots})


def preset(name: str, **changes) -> Layout:
    cols, rows, count = PRESETS[name]
    lay = Layout(name=name, cols=cols, rows=rows, **changes)
    if count is not None:
        for i, s in enumerate(lay.slots):
            s.enabled = i < count
    return lay


# ---------------------------------------------------------------- fit
def envelope(layout: Layout, art_d: float, runup: float, indices=None) -> tuple:
    """The laser travel box of the given tins (all enabled ones by default): art plus row run-ups on X."""
    idx = layout.enabled() if indices is None else list(indices)
    if not idx:
        return None
    xs = [layout.centre(i)[0] for i in idx]
    ys = [layout.centre(i)[1] for i in idx]
    h = art_d / 2
    return (round(min(xs) - h - runup, 3), round(min(ys) - h, 3), round(max(xs) + h + runup, 3), round(max(ys) + h, 3))


def fit_text(r: dict, zero: str = "slot1") -> str:
    """The fit report in plain words."""
    f = r["free_from_zero"]
    where = "tin 1's centre" if zero == "slot1" else "the layout's centre"
    parts = [f"{f[k]:.0f} mm {name}" for k, name in (("right", "to the right"), ("left", "to the left"),
                                                    ("up", "up"), ("down", "down")) if f[k] >= 1]
    head = (f"The layout is about {r['width']:.0f} x {r['height']:.0f} mm including run-ups. "
            + ("That's inside this controller's travel (" if r["fits_travel"] else "That's MORE than this controller's travel (")
            + f"{r['travel'][0]:.0f} x {r['travel'][1]:.0f} mm, $130/$131). ")
    need = f"With job zero at {where}, the head needs about " + ", ".join(parts) + " of free travel. " if parts else ""
    return head + need + ("Confirm it with the laser-off Total travel perimeter before the first burn, and check "
                          "the cords reach the far tins.")


def fit_report(layout: Layout, art_d: float, runup: float, travel=CONTROLLER_TRAVEL) -> dict:
    """Does the layout fit the controller's travel? It can only say what free travel job zero needs on each side:
    the app never homes, so where zero sits on the machine is unknown until the laser-off travel frame is run."""
    env = envelope(layout, art_d, runup)
    w, h = env[2] - env[0], env[3] - env[1]
    return dict(envelope=env, width=round(w, 1), height=round(h, 1), travel=travel,
                fits_travel=w <= travel[0] and h <= travel[1],
                free_from_zero=dict(left=round(max(0.0, -env[0]), 1), right=round(max(0.0, env[2]), 1),
                                    up=round(max(0.0, env[3]), 1), down=round(max(0.0, -env[1]), 1)),
                note="Fits the controller's travel only if job zero is placed with this much free travel on each "
                     "side; check cords and run the laser-off travel frame before burning.")


# ---------------------------------------------------------------- per-tin jobs
def shift_job(job: planner.JobPlan, dx: float, dy: float) -> planner.JobPlan:
    """Move a planned (not yet compiled) job by (dx, dy) in the job-zero frame: art, piece and usable area together."""
    g = job.geom
    sh = lambda r: (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)
    job.geom = dataclasses.replace(g, x0=g.x0 + dx, yt=g.yt + dy, piece_rect=sh(g.piece_rect),
                                   usable_rect=sh(g.usable_rect))
    return job


def tin_piece(layout: Layout, i: int, piece: dict) -> dict:
    """Tin i as an ordinary Studio piece: the lid, with job zero as a picked spot outside it, so the lid sits at
    its slot and the layout's one job zero is kept. Editable like any other piece; nothing is injected."""
    if not layout.slots[i].enabled:
        raise ValueError(f"Tin {i + 1} is switched off in this layout.")
    cx, cy = layout.centre(i)
    pc = copy.deepcopy(piece)
    w, h = float(pc["w"]), float(pc["h"])
    zero = "tin 1's centre" if layout.zero == "slot1" else "the layout centre"
    pc.update(origin="spot", spot=(w / 2 - cx, h / 2 - cy),
              name=f"Tin {i + 1} of '{layout.name}' (job zero = {zero})")
    return pc


def slot_job(picture, material, layout: Layout, i: int, piece: dict, art_w: float, look: dict | None = None):
    """Tin i's own checked job, built exactly as Studio builds it after 'Set up this tin'."""
    pc = tin_piece(layout, i, piece)
    pic = imaging.orient(picture, layout.rotation(i), False)
    job = planner.build_job(pic, material, planner.Placement(pc, art_w=art_w, fit="whole"), look=look,
                            name=f"{layout.name} - tin {i + 1}")
    cx, cy = layout.centre(i)
    planner.compile_job(job, start=(cx, cy))
    job.tin = dict(layout=layout.name, index=i, centre=(cx, cy), fingerprint=fingerprint(layout, i, material, art_w))
    return job


def fingerprint(layout: Layout, i: int, material, art_w: float) -> str:
    """Changes whenever anything that moves or changes tin i's burn changes, so a saved job can be refused as stale."""
    m = dataclasses.asdict(material) if dataclasses.is_dataclass(material) else dict(material)
    d = dict(centre=layout.centre(i), rot=layout.rotation(i), pitch=(layout.pitch_x, layout.pitch_y), art_w=art_w,
             material=m)
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


def is_stale(job, layout: Layout, material, art_w: float) -> bool:
    t = getattr(job, "tin", None)
    return t is None or t["fingerprint"] != fingerprint(layout, t["index"], material, art_w)


# ---------------------------------------------------------------- traces
def image_trace(layout: Layout, i: int, piece: dict, n: int = 96) -> list:
    """The true image path for one tin: the usable face circle for a round lid (not its bounding square)."""
    cx, cy = layout.centre(i)
    m = piece.get("margins", (0, 0, 0, 0))
    if piece.get("shape") == "circle":
        r = (piece["w"] - m[0] - m[2]) / 2
        return [(round(cx + r * math.cos(math.tau * k / n), 3), round(cy + r * math.sin(math.tau * k / n), 3))
                for k in range(n + 1)]
    w, h = piece["w"] - m[0] - m[2], piece["h"] - m[1] - m[3]
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2),
            (cx - w / 2, cy - h / 2)]


def travel_trace(job) -> list:
    """The laser-off movement envelope of one built tin job (its verified travel box, run-ups included)."""
    from . import verify
    t = verify.verify_job(job)["travel"]
    return [(t[0], t[1]), (t[2], t[1]), (t[2], t[3]), (t[0], t[3]), (t[0], t[1])]


def traces(layout: Layout, piece: dict, kind: str = "image", indices=None, jobs=None) -> list:
    """Paths for one tin, a selection or all enabled tins, in queue order. kind: 'image' or 'travel'."""
    idx = layout.enabled() if indices is None else [i for i in indices if layout.slots[i].enabled]
    if kind == "image":
        return [image_trace(layout, i, piece) for i in idx]
    if kind == "travel":
        if jobs is None:
            raise ValueError("Travel traces need the built tin jobs.")
        return [travel_trace(jobs[i]) for i in idx]
    raise ValueError("Trace kind must be 'image' or 'travel'.")
