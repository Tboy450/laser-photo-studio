"""Job folders: every job is saved before anything runs, with LaserGRBL-compatible G-code files.

%LOCALAPPDATA%/Laser Photo Studio/Jobs/<date>_<name>/
    job.json                  settings, passes (+ SHA-256 of each file), placement, check results
    passes/01 Layer 1.nc ...  one file per pass; the runner burns exactly the lines between the BODY markers
    <name> - all passes.nc    everything in one file (for LaserGRBL, no photo pauses)
    1 LOOKS LIKE ... .png etc previews, README.txt
    state.json                live progress written by the runner (also the recovery record)
    control.json              pause / resume / stop / continue requests from the app
    log.txt, photos/
"""
from __future__ import annotations

import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .planner import JobPlan
from .presets import BADGES, DATA_DIR, STYLES

JOBS_DIR = DATA_DIR / "Jobs"
LOCK_FILE = DATA_DIR / "sender.lock"
SETTINGS_FILE = DATA_DIR / "settings.json"
APP_DIR = Path(__file__).resolve().parents[1]
BEGIN, END = "; BEGIN BODY", "; END BODY"


def safe_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9 _.-]+", "", s).strip().replace(" ", "-")
    return (s or "job")[:40]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, data) -> None:
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_settings() -> dict:
    d = dict(port="COM4", baud=115200, phone_folder=str(Path.home() / "Downloads" / "Mobile Devices"),
             lasergrbl=r"C:\Program Files (x86)\LaserGRBL\LaserGRBL.exe", pulses=3, perimeter_feed=1500,
             perimeter_spacing=0.0, pause_between_layers=True)
    d.update(read_json(SETTINGS_FILE, {}) or {})
    return d


