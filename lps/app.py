"""Laser Photo Studio - main window: steps 1-2 and the shared plumbing (background builds, events)."""
from __future__ import annotations

import argparse
import copy
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, gcodeinfo, helptext, imaging, jobs, planner, presets, verify
from .app_laser import LaserMixin
from .app_place import PlaceMixin
from .dialogs import FormDialog, TestGridDialog
from .preview import PreviewPanel
from .presets import BADGES, PIECES, STYLES
from .sample_view import SampleStrip
from .ui_common import COLORS, ScrollFrame, badge, link, setup_style, wrap_label

GROUPS = (("PROVEN", "Proven on your U20"), ("START", "Starting points - test first"),
          ("EXPERIMENTAL", "Experimental - test first"), ("MINE", "My presets"))
STYLE_KEYS = list(STYLES)


class App(PlaceMixin, LaserMixin):
    def __init__(self, root: tk.Tk, args):
        self.root = root
        root.title(f"Laser Photo Studio {__version__}  -  Tronxy Ultrabot U20")
        root.geometry("1380x880")
        root.minsize(1120, 720)
        setup_style(root)
        root.configure(background=COLORS["bg"])
        ico = jobs.APP_DIR / "assets" / "icon.ico"
        if ico.exists():
            try:
                root.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self.settings = jobs.load_settings()
        self.materials = presets.load_materials()
        self.mat = self.base_mat = self.materials[0]
        self.help_win = None
        self.picture = self.picture_raw = self.picture_path = None
        self.rotate, self.mirror = 0, False
        self.piece_key = self.mat.piece or "custom"
        self.piece = copy.deepcopy(PIECES[self.piece_key])
        self.piece_user_set = False
        self.art_w = None
        self.dx = self.dy = 0.0
        self.grid_spec = None
        self.job = None
        self.gen = 0
        self.report = None
        self.compiled_gen = -1
        self.saved = {}
        self.gfile = None
        self.events: queue.Queue = queue.Queue()
        self.event_hooks = []
        self.perim_points, self.perim_idx = [], None
        self._build_after = None
        self._loading = False
        self.init_machine_state()
        self._build_ui()
        self.select_material(self.mat.key)
        self.root.after(60, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_laser_loops()
        if args.demo:
            self.demo.set(True)
        if args.picture:
            self.root.after(200, lambda: self.open_picture(args.picture))
        if args.perimeter is not None:
            self.root.after(250, lambda: self.perimeter_mode(args.perimeter or None))

    # ================================================================ layout
    def _build_ui(self):
        top = tk.Frame(self.root, background="#2b2622", height=48)
        top.pack(fill="x")
        tk.Label(top, text="  Laser Photo Studio", fg="#ffffff", bg="#2b2622",
                 font=("Segoe UI", 15, "bold")).pack(side="left", pady=8)
        tk.Label(top, text="picture -> checked G-code -> safe runs on your Tronxy U20", fg="#cbbfb2",
                 bg="#2b2622").pack(side="left", padx=10)
        ttk.Button(top, text="Settings", command=self.open_settings).pack(side="right", padx=(4, 10))
        ttk.Button(top, text="Guide", command=lambda: self.open_help()).pack(side="right", padx=4)
        self.pill = tk.Label(top, text=" Not connected ", bg="#6b7280", fg="white", font=("Segoe UI", 10, "bold"),
                             padx=8, pady=3)
        self.pill.pack(side="right", padx=6)
        pw = ttk.PanedWindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw, width=470)
        self.nb = ttk.Notebook(left)
        self.nb.pack(fill="both", expand=True, padx=(8, 0), pady=8)
        self.pages = []
        for name in ("1 Picture", "2 Material", "3 Size", "4 Check", "5 Laser"):
            sf = ScrollFrame(self.nb)
            self.nb.add(sf, text=name)
            self.pages.append(sf)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        pw.add(left, weight=0)
        self.preview = PreviewPanel(pw, self)
        pw.add(self.preview, weight=1)
        self.root.after(150, lambda: pw.sashpos(0, int(self.root.winfo_fpixels("5.6i"))))
        self.statusbar = tk.Label(self.root, anchor="w", bg="#e7e2da", fg=COLORS["ink"], padx=10, pady=4)
        self.statusbar.pack(fill="x", side="bottom")
        self._page_picture(self.pages[0].inner)
        self._page_material(self.pages[1].inner)
        self.page_place(self.pages[2].inner)
        self.page_check(self.pages[3].inner)
        self.page_laser(self.pages[4].inner)
        self.say("Welcome! Step 1: open a picture. Or open a G-code file to check where it will burn.")

    def say(self, text, kind="info"):
        col = {"info": COLORS["ink"], "ok": COLORS["ok"], "warn": COLORS["warn"], "bad": COLORS["bad"]}[kind]
        self.statusbar.configure(text=text, fg=col)

    def goto(self, index):
        self.nb.select(index)

    def _next(self, parent, text, index):
        ttk.Button(parent, text=text, command=lambda: self.goto(index)).pack(anchor="e", pady=(16, 4))

    # ================================================================ step 1
    def _page_picture(self, f):
        ttk.Label(f, text="1. Pick a picture", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Photos, drawings or logos. Phone photos (HEIC) work too. Tip: drag a picture onto the "
                      "desktop icon to open it straight away.", style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        ttk.Button(f, text="Open picture...", style="Big.TButton", command=self.open_picture).pack(anchor="w")
        self.pic_info = wrap_label(f, "No picture yet.")
        self.pic_info.pack(anchor="w", pady=(8, 4))
        box = ttk.LabelFrame(f, text="Is it the right way up?", style="Card.TLabelframe")
        box.pack(fill="x", pady=8)
        wrap_label(box, "Phone photos are often rotated. Turn it until the preview looks right.",
                   style="Small.TLabel").pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(anchor="w", pady=(6, 0))
        ttk.Button(row, text="Turn left", command=lambda: self.turn(-1)).pack(side="left")
        ttk.Button(row, text="Turn right", command=lambda: self.turn(1)).pack(side="left", padx=6)
        ttk.Button(row, text="Mirror", command=self.flip).pack(side="left")
        g = ttk.LabelFrame(f, text="Already have a G-code file?", style="Card.TLabelframe")
        g.pack(fill="x", pady=8)
        wrap_label(g, "Check the burn area of an existing .nc job (from any compatible source), "
                      "with the 1% dot perimeter check.", style="Small.TLabel").pack(anchor="w")
        ttk.Button(g, text="Open G-code for a perimeter check...", command=lambda: self.perimeter_mode(None)).pack(
            anchor="w", pady=(6, 0))
        self._next(f, "Next: material  >", 1)

    def open_picture(self, path=None):
        path = path or filedialog.askopenfilename(
            title="Open a picture", filetypes=[("Pictures", " ".join("*" + e for e in imaging.PICTURE_TYPES)),
                                               ("All files", "*.*")])
        if not path:
            return
        if Path(path).suffix.lower() in (".nc", ".gcode", ".gc", ".ngc", ".tap", ".txt"):
            self.perimeter_mode(path)
            return
        try:
            self.picture_raw = imaging.load_picture(path)
        except Exception as e:
            messagebox.showerror("Can't open picture", f"{Path(path).name}\n\n{e}")
            return
        self.picture_path = Path(path)
        self.rotate, self.mirror = 0, False
        self.grid_spec = None
        self.gfile = None
        self.dx = self.dy = 0.0
        self.art_w = None
        self._apply_orientation()
        self.say(f"Opened {self.picture_path.name}. Step 2: choose the material.", "ok")

    def turn(self, d):
        if self.picture_raw is None:
            return
        self.rotate = (self.rotate + d) % 4
        self.art_w = None
        self._apply_orientation()

    def flip(self):
        if self.picture_raw is None:
            return
        self.mirror = not self.mirror
        self._apply_orientation()

    def _apply_orientation(self):
        self.picture = imaging.orient(self.picture_raw, self.rotate, self.mirror)
        w, h = self.picture.size
        self.pic_info.configure(text=f"{self.picture_path.name}  -  {w} x {h} pixels"
                                     f"{'  (turned)' if self.rotate else ''}{'  (mirrored)' if self.mirror else ''}")
        self.sync_place_fields()
        self.changed()

    # ================================================================ step 2
    def _page_material(self, f):
        ttk.Label(f, text="2. Material & print style", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Green = proven on your machine. Yellow = good starting points from other 20 W lasers - "
                      "run a test grid first.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        self.tree = ttk.Treeview(f, show="tree", height=12, selectmode="browse")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._tree_pick)
        self._fill_tree()
        card = ttk.LabelFrame(f, text="About this setting", style="Card.TLabelframe")
        card.pack(fill="x", pady=8)
        self.m_badge = badge(card, "PROVEN", "")
        self.m_badge.pack(anchor="w")
        self.m_name = wrap_label(card, "", style="H2.TLabel")
        self.m_name.pack(anchor="w", pady=(4, 0))
        self.m_summary = wrap_label(card, "")
        self.m_summary.pack(anchor="w", pady=(4, 2))
        self.sample_strip = SampleStrip(card, self)
        self.sample_strip.pack(fill="x", pady=(6, 6))
        self.m_notes = wrap_label(card, "", style="Small.TLabel")
        self.m_notes.pack(anchor="w")
        self.m_settings = wrap_label(card, "", style="Muted.TLabel")
        self.m_settings.pack(anchor="w", pady=(4, 0))
        lr = ttk.Frame(card)
        lr.pack(anchor="w", pady=(4, 0))
        link(lr, "Too light or too dark?", lambda: self.open_help("Too light or too dark?")).pack(side="left")
        st = ttk.LabelFrame(f, text="Print style", style="Card.TLabelframe")
        st.pack(fill="x", pady=4)
        self.style_var = tk.StringVar()
        self.style_box = ttk.Combobox(st, textvariable=self.style_var, state="readonly", width=40,
                                      values=[STYLES[k]["name"] for k in STYLE_KEYS])
        self.style_box.pack(anchor="w")
        self.style_box.bind("<<ComboboxSelected>>", self._style_pick)
        self.style_help = wrap_label(st, "", style="Small.TLabel")
        self.style_help.pack(anchor="w", pady=(4, 0))
        link(st, "Compare all print styles", lambda: self.open_help("Print styles")).pack(anchor="w", pady=(4, 0))
        adv = ttk.LabelFrame(f, text="Adjust settings (optional)", style="Card.TLabelframe")
        adv.pack(fill="x", pady=4)
        self.adv_vars = {}
        grid = ttk.Frame(adv)
        grid.pack(fill="x")
        fields = [("feed", "Speed (mm/min)", 100, 6000, 50), ("power", "Power (%)", 1, 100, 1),
                  ("power_min", "Lightest power (%) - grayscale", 0, 100, 1),
                  ("tp1", "Layer power light (%)", 1, 100, 1), ("tp2", "Layer power mid (%)", 1, 100, 1),
                  ("tp3", "Layer power dark (%)", 1, 100, 1), ("pitch", "Row spacing (mm)", 0.05, 0.5, 0.01),
                  ("passes", "Repeat passes", 1, 3, 1), ("interlace", "Cooling row groups (1 = off)", 1, 5, 1),
                  ("halftone_cell", "Halftone dot spacing (mm)", 0.2, 2.0, 0.1), ("runup", "Run-up (mm)", 0.5, 15, 0.1)]
        for i, (k, label, lo, hi, inc) in enumerate(fields):
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=1)
            v = tk.StringVar()
            sp = ttk.Spinbox(grid, from_=lo, to=hi, increment=inc, textvariable=v, width=8,
                             command=self._adv_changed)
            sp.grid(row=i, column=1, sticky="e", padx=(8, 0))
            sp.bind("<FocusOut>", lambda e: self._adv_changed())
            sp.bind("<Return>", lambda e: self._adv_changed())
            self.adv_vars[k] = (v, sp)
        self.energy_lbl = wrap_label(adv, "", style="Small.TLabel")
        self.energy_lbl.pack(anchor="w", pady=(6, 0))
        self.rule_var = tk.StringVar()
        self.rule_box = ttk.Combobox(adv, textvariable=self.rule_var, state="readonly", width=44, values=[
            "Plank recipe: all tones, all -0.1 mm, darks -0.2 mm", "Tone by layer count: light 1, mid 2, dark 3"])
        self.rule_box.pack(anchor="w", pady=(6, 0))
        self.rule_box.bind("<<ComboboxSelected>>", lambda e: self._adv_changed())
        self.thin_var = tk.BooleanVar()
        ttk.Checkbutton(adv, text="Thin-line pass for lettering (max 30%)", variable=self.thin_var,
                        command=self._adv_changed).pack(anchor="w", pady=(4, 0))
        row = ttk.Frame(adv)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="Save as my preset...", command=self.save_preset).pack(side="left")
        self.del_btn = ttk.Button(row, text="Delete my preset", command=self.delete_preset)
        self.del_btn.pack(side="left", padx=6)
        ttk.Button(f, text="Make a test grid for a new material...", command=self.test_grid).pack(anchor="w",
                                                                                               pady=(10, 0))
        self._next(f, "Next: size & placement  >", 2)

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for kind, title in GROUPS:
            items = [m for m in self.materials if m.badge == kind]
            if not items:
                continue
            gid = self.tree.insert("", "end", text=title, open=True)
            for m in items:
                self.tree.insert(gid, "end", iid=f"m:{m.key}", text=m.name)

    def _tree_pick(self, _=None):
        sel = self.tree.selection()
        if sel and sel[0].startswith("m:") and not self._loading and sel[0][2:] != self.mat.key:
            self.select_material(sel[0][2:])

    def select_material(self, key):
        m = next((x for x in self.materials if x.key == key), None)
        if m is None:
            return
        self.mat = self.base_mat = m
        self._loading = True
        try:
            if self.tree.exists(f"m:{key}") and self.tree.selection() != (f"m:{key}",):
                self.tree.selection_set(f"m:{key}")
                self.tree.see(f"m:{key}")
            if not self.piece_user_set and m.piece and m.piece in PIECES and self.picture is not None:
                self.set_piece(m.piece, user=False)
            elif not self.piece_user_set and m.piece in PIECES and self.picture is None:
                self.set_piece(m.piece, user=False)
            self.reset_look_from_material()
            self._show_material()
        finally:
            self._loading = False
        self.changed()

    def _show_material(self):
        m = self.mat
        self.m_name.configure(text=m.name)
        bg, fg = {"PROVEN": ("#dcfce7", "#166534"), "START": ("#fef3c7", "#92400e"),
                  "EXPERIMENTAL": ("#fee2e2", "#991b1b"), "MINE": ("#dbeafe", "#1e40af")}[m.badge]
        self.m_badge.configure(text=f" {BADGES[m.badge]} ", background=bg, foreground=fg)
        self.m_summary.configure(text=m.summary)
        self.sample_strip.show(m)
        self.m_notes.configure(text="\n".join("- " + n for n in m.notes))
        s = STYLES[m.style]
        if m.style == "layers":
            pw = "/".join(f"{p / 10:g}" for p in m.tone_power) + " %"
        elif m.style == "grayscale":
            pw = f"{m.power_min / 10:g}-{m.power / 10:g} %"
        else:
            pw = f"{m.power / 10:g} %"
        self.m_settings.configure(text=f"Power {pw}  |  speed {m.feed} mm/min  |  rows {m.pitch} mm  |  "
                                       f"{len(m.layer_rule) if m.style == 'layers' else m.passes} "
                                       f"{'layers' if m.style == 'layers' else 'pass(es)'}")
        self.style_var.set(s["name"])
        self.style_help.configure(text=f"{s['what']} {s['why']}\nBest for: {s['best']}")
        base = self.base_mat
        if base.style != m.style:
            self.energy_lbl.configure(text="Different print style from the preset: compare them with a test grid.")
        else:
            r = presets.energy(m) / max(1e-9, presets.energy(base))
            self.energy_lbl.configure(
                text="Energy per mm: same as the preset." if abs(r - 1) < 0.005 else
                f"Energy per mm: {r:.2f}x the preset, so {'darker' if r > 1 else 'lighter'} marks "
                "(power / speed x passes).")
        vals = dict(feed=m.feed, power=m.power / 10, power_min=m.power_min / 10, tp1=m.tone_power[0] / 10,
                    tp2=m.tone_power[1] / 10, tp3=m.tone_power[2] / 10, pitch=m.pitch, passes=m.passes,
                    interlace=m.interlace, halftone_cell=m.halftone_cell, runup=m.runup)
        for k, (v, sp) in self.adv_vars.items():
            v.set(f"{vals[k]:g}")
            relevant = {"power": m.style not in ("layers",), "power_min": m.style == "grayscale",
                        "tp1": m.style == "layers", "tp2": m.style == "layers", "tp3": m.style == "layers",
                        "halftone_cell": m.style == "halftone", "passes": m.style != "layers"}.get(k, True)
            sp.state(["!disabled"] if relevant else ["disabled"])
        self.rule_var.set(self.rule_box["values"][1 if tuple(m.layer_rule) == ((1, 0), (2, 1), (3, 2)) else 0])
        self.rule_box.state(["!disabled"] if m.style == "layers" else ["disabled"])
        self.thin_var.set(m.thin_pass)
        self.del_btn.state(["!disabled"] if m.badge == "MINE" else ["disabled"])

    def _customised(self, **changes):
        m = self.mat
        if m.badge != "MINE" and not m.name.endswith("(adjusted)"):
            changes.setdefault("name", m.name + " (adjusted)")
        self.mat = m.copy(**changes)
        self._show_material()
        self.changed()

    def _style_pick(self, _=None):
        key = STYLE_KEYS[self.style_box.current()]
        if key == self.mat.style:
            return
        changes = dict(style=key)
        if key == "layers":
            p = self.mat.power
            changes.update(tone_power=(int(p * 0.72), int(p * 0.86), int(p)), interlace=5)
        elif self.mat.style == "layers":
            changes.update(power=int(self.mat.tone_power[2]), interlace=1)
        self._customised(**changes)

    def _adv_changed(self):
        if self._loading:
            return
        try:
            v = {k: float(var.get()) for k, (var, _) in self.adv_vars.items()}
        except ValueError:
            return
        m = self.mat
        rule = ((1, 0), (2, 1), (3, 2)) if self.rule_box.current() == 1 else ((1, 0), (1, 1), (3, 2))
        changes = dict(feed=int(min(6000, max(100, v["feed"]))), power=int(round(v["power"] * 10)),
                       power_min=int(round(v["power_min"] * 10)),
                       tone_power=tuple(int(round(v[k] * 10)) for k in ("tp1", "tp2", "tp3")),
                       pitch=round(max(0.05, v["pitch"]), 3), passes=int(v["passes"]),
                       interlace=int(max(1, v["interlace"])), halftone_cell=v["halftone_cell"],
                       runup=v["runup"], layer_rule=rule, thin_pass=self.thin_var.get())
        if all(getattr(m, k) == val for k, val in changes.items()):
            return
        self._customised(**changes)

    def save_preset(self):
        d = FormDialog(self.root, "Save as my preset", [("name", "Name", self.mat.name.replace(" (adjusted)", ""),
                                                         "str")],
                       intro="Saves these settings so they appear under 'My presets'. Tip: note what you tested, "
                             "e.g. 'Cherry - 45% 3000'.").result
        if not d or not d["name"].strip():
            return
        key = "my-" + jobs.safe_name(d["name"]).lower()
        base = self.base_mat
        m = self.mat.copy(key=key, name=d["name"].strip(), badge="MINE",
                          summary=self.mat.summary if self.mat.badge == "MINE" else f"Saved from {self.mat.name}.",
                          based_on=base.based_on if base.badge == "MINE" else base.key)
        presets.save_user_material(m)
        self.materials = presets.load_materials()
        self._fill_tree()
        self.select_material(key)
        self.say(f"Saved '{m.name}' to My presets.", "ok")

    def delete_preset(self):
        if self.mat.badge != "MINE" or not messagebox.askyesno("Delete preset", f"Delete '{self.mat.name}'?"):
            return
        presets.delete_user_material(self.mat.key)
        self.materials = presets.load_materials()
        self._fill_tree()
        self.select_material(self.materials[0].key)

    def test_grid(self):
        d = TestGridDialog(self.root, self.mat).result
        if not d:
            return
        self.grid_spec = d
        self.picture_path = Path("test-grid.png")
        self.dx = self.dy = 0.0
        self.pic_info.configure(text="Test grid (no picture)")
        self.changed()
        self.goto(2)
        self.say("Test grid ready. Place it (step 3), check it (step 4), then run the perimeter check and burn it "
                 "(step 5). Afterwards save the best patch as your preset.", "ok")

    # ================================================================ background build / check
    def changed(self, delay=350):
        if self._loading:
            return
        self.report = None
        if self._build_after:
            self.root.after_cancel(self._build_after)
        self._build_after = self.root.after(delay, self._start_build)

    def job_name(self):
        if self.grid_spec:
            return f"test-grid-{self.mat.key}"
        stem = self.picture_path.stem if self.picture_path else "job"
        return f"{stem}-{self.mat.key}"

    def _start_build(self):
        self._build_after = None
        if self.picture is None and not self.grid_spec:
            return
        self.gen += 1
        gen = self.gen
        mat, placement, look = self.build_params()
        pic, grid, name = self.picture, self.grid_spec, self.job_name()
        self.say("Updating preview...")

        def work():
            try:
                if grid:
                    job = planner.build_test_grid(mat, placement, grid["powers"], grid["speeds"], grid["patch"],
                                                  grid["gap"], grid["content"], name=name)
                else:
                    job = planner.build_job(pic, mat, placement, look, name=name)
                self.events.put(("built", gen, job, None))
            except Exception:
                self.events.put(("built", gen, None, traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()

    def check_job(self):
        if self.job is None:
            return
        gen, job = self.gen, self.job
        self.say("Checking every command offline...")
        self.check_text.configure(text="Checking...")

        def work():
            try:
                planner.compile_job(job)
                rep = verify.verify_job(job)
                self.events.put(("compiled", gen, job, rep))
            except Exception:
                self.events.put(("compiled", gen, None, traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()

    def _tab_changed(self):
        if self.nb.index("current") >= 3 and self.job is not None and self.compiled_gen != self.gen:
            self.check_job()
        self.refresh_laser_page()

    def _drain(self):
        try:
            while True:
                ev = self.events.get_nowait()
                self._event(ev)
                for hook in list(self.event_hooks):
                    try:
                        hook(ev)
                    except tk.TclError:
                        pass
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def _event(self, ev):
        kind = ev[0]
        if kind == "built":
            _, gen, job, err = ev
            if gen != self.gen:
                return
            if err:
                self.say("Couldn't build the job - see details.", "bad")
                messagebox.showerror("Build failed", err[-1500:])
                return
            self.job = job
            self.report = None
            self.perim_points = []
            self.preview.set_job(job)
            self.update_check_panel()
            self.say("Preview updated." + ("" if self.nb.index("current") >= 3 else " Next: size & placement."))
            if self.nb.index("current") >= 3:
                self.check_job()
        elif kind == "compiled":
            _, gen, job, rep = ev
            if gen != self.gen:
                return
            if job is None:
                self.say("Check failed - see details.", "bad")
                messagebox.showerror("Check failed", str(rep)[-1500:])
                return
            self.report = rep
            self.compiled_gen = gen
            self.update_check_panel()
            self.preview.refresh()
            self.say(verify.summary_text(rep).split("\n")[0], "ok" if rep["ok"] else "bad")
        else:
            self.machine_event(ev)

    def open_help(self, topic=None):
        from .dialogs import HelpWindow
        if self.help_win is not None and self.help_win.winfo_exists():
            self.help_win.topics = helptext.topics(self.mat)
            self.help_win.show_topic(topic)
            self.help_win.deiconify()
            self.help_win.lift()
        else:
            self.help_win = HelpWindow(self, topic)

    def open_settings(self):
        from .dialogs import SettingsDialog
        d = SettingsDialog(self.root, self.settings).result
        if d:
            self.settings.update(d)
            jobs.save_settings(self.settings)
            self.port_var.set(self.settings["port"])
            self.say("Settings saved.", "ok")

    def on_close(self):
        if self.worker is not None:
            self.disconnect(wait=True)
        if jobs.active_runner():
            messagebox.showinfo("Job keeps running", "The engraving job keeps running in the background. Open "
                                                     "Laser Photo Studio again to watch it or stop it.")
        self.root.destroy()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Laser Photo Studio")
    ap.add_argument("picture", nargs="?")
    ap.add_argument("--perimeter", nargs="?", const="", default=None, help="open the perimeter check (optional .nc)")
    ap.add_argument("--demo", action="store_true", help="simulated laser")
    args = ap.parse_args(argv)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root, args)
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
