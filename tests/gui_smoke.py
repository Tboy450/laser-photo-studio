"""Scripted GUI smoke test in demo mode (simulated laser; COM4 is never opened). Saves screenshots.
Usage: python tests/gui_smoke.py <screenshot folder>"""
import os
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
PROJECT = Path(os.environ["LASER_PHOTO_STUDIO_TEST_PROJECT"]) if os.getenv("LASER_PHOTO_STUDIO_TEST_PROJECT") else None
PIC = (PROJECT / "outputs/north-pole-mural/operator-design.webp" if PROJECT else
       jobs.APP_DIR / "assets/samples/dragon-source.jpg")
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
    assert pump(app, 30, lambda: app.ready_items()[1][0]), "job not checked"
    ready = [done for done, _, _ in app.ready_items()]
    assert ready[:2] == [True, True] and not any(ready[2:]), ready     # picture + check done, nothing else yet
    app.connect()
    assert pump(app, 10, lambda: app.connected and app.last_status is not None), "demo connect failed"
    app.worker.submit("origin", machine.set_origin_here, 0.0, 0.0)
    assert pump(app, 5, lambda: app.origin_set), "origin not set"
    from tkinter import messagebox
    messagebox.askokcancel = lambda *a, **k: True
    app.run_perimeter("image")
    assert pump(app, 60, lambda: not app.perim_running), "perimeter timed out"
    burns = app.worker.ctrl.burns
    assert burns and all(p[4] == 10 for p in burns), burns
    shot(app, "4-laser")
    assert pump(app, 5, lambda: all(done for done, _, _ in app.ready_items())), app.ready_items()
    app.pages[4].canvas.yview_moveto(0.55)
    pump(app, 0.5)
    shot(app, "4b-ready")
    app.nudge(1, 0)    # moving the picture means the perimeter check has to be run again
    assert pump(app, 30, lambda: not app.ready_items()[4][0] and app.ready_items()[1][0]), app.ready_items()
    app.nudge(None, None)
    app.pages[4].canvas.yview_moveto(0.0)
    # Lining up by clicking the preview (demo laser): 'the dot is here', 'move the head there', then jogging with
    # 'Move the picture with the head' keeps the head's X/Y.
    messagebox.askyesno = lambda *a, **k: True      # the confirmations would wait for a person

    def at(x, y):
        st = app.last_status
        return bool(st and st.wpos and abs(st.wpos[0] - x) < 0.05 and abs(st.wpos[1] - y) < 0.05)
    assert pump(app, 30, lambda: app.ready_items()[1][0]), "re-check after nudging"
    app.click_var.set("here")
    app.preview_clicked(5.0, 4.0, 5.0, 4.0)
    assert at(0, 0) and app.current_observation()
    app.apply_alignment()
    assert pump(app, 10, lambda: at(5.0, 4.0)), app.last_status
    app.click_var.set("goto")
    app.preview_clicked(20.0, 30.0, 20.0, 30.0)
    assert pump(app, 20, lambda: at(20.0, 30.0)), app.last_status
    count = app.origin_count
    app.follow_var.set(True)
    app.jog(1.0, 0.0)
    assert pump(app, 20, lambda: app.origin_count == count + 1), "follow jog"
    assert at(20.0, 30.0), app.last_status
    assert not app.ready_items()[4][0]                # the picture moved: perimeter check needed again
    app.follow_var.set(False)
    app.click_var.set("none")
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
    # Step 3: pick the start point by clicking the picture; the job is re-measured from that spot.
    app.goto(2)
    app.origin_var.set("spot")
    app._piece_edited()
    app.preview_clicked(0.0, 0.0, 30.0, 20.0)
    assert pump(app, 30, lambda: app.job.piece.get("spot") == [30.0, 20.0]), app.job.piece
    assert app.job.geom.piece_rect[:2] == (-30.0, -20.0), app.job.geom.piece_rect
    assert not app.origin_set                       # the controller's start point is now out of date
    shot(app, "2b-picked-start-point")
    # Toy car: the window shows a scaled top view; another body type refills the numbers; 'Use this car' sets the piece.
    from lps import presets
    from lps.dialogs import CarDialog
    d = CarDialog(root, presets.car_values("mustang"), wait=False)
    d.geometry("+60+60")
    pump(app, 0.8)
    grab(d, "2c-toy-car")
    d.body_box.current(d.body_keys.index("pickup"))
    d._body_picked()
    assert d.values()["length"] == 78.0 and d.values()["front"] == "right", d.values()
    d.destroy()
    app.use_car(presets.car_values("mustang"))
    assert pump(app, 30, lambda: app.job.piece.get("name", "").startswith("Toy car")), "car job"
    shot(app, "2d-toy-car-piece")
    app.zone_edit_var.set(True)
    app.select_keepout(0)
    app.preview.refresh()
    app.pages[2].canvas.yview_moveto(0.43)
    pump(app, .5)
    shot(app, "2d-editable-windshield")
    app.pages[2].canvas.yview_moveto(0.0)
    app.zone_edit_var.set(False)
    # Exact size: the box is what you type, and the perimeter is that box.
    app.pw_var.set("14")
    app.exact_var.set(True)
    app._exact_toggled((14.0, 19.0))
    assert pump(app, 30, lambda: app.job.geom.art_w == 14.0 and app.job.geom.art_h == 19.0), app.job.geom
    assert app.picture_box() == (0.0, 0.0, 14.0, 19.0), app.picture_box()
    assert "14 x 19 mm" in app.box_lbl.cget("text"), app.box_lbl.cget("text")
    shot(app, "2e-exact-size")
    roof = PROJECT / 'outputs/mazda-rx7-2026-11-05/sized/01-roof-14x19-IMPORT.png' if PROJECT else None
    if roof and roof.exists():
        app.open_picture(roof)
        app.v_neg.set(False)
        app.changed(0)
        assert pump(app,30,lambda: not app.layout_pending and app.picture_box()==(0.,0.,14.,19.)), 'roof box'
        pump(app,.4)
        shot(app,'2f-actual-roof-14x19')
    app.use_car(presets.car_values("mustang"))
    assert pump(app, 30, lambda: app.job.piece.get("name", "").startswith("Toy car")), "back to the car"
    # The grid follows the zoom: finer on the small car than on the plank; it can be switched off.
    cv = app.preview.canvas
    assert app.preview.grid_mm and app.preview.grid_mm <= 10 and cv.find_withtag("grid"), app.preview.grid_mm
    assert any(t.startswith("grid:") for _, _, t in app.preview._key_items), app.preview._key_items
    app.preview.grid_on.set(False)
    app.preview._grid_toggled()
    assert not cv.find_withtag("grid") and not jobs.load_settings()["grid"]
    app.preview.grid_on.set(True)
    app.preview._grid_toggled()
    app.goto(3)     # the check runs from step 4
    assert pump(app, 30, lambda: app.report is not None and app.compiled_gen == app.gen), "car check"
    assert app.report["ok"] and len(app.job.piece["keepouts"]) == 2, app.report
    # Every colour theme switches live on the running app, and the choice is remembered.
    from lps.ui_common import COLORS, THEMES
    app.goto(1)
    app.pages[1].canvas.yview_moveto(0.0)
    for name in THEMES:
        app.set_theme(name)
        pump(app, 0.6)
        assert COLORS["ink"] == THEMES[name]["ink"] and app.preview.canvas.cget("background") == COLORS["canvas"]
        assert jobs.load_settings()["theme"] == name
        cv = app.preview.canvas
        fills = {cv.itemcget(i, "fill") for i in cv.find_withtag("grid") if cv.type(i) == "line"}
        assert COLORS["grid"] in fills and "#ffffff" not in fills - {COLORS["grid"], COLORS["grid_back"]}, (name, fills)
        shot(app, f"7-theme-{name}")
    app.goto(4)
    app.set_theme("dragonfly")
    app.pages[4].canvas.yview_moveto(0.0)
    pump(app, 0.6)
    shot(app, "7b-dragonfly-laser")
    app.set_theme("light")
    # Start a short demo job (the plank job would take long even simulated): only check that it launches.
    print("OK", folder)
    root.destroy()


if __name__ == "__main__":
    main()