def save_settings(d: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    write_json(SETTINGS_FILE, d)


def origin_text(piece: dict) -> str:
    if piece.get("origin") == "center":
        return "centre of the piece"
    if piece.get("origin") == "spot":
        ax, ay = piece.get("spot") or (0.0, 0.0)
        return (f"spot you picked, {ax:g} mm from the piece's left edge and {ay:g} mm up from its bottom edge "
                "(the Job zero crosshair)")
    return "lower-left corner of the piece"


def header(job: JobPlan, title: str) -> list:
    m, g = job.material, job.geom
    style = STYLES.get(m.style, {}).get("name", m.style)
    return [f"; Laser Photo Studio {__version__} - {job.name}",
            f"; {title}",
            f"; Material: {m.name} [{BADGES.get(m.badge, m.badge)}] | {style} | rows {m.pitch} mm | Look: {m.look}",
            f"; Start point (origin): work X0 Y0 = {origin_text(job.piece)}. Art X{g.x0:.2f}..{g.x1:.2f} "
            f"Y{g.y0:.2f}..{g.yt:.2f} mm. Check the perimeter before burning.",
            f"; Picture box [mm]: X{g.x0:.3f} Y{g.y0:.3f} W{g.art_w:.3f} H{g.art_h:.3f}",
            f"; Burn grid: C{g.cols} R{g.rows} DX{g.x_pitch:.9f} DY{g.y_pitch:.9f}",
            "; Scan direction: " + ("alternating rows" if m.scan_direction == "alternating" else
                                     "left to right only; returns with laser off"),
            f"; Laser-off row return: {m.row_feed} mm/min; feature hops: {m.hop_feed} mm/min",
            "; Fast blank scan-line gaps: " + ("ON (experimental); S0 gaps >=1 mm use faster return feed"
                                                if m.fast_blank_gaps else "OFF"),
            "; M4 dynamic power, S1000 = 100% ($30=1000). Laser-off travel is G1 S0. Never home this machine."]


def pass_text(job: JobPlan, p, i: int, n: int) -> str:
    s_vals = sorted({int(v) for v in set(p.cells.ravel().tolist()) if v}) if p.cells.any() else []
    title = f"Pass {i}/{n}: {p.title} - {p.explain} | power S{s_vals[0] if s_vals else 0}-S{s_vals[-1] if s_vals else 0}"
    lines = header(job, title) + ["M5 S0", "G21 G90 G94 G54", BEGIN] + p.commands + \
        [END, "M5 S0", "G1 X0.000 Y0.000 F3000 S0", "M5 S0"]
    return "\n".join(lines) + "\n"


def all_text(job: JobPlan) -> str:
    lines = header(job, f"All {len(job.passes)} passes in one file (no photo pauses)") + ["M5 S0", "G21 G90 G94 G54"]
    for i, p in enumerate(job.passes, 1):
        lines += [f"; ---- pass {i}: {p.title} - {p.explain}"] + p.commands
    lines += ["M5 S0", "G1 X0.000 Y0.000 F3000 S0", "M5 S0"]
    return "\n".join(lines) + "\n"


def read_body(path: Path) -> list:
    text = Path(path).read_text(encoding="ascii").splitlines()
    a, b = text.index(BEGIN), text.index(END)
    return text[a + 1:b]


def pass_filename(i: int, p) -> str:
    return f"{i:02d} {re.sub(r'[^A-Za-z0-9 ]+', '', p.title).strip() or p.key}.nc"


def lasergrbl_name(job: JobPlan) -> str:
    return f"{safe_name(job.name)} - all passes.nc"


def lasergrbl_path(folder: Path) -> Path:
    """The single-file version of a saved job, for LaserGRBL."""
    doc = read_json(Path(folder) / "job.json", {}) or {}
    return Path(folder) / doc.get("lasergrbl_file", "all-passes.nc")


def readme_text(job: JobPlan, negative: bool) -> str:
    m, g = job.material, job.geom
    style = STYLES.get(m.style, {}).get("name", m.style)
    neg = ("Test patches (no picture): each patch burns at its own power and speed; see the ladder map."
           if job.gray is None else
           "Negative was ON: the LIGHT parts of the picture are burned. Right for materials that mark light "
           "(black anodized aluminum, slate, black acrylic) when engraving a photo."
           if negative else
           "Negative was OFF: the DARK parts of the picture are burned (normal for wood and dark-marking materials, "
           "and for black-on-white artwork that should be marked as drawn).")
    first = pass_filename(1, job.passes[0]) if job.passes else "01 ....nc"
    return f"""Laser Photo Studio {__version__} job: {job.name}
Material: {m.name} [{BADGES.get(m.badge, m.badge)}]   Style: {style}
Scan direction: {'Alternating rows' if m.scan_direction == 'alternating' else 'Left to right only (laser-off returns)'}
Laser-off row return: {m.row_feed} mm/min; feature hops: {m.hop_feed} mm/min
Fast blank scan-line gaps: {'ON (experimental): S0 gaps >=1 mm use the faster return speed' if m.fast_blank_gaps else 'OFF'}
Art: {g.art_w:.1f} x {g.art_h:.1f} mm at X {g.x0:.2f}..{g.x1:.2f}, Y {g.y0:.2f}..{g.yt:.2f} mm from the start point
Start point (origin, work X0 Y0): {origin_text(job.piece)}
{neg}

FILES
passes\\{first} ...    One file per pass, in order. Best run from Laser Photo Studio (step 5): photo pauses
                         after each pass and safe recovery if the USB drops out.
{lasergrbl_name(job)}
                         Everything in one file, for LaserGRBL (no photo pauses).
1 LOOKS LIKE ....png     Roughly how the finished piece should look on the material. NOT a laser input.
2 LASER INPUT ....png    Black = where the laser fires (darker = more power), white = untouched. 1 pixel = 1 dot
                         ({m.pitch} mm). Same convention LaserGRBL uses when it imports a picture, and the same
                         as the project's *-IMPORT.png files. The .nc files already contain it.
3 IN LASERGRBL ....png   How LaserGRBL's preview will draw the .nc: light lines on a dark background where the
                         laser fires, brighter = more power (its default dark theme). LaserGRBL does NOT invert
                         anything when it opens a .nc, so wood jobs look like a negative there, while
                         light-marking materials (anodized, slate) look like the real result.
4 burn map ....png       Each pass in its own colour.

LASERGRBL TIPS
- Open the .nc with File > Open. Don't import the PNGs and don't press LaserGRBL's invert (negative) button:
  the conversion is already done.
- Put the head on the start point above and check the frame/perimeter first.
- If the USB drops out in LaserGRBL, don't use its Resume or Home - it can jump to old coordinates. Jobs run
  from Laser Photo Studio record reported positions and command progress for checked recovery. Sent/accepted
  commands do not by themselves prove completed motion.
"""


def save_job(job: JobPlan, report: dict, picture=None, previews: dict | None = None, extra: dict | None = None,
             folder: Path | None = None) -> Path:
    folder = folder or JOBS_DIR / f"{dt.datetime.now():%Y-%m-%d_%H%M%S}_{safe_name(job.name)}"
    (folder / "passes").mkdir(parents=True, exist_ok=True)
    (folder / "photos").mkdir(exist_ok=True)
    passes = []
    for i, p in enumerate(job.passes, 1):
        f = folder / "passes" / pass_filename(i, p)
        f.write_text(pass_text(job, p, i, len(job.passes)), encoding="ascii")
        assert read_body(f) == p.commands
        passes.append(dict(key=p.key, title=p.title, explain=p.explain, file=f"passes/{f.name}", sha256=sha256(f),
                           commands=len(p.commands), est_s=round(p.est_s, 1), cells=int((p.cells > 0).sum()),
                           kind=p.kind, **(dict(spots=p.spots, cool_s=p.cool_s) if p.kind == "dwell" else
                                           dict(lines=p.lines) if p.kind == "crawl" else {})))
    (folder / lasergrbl_name(job)).write_text(all_text(job), encoding="ascii")
    if picture is not None:
        picture.save(folder / "picture.png")
    for name, im in (previews or {}).items():
        im.save(folder / f"{name}.png")
    g = job.geom
    travel = report.get("travel") or (g.x0, g.y0, g.x1, g.yt)
    env = [round(min(travel[0], 0.0) - 1.0, 2), round(min(travel[1], 0.0) - 1.0, 2),
           round(max(travel[2], 0.0) + 1.0, 2), round(max(travel[3], 0.0) + 1.0, 2)]
    doc = dict(app="Laser Photo Studio", version=__version__, created=dt.datetime.now().isoformat(timespec="seconds"),
               name=job.name, material=asdict(job.material), piece=job.piece,
               geometry=dict(pitch=g.pitch, x_pitch=g.x_pitch, y_pitch=g.y_pitch,
                             cols=g.cols, rows=g.rows, x0=g.x0, yt=g.yt, piece_rect=g.piece_rect,
                             usable_rect=g.usable_rect),
               burn_bbox=job.burn_bbox(), travel=travel, envelope=env, passes=passes,
               picture_bbox=[g.x0, g.y0, g.x1, g.yt],
               verified=bool(report.get("ok")), est_s=round(job.est_s, 1),
               origin=origin_text(job.piece), lasergrbl_file=lasergrbl_name(job))
    doc.update(extra or {})
    if picture is not None:
        doc['editable_picture'] = dict(file='picture.png', sha256=sha256(folder / 'picture.png'),
                                      orientation='already applied; tone/dither not applied')
    write_json(folder / "job.json", doc)
    (folder / "README.txt").write_text(readme_text(job, bool((extra or {}).get("look", {}).get("negative"))),
                                      encoding="utf-8")
    return folder


# ---------------------------------------------------------------------------------------- processes and locks
def pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000 | 0x100000, False, int(pid))
    if not h:
        return False
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259


