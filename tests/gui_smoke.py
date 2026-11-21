"""Scripted GUI smoke test in demo mode (simulated laser; COM4 is never opened). Saves screenshots.
Usage: python tests/gui_smoke.py <screenshot folder>"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from lps import jobs, machine  # noqa: E402
from lps.app import App  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
PIC = Path(r"C:\Users\Heemi\Documents\Codex\2026-10-25\got\outputs\north-pole-mural\operator-design.webp")
real_serial = machine.SerialWire.open


def forbid(*a, **k):
    raise AssertionError("the smoke test must never open a real serial port")


machine.SerialWire.open = forbid
TMP = OUT / "data"
jobs.JOBS_DIR = TMP / "Jobs"
jobs.SETTINGS_FILE = TMP / "settings.json"
jobs.LOCK_FILE = TMP / "sender.lock"
import lps.app_laser as _al  # noqa: E402
_al.DEMO_STATE = TMP / "demo-state.json"


def pump(app, seconds, until=None):
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        if until and until():
            return True
        time.sleep(0.02)
    return False


def shot(app, name):
    r = app.root
    r.attributes("-topmost", True)
    r.lift()
    r.update()
    time.sleep(0.5)
    r.update()
    x, y, w, h = r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(OUT / f"{name}.png")
    r.attributes("-topmost", False)


def grab(win, name):
    win.attributes("-topmost", True)
    win.update()
    time.sleep(0.5)
    win.update()
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(OUT / f"{name}.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = App(root, SimpleNamespace(demo=True, picture=None, perimeter=None))
    root.geometry("1380x880+20+20")
    pump(app, 1.0)
    shot(app, "0-start")
    app.open_picture(str(PIC))
    assert pump(app, 20, lambda: app.job is not None), "build timed out"
    app.goto(1)
    pump(app, 0.5)
    shot(app, "1-material")
    # Photos under 'About this setting': thumbnails, then the viewer.
    strip = app.sample_strip
    assert len(strip.items) >= 6 and len(strip._refs) == 6, (len(strip.items), len(strip._refs))
    app.pages[1].canvas.yview_moveto(0.22)
    pump(app, 0.8)
    shot(app, "1a-material-photos")
    strip.open(3)
    pump(app, 1.0)
    v = strip.viewer
    v.geometry("1100x840+60+30")
    pump(app, 0.8)
    grab(v, "6-photo-viewer")
    v.step(1)
    pump(app, 0.3)
    assert v.i == 4, v.i
    v.destroy()
    app.pages[1].canvas.yview_moveto(0.0)
    app.goto(2)
    pump(app, 0.5)
    shot(app, "2-size")
    app.goto(3)
    assert pump(app, 30, lambda: app.report is not None and app.compiled_gen == app.gen), "check timed out"
    assert app.report["ok"], app.report
    assert app.btn_export.cget("text") == "Export G-code (.nc)..."
    assert not hasattr(app, "btn_lgrbl")
    assert hasattr(app, "export_gcode")
    shot(app, "3-check")
    folder = app.save_current_job(quiet=True)
    assert folder and jobs.lasergrbl_path(folder).exists()
    app.open_help("Negative & previews")
    pump(app, 1.0)
    hw = app.help_win
    hw.geometry("1000x720+60+60")
    pump(app, 0.5)
    hw.attributes("-topmost", True)
    hw.update()
    time.sleep(0.5)
    x, y, w, h = hw.winfo_rootx(), hw.winfo_rooty(), hw.winfo_width(), hw.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(OUT / "5-guide.png")
    hw.destroy()
    app.goto(4)
    app.connect()
    assert pump(app, 10, lambda: app.connected and app.last_status is not None), "demo connect failed"
    app.worker.submit("origin", machine.set_origin_here, 0.0, 0.0)
    assert pump(app, 5, lambda: app.origin_set), "origin not set"
    pts = __import__("lps.planner", fromlist=["x"]).perimeter_points(app.job.burn_bbox())
    app.perim_points = pts
    app.perim_running = True
    app.worker.submit("perimeter", machine.perimeter_check, pts, 1, 6000, cancel=app.worker.cancel,
                      progress=lambda i, n, name, what: app.events.put(("perim", i, n, name, what)))
    assert pump(app, 60, lambda: not app.perim_running), "perimeter timed out"
    pulses = app.worker.ctrl.pulses
    assert len(pulses) == 4 and all(p[2] == 10 for p in pulses), pulses
    shot(app, "4-laser")
    # Material card explanations: internal settings and the energy readout after slowing down.
    app.select_material("anodized-dots")
    var, _ = app.adv_vars["feed"]
    var.set("1800")
    app._adv_changed()
    assert "1.39x" in app.energy_lbl.cget("text"), app.energy_lbl.cget("text")
    assert "Power 50 %" in app.m_settings.cget("text"), app.m_settings.cget("text")
    assert "S500" in app.m_technical.cget("text"), app.m_technical.cget("text")
    app.preview.view.set("toolpath")
    app.preview.refresh()
    pump(app, 0.2)
    assert app.preview.view.get() == "toolpath"
    assert "planned" in app.preview.legend.cget("text").lower()
    app.goto(1)
    pump(app, 1.0)
    app.pages[1].canvas.yview_moveto(0.40)
    shot(app, "1b-material-explained")
    # Start a short demo job (the plank job would take long even simulated): only check that it launches.
    print("OK", folder)
    root.destroy()


if __name__ == "__main__":
    main()