def active_runner():
    info = read_json(LOCK_FILE)
    if info and pid_alive(info.get("pid", 0)):
        return info
    return None


def running_processes(names=("LaserGRBL.exe", "Positioning Laser.exe")) -> list:
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        name = line.split('","')[0].strip('"')
        if name.lower() in {n.lower() for n in names}:
            found.append(name)
    return sorted(set(found))


def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def launch_runner(folder: Path, spec: dict) -> int:
    """Start the job in its own detached process, so closing the app doesn't stop the laser."""
    spec = dict(spec)
    old = read_json(folder / "control.json", {}) or {}
    spec["control_seq"] = int(old.get("seq", 0))
    write_json(folder / "run.json", spec)
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    p = subprocess.Popen([pythonw(), "-m", "lps.runner", str(folder)], cwd=str(APP_DIR), creationflags=flags,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True)
    return p.pid


def send_control(folder: Path, cmd: str) -> None:
    cur = read_json(folder / "control.json", {}) or {}
    write_json(folder / "control.json", dict(seq=int(cur.get("seq", 0)) + 1, cmd=cmd,
                                             at=dt.datetime.now().isoformat(timespec="seconds")))


def latest_jobs(limit: int = 30) -> list:
    if not JOBS_DIR.exists():
        return []
    items = [p for p in JOBS_DIR.iterdir() if (p / "job.json").exists()]
    return sorted(items, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


# ---------------------------------------------------------------------------------------- LaserGRBL
def find_lasergrbl(configured: str = "") -> str | None:
    for c in (configured, r"C:\Program Files (x86)\LaserGRBL\LaserGRBL.exe", r"C:\Program Files\LaserGRBL\LaserGRBL.exe",
              str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LaserGRBL" / "LaserGRBL.exe")):
        if c and Path(c).exists():
            return c
    return None


def open_in_lasergrbl(path: Path, exe: str) -> None:
    """LaserGRBL opens a single file passed on its command line (MainForm.ManageCommandLineArgs)."""
    subprocess.Popen([exe, str(path)], cwd=str(Path(exe).parent), close_fds=True)
