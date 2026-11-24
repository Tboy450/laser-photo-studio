"""Laser Photo Studio - main window: steps 1-2 and the shared plumbing (background builds, events)."""
from __future__ import annotations

import argparse
import copy
from math import isfinite
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, gcodeinfo, helptext, imaging, job_package, jobs, planner, presets, verify, windows_drop
from .app_laser import LaserMixin
from .app_place import PlaceMixin
from .dialogs import FormDialog, LidLadderDialog, TestGridDialog
from .preview import PreviewPanel
from .presets import BADGES, PIECES, STYLES
from .sample_library import SampleLibrary
from .sample_view import SampleStrip
from .ui_common import COLORS, THEMES, ScrollFrame, apply_theme, badge, badge_colors, link, paint, wrap_label

GROUPS = (("PROVEN", "Proven on your U20"), ("START", "Starting points - test first"),
          ("EXPERIMENTAL", "Experimental - test first"), ("MINE", "My presets"))
STYLE_KEYS = list(STYLES)


class App(PlaceMixin, LaserMixin):
    def __init__(self, root: tk.Tk, args):
        self.root = root
        root.title(f"Laser Photo Studio {__version__}  -  Tronxy Ultrabot U20")
        root.geometry("1380x880")
        root.minsize(1120, 720)
        ico = jobs.APP_DIR / "assets" / "icon.ico"
        if ico.exists():
            try:
                root.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self.settings = jobs.load_settings()
        apply_theme(root, self.settings.get("theme", "light"))
        paint(root, background="bg")
        self.materials = presets.load_materials()
        self._job_material_snapshot = None
        self._snapshot_preset_key = None
        self._repeat_reference = None
        self._pending_material = None
        self.mat = self.base_mat = self.materials[0]
        self.help_win = None
        self.picture = self.picture_raw = self.picture_path = None
        self.rotate, self.mirror = 0, False
        self.piece_key = self.mat.piece or "custom"
        self.piece = copy.deepcopy(PIECES[self.piece_key])
        self.piece_user_set = False
        self._before_exact = None
        self._opened_placement = None
        self._pair = None
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
        self._build_after = None
        self.layout_pending = False
        self.layout_error = None
        self.source_provenance = None
        self._loading = False
        self._closing = False
        self.init_machine_state()
        self._build_ui()
        self.select_material(self.mat.key)
        self.root.after(60, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.start_laser_loops()
        root.after_idle(windows_drop.accept_files, root, self.open_dropped_file)
        if args.demo:
            self.demo.set(True)
        if args.picture:
            self.root.after(200, lambda: self.open_picture(args.picture))
        if args.perimeter is not None:
            self.root.after(250, lambda: self.perimeter_mode(args.perimeter or None))
        if getattr(args, 'job', None):
            def open_initial_job():
                if self.open_saved_job(args.job):
                    self.goto(3)
                    if getattr(args, 'connect', None):
                        self.port_var.set(args.connect)
                        self.goto(4)
                        self.root.after(100, self.connect)
                    if getattr(args, 'startup_report', None):
                        self._startup_report(Path(args.startup_report))
            self.root.after(200, open_initial_job)

    # ================================================================ layout
    def _build_ui(self):
        top = paint(tk.Frame(self.root, height=48), background="header")
        top.pack(fill="x")
        paint(tk.Label(top, text="  Laser Photo Studio", font=("Segoe UI", 15, "bold")),
              foreground="header_ink", background="header").pack(side="left", pady=8)
        ttk.Button(top, text="Settings", command=self.open_settings).pack(side="right", padx=(4, 10))
        ttk.Button(top, text="Guide", command=lambda: self.open_help()).pack(side="right", padx=4)
        names = {k: v["name"] for k, v in THEMES.items()}
        self.theme_var = tk.StringVar(value=names.get(self.settings.get("theme", "light"), names["light"]))
        tb = ttk.Combobox(top, textvariable=self.theme_var, state="readonly", width=25, values=list(names.values()))
        tb.pack(side="right", padx=4)
        tb.bind("<<ComboboxSelected>>", lambda e: self.set_theme(list(names)[tb.current()]))
        paint(tk.Label(top, text="Colours"), foreground="header_muted", background="header").pack(side="right")
        self.pill = paint(tk.Label(top, text=" Not connected ", font=("Segoe UI", 10, "bold"), padx=8, pady=3),
                          background="pill", foreground="header_ink")
        self.pill.pack(side="right", padx=6)
        paint(tk.Label(top, text="picture -> checked G-code -> safe runs on your Tronxy U20", anchor="w"),
              foreground="header_muted", background="header").pack(side="left", padx=10, fill="x", expand=True)
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
        self.statusbar = paint(tk.Label(self.root, anchor="w", padx=10, pady=4), background="status")
        self.statusbar.pack(fill="x", side="bottom")
        self._page_picture(self.pages[0].inner)
        self._page_material(self.pages[1].inner)
        self.page_place(self.pages[2].inner)
        self.page_check(self.pages[3].inner)
        self.page_laser(self.pages[4].inner)
        self.say("Welcome! Step 1: open a picture. Or open a G-code file to check where it will burn.")

    def say(self, text, kind="info"):
        self._said = (text, kind)
        col = {"info": COLORS["ink"], "ok": COLORS["ok"], "warn": COLORS["warn"], "bad": COLORS["bad"]}[kind]
        self.statusbar.configure(text=text, fg=col)

    def set_theme(self, name):
        """Switch colours now (and next time): Light, Dragonfly dark, or a high-contrast pair."""
        old = dict(COLORS)
        apply_theme(self.root, name)
        self.settings["theme"] = name
        jobs.save_settings(self.settings)
        self.theme_var.set(THEMES[name]["name"])
        for lab in (self.conn_lbl, self.gfile_lbl):      # coloured by what they say: keep the same meaning
            role = next((k for k, v in old.items() if v == str(lab.cget("foreground"))), None)
            if role:
                lab.configure(foreground=COLORS[role])
        self.preview.key.configure(background=ttk.Style().lookup("TFrame", "background") or COLORS["bg"])
        self.preview.refresh()
        self._show_material()
        self.update_check_panel()
        self._ready_shown = None
        self.refresh_laser_page()
        self.say(*getattr(self, "_said", ("Colours changed.", "info")))

    def goto(self, index):
        self.nb.select(index)

    def _next(self, parent, text, index):
        ttk.Button(parent, text=text, command=lambda: self.goto(index)).pack(anchor="e", pady=(16, 4))

    # ================================================================ step 1
    def _page_picture(self, f):
        ttk.Label(f, text="1. Pick a picture", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Open a photo, drawing or logo. Phone photos (HEIC) work too.",
                   style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        ttk.Button(f, text="Open picture...", style="Big.TButton", command=self.open_picture).pack(anchor="w")
        ttk.Button(f, text="Replace picture and keep settings and layout...",
                   command=lambda: self.open_picture(keep_layout=True)).pack(anchor="w", pady=(6, 0))
        ttk.Button(f, text="Open saved Studio picture job...", command=self.open_saved_job).pack(anchor="w", pady=(6, 0))
        ttk.Button(f, text="Samples & Jobs...", command=self.open_sample_library).pack(anchor="w", pady=(6, 0))
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

    def open_sample_library(self):
        browser = getattr(self, "_sample_library", None)
        if browser is not None and browser.winfo_exists():
            browser.reload()
            browser.lift()
            browser.focus_set()
        else:
            self._sample_library = SampleLibrary(self)

    def _picture_job_in_use(self):
        return bool(jobs.active_runner() or self.perim_running or (self.worker and
                    (self.worker.busy or not self.worker.tasks.empty())))

    def _picker_folder(self, kind):
        default = jobs.JOBS_DIR if kind == "job" else Path.home() / "Pictures"
        configured = self.settings.get(f"last_{kind}_folder")
        return next((str(p) for p in (Path(configured) if configured else default, default, Path.home())
                     if p.is_dir()), str(Path.home()))

    def _remember_picker_folder(self, kind, path, descriptor=None):
        path = Path(path).absolute()
        directory = str(path if path.is_dir() else path.parent)
        values = {f"last_{kind}_folder": directory}
        if kind == "job":
            descriptor = str(descriptor or (path / "job.json" if path.is_dir() else path))
            older = self.settings.get("recent_editable_jobs") or []
            values["recent_editable_jobs"] = [descriptor, *(p for p in older if p != descriptor)][:12]
        if all(self.settings.get(key) == value for key, value in values.items()):
            return
        saved = dict(self.settings, **values)
        try:
            jobs.save_settings(saved)
            self.settings = saved
        except OSError:
            self.say(f"Opened successfully, but Studio could not remember the folder in {jobs.SETTINGS_FILE}.", "warn")

    def open_dropped_file(self, path):
        if self._closing:
            return False
        if not path:
            self.say("Drop one picture or Studio job at a time.", "warn")
            return False
        path = Path(path)
        if path.suffix.lower() in imaging.PICTURE_TYPES or path.suffix.lower() == ".lpsjob" or path.name.lower() == "job.json":
            return self.open_picture(path)
        self.say("Drop a picture, a .lpsjob package or a Studio job.json.", "warn")
        return False

    def open_picture(self, path=None, *, keep_layout=False):
        if self._picture_job_in_use():
            self.say("Finish the active operation before opening another picture or job.", "warn")
            return False
        if keep_layout and (self.picture is None or self.grid_spec or self.gfile or self.fit_var.get() == "exact"):
            self.say("Open a picture and set its physical piece and picture size before replacing it.", "warn")
            return False
        path = path or filedialog.askopenfilename(
            title="Open a picture", initialdir=self._picker_folder("picture"),
            filetypes=[("Pictures", " ".join("*" + e for e in imaging.PICTURE_TYPES)),
                                               ("All files", "*.*")])
        if not path:
            return
        if keep_layout and Path(path).suffix.lower() not in imaging.PICTURE_TYPES:
            self.say("Choose an image for the replacement. Use Open saved Studio picture job for a job file.", "warn")
            return False
        if Path(path).suffix.lower() == ".lpsjob" or Path(path).name.lower() == 'job.json' or Path(path).is_dir():
            return self.open_saved_job(path)
        if Path(path).suffix.lower() in (".nc", ".gcode", ".gc", ".ngc", ".tap", ".txt"):
            self.perimeter_mode(path)
            return
        try:
            self.picture_raw = imaging.load_picture(path)
        except Exception as e:
            messagebox.showerror("Can't open picture", f"{Path(path).name}\n\n{e}")
            return
        self.picture_path = Path(path)
        self.source_provenance = None
        if not keep_layout:
            if self.fit_var.get() == "saved-whole":
                self.fit_var.set("whole")
            self._opened_placement = None
            if self._before_exact is not None:
                self.piece, self.piece_key, self.piece_user_set = self._before_exact[:3]
                self.fit_var.set("whole")
            self._before_exact = None
            self._pair = None
            self.proportions_var.set(True)
            self.dx = self.dy = 0.0
            self.art_w = None
        else:
            self.piece_user_set = True
        self.rotate, self.mirror = 0, False
        self.grid_spec = None
        self.gfile = None
        self._apply_orientation(use_picture_defaults=not keep_layout)
        self.show_saved_size()
        if not self.piece_user_set and self.file_has_size and not self.protect_piece_outline():
            self.use_saved_size()
        self.say(f"Opened {self.picture_path.name}. " +
                 ("Kept the print settings, picture adjustments, piece and placement. Review the new marks in Check."
                  if keep_layout else f"Using {self.mat.name} and its starting picture adjustments. Review in Check."), "ok")
        self._remember_picker_folder("picture", path)
        return True

    def turn(self, d):
        if self.picture_raw is None:
            return
        self.rotate = (self.rotate + d) % 4
        if self.fit_var.get() not in ("marks", "art-exact"):
            self.art_w = None
            self.artw_var.set("")
        self._apply_orientation()
        self.show_saved_size()

    def _adopt_material_snapshot(self, material):
        """Load job values without registering a project name as another preset."""
        self._dismiss_material_choice()
        match = presets.matching_recipe(material, self.materials)
        self._job_material_snapshot = material
        self._snapshot_preset_key = match.key if match else None
        self.mat = material
        if match:
            self.base_mat = match
            selection = 'm:' + match.key
        else:
            self.base_mat = material
            selection = 'job:material'
        self._fill_tree()
        self.tree.selection_set(selection)
        self.tree.see(selection)
        self._show_material()

    def _startup_report(self, path, attempts=40):
        """Optional local diagnostic receipt for a CLI-opened job, without sending motion."""
        m, placement, look = self.build_params()
        status = self.last_status
        ready = bool(self.connected and status and status.idle_off and not self.status_stale()
                     and not self.layout_pending and not self.layout_error and self.report
                     and self.report['ok'] and self.compiled_gen == self.gen)
        try:
            jobs.write_json(path, dict(connected=self.connected, port=self.port_var.get(),
                controller=status.state if status else None, wpos=status.wpos if status else None,
                zero_workflow_ready=ready, origin_set=self.origin_set, layout_pending=self.layout_pending,
                layout_error=self.layout_error, gen=self.gen, compiled_gen=self.compiled_gen,
                editable_source=str(self.picture_path), source_sha256=jobs.sha256(self.picture_path),
                material=m.__dict__, placement=placement.__dict__, look=look,
                selected_material=list(self.tree.selection()), job_started=False))
        except OSError as exc:
            self.say('Could not write startup diagnostic: ' + str(exc), 'warn')
            return
        if not ready and attempts > 0 and not self._closing:
            self.root.after(250, lambda: self._startup_report(path, attempts-1))

    def open_saved_job(self, path=None):
        if self._picture_job_in_use():
            self.say('Finish the active operation before loading another picture job.', 'warn')
            return False
        path = path or filedialog.askopenfilename(title='Open saved Studio picture job',
                                                   initialdir=self._picker_folder("job"),
                                                   filetypes=[('Studio job', 'job.json *.lpsjob')])
        if not path:
            return False
        from . import picture_jobs
        opened = Path(path)
        try:
            if opened.suffix.lower() == ".lpsjob":
                path = job_package.import_job(opened)
            raw, picture, job, report, look, placement, provenance = picture_jobs.read(path)
        except Exception as exc:
            messagebox.showerror('Cannot open editable job', str(exc))
            return False
        self._loading = True
        try:
            if self._build_after:
                self.root.after_cancel(self._build_after)
                self._build_after = None
            self.gen += 1  # reject outstanding builds of the previous picture
            self._adopt_material_snapshot(job.material)
            self.picture = self.picture_raw = raw
            self.picture_path = picture
            self.rotate, self.mirror = 0, False
            self.source_provenance = provenance
            self._before_exact = None
            self._opened_placement = self.placement_summary(job, report, planner.Placement(job.piece, **placement))
            self._pair = None
            self.grid_spec = self.gfile = None
            self.piece = copy.deepcopy(job.piece)
            self.piece_key = presets.matching_piece_key(self.piece) or 'custom'
            self.piece_user_set = True
            self.art_w, self.dx, self.dy = placement.get('art_w'), placement.get('dx', 0), placement.get('dy', 0)
            self.fit_var.set(placement['fit'])
            self.look_mode.configure(text="Picture adjustments from the saved job. Edit a control to update the preview.")
            for k, var in (('brightness',self.v_bright),('contrast',self.v_contrast),('gamma',self.v_gamma),
                           ('sharpen',self.v_sharpen),('autolevel',self.v_auto),('negative',self.v_neg),
                           ('black_point',self.v_black),('white_point',self.v_white)):
                var.set(look[k])
            self.expose_legacy_auto(job.geom.crop)
            # Legacy Auto is now represented by visible black/white points. Compare like with like.
            self._repeat_reference = (Path(provenance["folder"]), job.material, self.build_params()[2])
            for v, value in zip(self.v_cut, job.material.tone_cuts):
                v.set(value)
            self.proportions_var.set(provenance['keep_proportions'])
            self.sync_place_fields()
            self.origin_set = False
            self.observed_dot = None
            self.completed_checks.clear()
            self.layout_pending, self.layout_error = False, None
            self.job, self.report, self.compiled_gen = job, report, self.gen
            bounds = job.burn_bbox()
            marks = (f'{bounds[2]-bounds[0]:.2f} × {bounds[3]-bounds[1]:.2f} mm'
                     if bounds else 'none')
            self.pic_info.configure(text='Editable saved picture job: ' + job.name +
                f'\nSaved marks: {marks}. Row spacing: {job.geom.y_pitch:.3f} mm.\n' + self.picture_recipe(job) +
                '\nLoaded job values override preset defaults; subsequent edits rebuild the job. '
                f'Piece: {presets.piece_choice_label(self.piece)}. Saved placement is retained.' +
                ('\nLegacy material defaults used: ' + ', '.join(provenance['defaults_used']) if provenance['defaults_used'] else ''))
        finally:
            self._loading = False
        self.preview.set_job(job)
        self.show_saved_size()
        self.update_check_panel()
        self.refresh_laser_page()
        self.say('Editable job loaded and verified. Picture controls are live; establish job zero for this setup.', 'ok')
        self._remember_picker_folder("job", opened, Path(path) if Path(path).is_file() else None)
        return True

    def flip(self):
        if self.picture_raw is None:
            return
        self.mirror = not self.mirror
        self._apply_orientation()

    def _apply_orientation(self, *, use_picture_defaults=False):
        self.picture = imaging.orient(self.picture_raw, self.rotate, self.mirror)
        if use_picture_defaults:
            self.reset_look_from_material()
        else:
            self.expose_legacy_auto()
        w, h = self.picture.size
        self.pic_info.configure(text=f"{self.picture_path.name}  -  {w} x {h} pixels"
                                     f"{'  (turned)' if self.rotate else ''}{'  (mirrored)' if self.mirror else ''}")
        self.sync_place_fields()
        self.changed()

    # ================================================================ step 2
    def _page_material(self, f):
        ttk.Label(f, text="2. Material & print style", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "To repeat a print, open its saved job in step 1. With a picture open, select a preset "
                      "below to see what it would change.",
                   style="Small.TLabel").pack(anchor="w", pady=(0, 6))
        self.tree = ttk.Treeview(f, show="tree", height=12, selectmode="browse")
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._tree_pick)
        self._fill_tree()
        self.material_choice = ttk.LabelFrame(f, text="Proposed preset")
        self.material_diff = wrap_label(self.material_choice, "", style="Small.TLabel")
        self.material_diff.pack(fill="x", padx=5, pady=4)
        ttk.Button(self.material_choice, text="Apply print settings only",
                   command=lambda: self._apply_material_choice(False)).pack(anchor="w", padx=5)
        self.apply_full_preset = ttk.Button(self.material_choice, text="Apply full preset",
                                           command=lambda: self._apply_material_choice(True))
        self.apply_full_preset.pack(anchor="w", padx=5)
        ttk.Button(self.material_choice, text="Keep current settings",
                   command=self._dismiss_material_choice).pack(anchor="w", padx=5, pady=(0, 4))
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
        self.m_technical = wrap_label(card, "", style="Small.TLabel")
        self.m_technical.pack(anchor="w", pady=(4, 0))
        lr = ttk.Frame(card)
        lr.pack(anchor="w", pady=(4, 0))
        link(lr, "Too light or too dark?", lambda: self.open_help("Too light or too dark?")).pack(side="left")
        link(lr, "G-code settings explained", lambda: self.open_help("G-code & machine settings")).pack(
            side="left", padx=12)
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
        self.adv_labels = {}
        grid = ttk.Frame(adv)
        grid.pack(fill="x")
        fields = [("feed", "Speed (mm/min)", 1, 6000, 50), ("power", "Power (%)", 1, 100, 1),
                  ("power_min", "Lightest power (%) - grayscale", 0, 100, 1),
                  ("tp1", "Layer power light (%)", 1, 100, 1), ("tp2", "Layer power mid (%)", 1, 100, 1),
                  ("tp3", "Layer power dark (%)", 1, 100, 1), ("pitch", "Row spacing (mm)", 0.05, 0.5, 0.01),
                  ("passes", "Repeat passes", 1, 3, 1), ("interlace", "Cooling row groups (1 = off)", 1, 5, 1),
                  ("halftone_cell", "Halftone dot spacing (mm)", 0.2, 2.0, 0.1), ("runup", "Run-up (mm)", 0.5, 15, 0.1)]
        for i, (k, label, lo, hi, inc) in enumerate(fields):
            self.adv_labels[k] = label
            ttk.Label(grid, text=label).grid(row=i, column=0, sticky="w", pady=1)
            v = tk.StringVar()
            sp = ttk.Spinbox(grid, from_=lo, to=hi, increment=inc, textvariable=v, width=6,
                             command=self._adv_changed)
            sp.grid(row=i, column=1, sticky="e", padx=(8, 0))
            sp.bind("<FocusOut>", lambda e: self._adv_changed())
            sp.bind("<Return>", lambda e: self._adv_changed())
            self.adv_vars[k] = (v, sp)
            hint = ttk.Label(grid, style="Small.TLabel")
            hint.grid(row=i, column=2, sticky="w", padx=(8, 0))
            v.trace_add("write", lambda *a, k=k, v=v, hint=hint: hint.configure(text=adv_hint(k, v.get())))
        self.energy_lbl = wrap_label(adv, "", style="Small.TLabel")
        self.energy_lbl.pack(anchor="w", pady=(6, 0))
        ttk.Label(adv, text="Scan direction").pack(anchor="w", pady=(8, 0))
        self.scan_var = tk.StringVar()
        self.scan_box = ttk.Combobox(adv, textvariable=self.scan_var, state="readonly", width=36,
                                    values=("Alternating rows", "Left to right only"))
        self.scan_box.pack(anchor="w")
        self.scan_box.bind("<<ComboboxSelected>>", self._scan_pick)
        return_row = ttk.Frame(adv)
        return_row.pack(anchor="w", pady=(6, 0))
        ttk.Label(return_row, text="Laser-off return speed (mm/min)").pack(side="left")
        self.return_var = tk.StringVar()
        self.return_box = ttk.Combobox(return_row, textvariable=self.return_var, width=8,
                                       values=(600, 1500, 3000, 4500, 5000, 6000))
        self.return_box.pack(side="left", padx=(8, 0))
        self.return_box.bind("<<ComboboxSelected>>", self._return_changed)
        self.return_box.bind("<Return>", self._return_changed)
        self.return_box.bind("<FocusOut>", self._return_changed)
        wrap_label(adv, "Moves to the next scan row with the laser off. Faster returns shorten print time "
                   "and cooling time between rows. Engraving speed and power stay the same. "
                   "Choose 1-6000; press Enter to apply. Saved with your preset and job. "
                   "Thin-line feature hops use their separate travel speed.",
                   style="Small.TLabel").pack(anchor="w", pady=(2, 4))
        self.fast_gaps_var = tk.BooleanVar()
        ttk.Checkbutton(adv, text="Faster blank gaps inside scan lines (experimental)",
                        variable=self.fast_gaps_var, command=self._fast_gaps_changed).pack(anchor="w")
        gaps = ttk.Frame(adv)
        gaps.pack(anchor="w")
        self.gap_feed_var, self.gap_guard_var, self.gap_min_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for col, (label, var, key, hi, inc) in enumerate((
                ("Blank travel speed (mm/min)", self.gap_feed_var, "blank_feed", 6000, 500),
                ("Slow-down / speed-up offset each side (mm)", self.gap_guard_var, "blank_guard_mm", 20, 0.5),
                ("Design guard: shortest fast part (mm)", self.gap_min_var, "blank_min_fast_mm", 100, 0.5))):
            ttk.Label(gaps, text=label).grid(row=col, column=0, sticky="w", padx=(0, 4))
            sp = ttk.Spinbox(gaps, from_=(1, 0.5, 0)[col], to=hi, increment=inc, textvariable=var, width=6)
            sp.grid(row=col, column=1, sticky="w", padx=(0, 12))
            for ev in ("<Return>", "<FocusOut>"):
                sp.bind(ev, lambda e, k=key, v=var: self._gap_setting_changed(k, v))
        wrap_label(adv, "Scan-line passes only. Blank travel speed is its own setting, separate from the rewind "
                   "above. Inside a row, each laser-off gap keeps the offset at engraving speed on both sides, so "
                   "the head slows down before the next mark and speeds up after the last one. Only the middle "
                   "travels at the blank travel speed. Design guard (not a setting you asked for, a safety rule): "
                   "the middle is capped at what the head can brake from in that length at the controller's "
                   "500 mm/s2, and if it's shorter than the shortest fast part, the whole gap stays at engraving "
                   "speed. Marks keep their speed and power. Off by default; test on scrap first.",
                   style="Small.TLabel").pack(anchor="w", pady=(2, 4))
        wrap_label(adv, "Left to right only returns with the laser off. It takes longer and helps compare "
                   "direction-dependent alignment; it does not increase resolution.",
                   style="Small.TLabel").pack(anchor="w", pady=(2, 6))
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
        ttk.Button(f, text="Wide-range lid ladder (2 in circle)...", command=self.lid_ladder).pack(anchor="w",
                                                                                                pady=(6, 0))
        ttk.Button(f, text="Continue a stopped lid ladder...", command=self.continue_ladder).pack(anchor="w",
                                                                                                 pady=(6, 0))
        self._next(f, "Next: size & placement  >", 2)

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        if self._job_material_snapshot is not None and self._snapshot_preset_key is None:
            self.tree.insert('', 'end', iid='job:material', text='Current job settings (' + self.mat.look + ')')
        for kind, title in GROUPS:
            items = [m for m in self.materials if m.badge == kind]
            if not items:
                continue
            gid = self.tree.insert("", "end", text=title, open=True)
            for m in items:
                self.tree.insert(gid, "end", iid=f"m:{m.key}", text=m.name)

    def _tree_pick(self, _=None):
        sel = self.tree.selection()
        if sel and sel[0].startswith("m:") and not self._loading and (
                sel[0][2:] != (self._snapshot_preset_key or self.mat.key) or
                (self._job_material_snapshot is not None and self._snapshot_preset_key is None)):
            key = sel[0][2:]
            if self.picture is None or self.grid_spec or self.gfile:
                self.select_material(key)
                return
            # Keep the active row selected until the operator applies the proposed values.
            active = ('job:material' if self._job_material_snapshot and not self._snapshot_preset_key
                      else 'm:' + (self._snapshot_preset_key or self.mat.key))
            self.tree.selection_set(active)
            target = next(m for m in self.materials if m.key == key)
            current, _, look = self.build_params()
            changes = presets.settings_changes(presets.print_settings(current), presets.print_settings(target))
            proposed_look = {k: getattr(target, k) for k in look}
            if self.picture_path and self.picture_path.stem.upper().endswith("IMPORT"):
                proposed_look["negative"] = False
            photo = self.picture_changes(look, proposed_look)
            suggested_piece = self._preset_piece(target)
            piece_change = (self._can_suggest_piece() and suggested_piece in PIECES and
                            suggested_piece != self.piece_key)
            placement_note = (f"Print only keeps the current piece. Full preset uses {PIECES[suggested_piece]['name']}."
                              if piece_change else "Both choices keep the current piece and placement.")
            self.apply_full_preset.configure(text="Apply full preset including suggested piece" if piece_change else
                                                  "Apply print and picture settings")
            self.material_diff.configure(text=f"{target.name} (preview surface: {target.look})\nPrint: " + (", ".join(changes) or "Same settings")
                + "\nPicture: " + (", ".join(photo) or "Same adjustments")
                + "\n" + placement_note)
            self._pending_material = key
            self.material_choice.pack(fill="x", after=self.tree, pady=4)

    def _dismiss_material_choice(self):
        self._pending_material = None
        self.material_choice.pack_forget()

    def _apply_material_choice(self, include_picture):
        key = self._pending_material
        if key is None:
            return
        if self._picture_job_in_use():
            self.say("Finish the active operation before changing the print settings.", "warn")
            return
        self.select_material(key, keep_piece=not include_picture, keep_picture=not include_picture)

    @staticmethod
    def _preset_piece(m):
        # Older tin recipes inherited the card geometry of their source preset.
        return "tin50" if m.look in ("tin", "blacktin") and m.piece == "card-portrait" else m.piece

    def _can_suggest_piece(self):
        return not (self.piece_user_set or self.dx or self.dy or self.origin_set)

    def select_material(self, key, *, keep_piece=False, keep_picture=False):
        m = next((x for x in self.materials if x.key == key), None)
        if m is None:
            return
        self._dismiss_material_choice()
        if self._job_material_snapshot is not None:
            self._job_material_snapshot = None
            self._snapshot_preset_key = None
            self._fill_tree()
        self.mat = self.base_mat = m
        self._loading = True
        try:
            if self.tree.exists(f"m:{key}") and self.tree.selection() != (f"m:{key}",):
                self.tree.selection_set(f"m:{key}")
                self.tree.see(f"m:{key}")
            if self._can_suggest_piece() and not keep_piece:
                default_piece = self._preset_piece(m)
                if default_piece in PIECES and default_piece != self.piece_key:
                    self.set_piece(default_piece, user=False)
            for var, value in zip(self.v_cut, m.tone_cuts):
                var.set(value)
            if not keep_picture:
                self.reset_look_from_material()
            self._show_material()
        finally:
            self._loading = False
        self.changed()

    def _show_material(self):
        m = self.mat
        self.m_name.configure(text=(self.base_mat.name if self._snapshot_preset_key else
            'Current job settings (' + m.look + ')') if self._job_material_snapshot is not None else m.name)
        base = self.base_mat
        adjusted = bool(presets.settings_changes(presets.print_settings(base), presets.print_settings(m)))
        historical = m.badge == "PROVEN"
        evidence = ("Edited print settings" if adjusted else "Saved job settings" if self._job_material_snapshot
                    else "Preset based on a 0.10 mm test" if historical else BADGES[m.badge])
        bg, fg = badge_colors("MINE" if adjusted or self._job_material_snapshot or historical else m.badge)
        self.m_badge.configure(text=f" {evidence} ", background=bg, foreground=fg)
        self.m_summary.configure(text=("Reference notes: " if adjusted or historical or self._job_material_snapshot
                                       else "") + m.summary)
        self.sample_strip.show(m)
        self.m_notes.configure(text="\n".join("- " + n for n in m.notes))
        s = STYLES[m.style]
        if m.style == "layers":
            pw = ("/".join(f"{p / 10:g}" for p in m.tone_power) + " % ("
                  + "/".join(f"S{p:g}" for p in m.tone_power) + ")")
        elif m.style == "grayscale":
            pw = f"{m.power_min / 10:g}-{m.power / 10:g} % (S{m.power_min:g}-S{m.power:g})"
        else:
            pw = f"{m.power / 10:g} % (S{m.power:g})"
        n = len(m.layer_rule) if m.style == "layers" else m.passes
        label = "Effective settings (adjusted from preset)" if adjusted else "Effective settings"
        self.m_settings.configure(text=f"{label}\nPower {pw}  |  speed {m.feed} mm/min  |  rows {m.pitch} mm "
                                       f"({25.4 / m.pitch:.0f} lines/inch)  |  {n} "
                                       f"{'layers' if m.style == 'layers' else 'pass' if n == 1 else 'passes'}")
        self.m_technical.configure(text=presets.gcode_settings_summary(m))
        self.style_var.set(s["name"])
        self.style_help.configure(text=f"{s['what']} {s['why']}\nBest for: {s['best']}")
        if base.style != m.style:
            self.energy_lbl.configure(text="Different print style from the preset: compare them with a test grid.")
        else:
            r = presets.energy(m) / max(1e-9, presets.energy(base))
            self.energy_lbl.configure(
                text="Nominal exposure per line matches the reference (power × pass count / speed)." if abs(r - 1) < 0.005 else
                f"Nominal exposure per line: {r:.2f}x the reference (power × pass count / speed).")
        vals = dict(feed=m.feed, power=m.power / 10, power_min=m.power_min / 10, tp1=m.tone_power[0] / 10,
                    tp2=m.tone_power[1] / 10, tp3=m.tone_power[2] / 10, pitch=m.pitch, passes=m.passes,
                    interlace=m.interlace, halftone_cell=m.halftone_cell, runup=m.runup)
        for k, (v, sp) in self.adv_vars.items():
            v.set(f"{vals[k]:g}")
            relevant = {"power": m.style not in ("layers",), "power_min": m.style == "grayscale",
                        "tp1": m.style == "layers", "tp2": m.style == "layers", "tp3": m.style == "layers",
                        "halftone_cell": m.style == "halftone", "passes": m.style != "layers"}.get(k, True)
            sp.state(["!disabled"] if relevant else ["disabled"])
        self._accepted_advanced = {key: var.get() for key, (var, _) in self.adv_vars.items()}
        self.rule_var.set(self.rule_box["values"][1 if tuple(m.layer_rule) == ((1, 0), (2, 1), (3, 2)) else 0])
        self.rule_box.state(["!disabled"] if m.style == "layers" else ["disabled"])
        self.thin_var.set(m.thin_pass)
        self.scan_var.set("Alternating rows" if m.scan_direction == "alternating" else "Left to right only")
        self.return_var.set(str(m.row_feed))
        self.fast_gaps_var.set(m.fast_blank_gaps)
        self.gap_feed_var.set(str(m.blank_feed))
        self.gap_guard_var.set(f"{m.blank_guard_mm:g}")
        self.gap_min_var.set(f"{m.blank_min_fast_mm:g}")
        self.del_btn.state(["!disabled"] if m.badge == "MINE" and self._job_material_snapshot is None else ["disabled"])
        self.sync_piece_options()

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
        self._customised(style=key)

    def _adv_changed(self):
        if self._loading:
            return
        v = {}
        for key, (var, box) in self.adv_vars.items():
            try:
                number = float(var.get())
                if not isfinite(number):
                    raise ValueError
                if key != "feed" and var.get() != self._accepted_advanced[key]:
                    if not float(box.cget("from")) <= number <= float(box.cget("to")):
                        raise ValueError
                    if key in ("passes", "interlace") and not number.is_integer():
                        raise ValueError
            except ValueError:
                self._show_material()
                self.say(f"{self.adv_labels[key]} is invalid. Restored the last accepted settings. "
                         f"{self.adv_labels[key]} is {var.get()}.", "warn")
                return
            v[key] = number
        changes = {}
        tones = list(self.mat.tone_power)
        note = ""
        for key, value in v.items():
            if self.adv_vars[key][0].get() == self._accepted_advanced[key]:
                continue
            if key == "feed":
                changes[key], note = speed_value(value)
            elif key in ("power", "power_min"):
                changes[key] = round(value * 10)
            elif key in ("tp1", "tp2", "tp3"):
                tones[int(key[-1]) - 1] = round(value * 10)
                changes["tone_power"] = tuple(tones)
            elif key in ("passes", "interlace"):
                changes[key] = int(value)
            else:
                changes[key] = value
        graduated = ((1, 0), (2, 1), (3, 2))
        if (self.rule_box.current() == 1) != (tuple(self.mat.layer_rule) == graduated):
            changes["layer_rule"] = graduated if self.rule_box.current() == 1 else ((1, 0), (1, 1), (3, 2))
        if self.thin_var.get() != self.mat.thin_pass:
            changes["thin_pass"] = self.thin_var.get()
        if changes:
            self._customised(**changes)
        if note:
            self.say(note, "warn")

    def _scan_pick(self, _=None):
        if self._loading:
            return
        direction = "forward" if self.scan_box.current() == 1 else "alternating"
        if direction != self.mat.scan_direction:
            self._customised(scan_direction=direction)

    def _return_changed(self, _=None):
        if self._loading:
            return
        try:
            value = float(self.return_var.get())
            if not 1 <= value <= 6000 or not value.is_integer():
                raise ValueError
        except ValueError:
            self.return_var.set(str(self.mat.row_feed))
            self.say("Return speed must be a whole number from 1 to 6000 mm/min. Previous value restored.", "warn")
            return
        if int(value) != self.mat.row_feed:
            self._customised(row_feed=int(value))

    def _gap_setting_changed(self, key, var):
        if self._loading:
            return
        try:
            value = int(round(float(var.get()))) if key == "blank_feed" else round(float(var.get()), 2)
            self.mat.copy(**{key: value})                     # range check
        except ValueError as e:
            self.say(f"Fast blank gaps: {e}" if "mm" in str(e) else "Fast blank gaps: enter a number in mm.", "warn")
            var.set(f"{getattr(self.mat, key):g}")
            return
        if value != getattr(self.mat, key):
            self._customised(**{key: value})

    def _fast_gaps_changed(self):
        if not self._loading and self.fast_gaps_var.get() != self.mat.fast_blank_gaps:
            self._customised(fast_blank_gaps=self.fast_gaps_var.get())

    def save_preset(self):
        d = FormDialog(self.root, "Save as my preset", [("name", "Name", self.mat.name.replace(" (adjusted)", ""),
                                                         "str")],
                       intro="Saves the material recipe AND current picture adjustments (including Negative). "
                             "Piece dimensions, placement and the photo are saved with a job, not this preset.").result
        if not d or not d["name"].strip():
            return
        key = "my-" + jobs.safe_name(d["name"]).lower()
        base = self.base_mat
        effective, _, look = self.build_params()
        m = effective.copy(**look).copy(key=key, name=d["name"].strip(), badge="MINE",
                          summary=self.mat.summary if self.mat.badge == "MINE" else f"Saved from {self.mat.name}.",
                          based_on=base.based_on if base.badge == "MINE" else base.key)
        if any(item.key == key for item in self.materials) and not messagebox.askyesno(
                "Replace saved preset?", f"Replace the saved settings for '{m.name}'?", parent=self.root):
            return
        try:
            presets.save_user_material(m)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Could not save preset", str(exc), parent=self.root)
            return
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
        self._before_exact = self._opened_placement = None
        self._repeat_reference = None
        self.grid_spec = d
        self.picture_path = Path("test-grid.png")
        self.dx = self.dy = 0.0
        self.pic_info.configure(text="Test grid (no picture)")
        self.changed()
        self.goto(2)
        self.say("Test grid ready. Place it (step 3), check it (step 4), then run the perimeter check and burn it "
                 "(step 5). Afterwards save the best patch as your preset.", "ok")

    def continue_ladder(self):
        """Burn what a stopped ladder didn't, on the same spots, in the order you pick."""
        from . import ladder
        found = [f for f in jobs.latest_jobs(30) if "lid-ladder" in f.name and (f / "state.json").exists()
                 and (jobs.read_json(f / "state.json") or {}).get("phase") in ("stopped", "dropout", "fault")]
        folder = filedialog.askdirectory(title="Stopped lid ladder job folder", mustexist=True,
                                         initialdir=str(found[0] if found else jobs.JOBS_DIR))
        if not folder:
            return
        try:
            c = ladder.continuation(folder)
        except Exception as e:
            messagebox.showerror("Can't continue this job", f"{Path(folder).name}\n\n{e}")
            return
        left = [s for s in c["speeds"] if s not in c["skip_speeds"]]
        part = "".join(f"\n{s} mm/min: rows Y {min(r):g} to {max(r):g} already burned, left out." for s, r in c["done_rows"].items())
        d = FormDialog(self.root, "Continue the ladder", [
            ("order", "Burn order", ladder.ORDERS["hot"], list(ladder.ORDERS.values()))],
            intro=f"{c['from_job']}\nAlready done: {', '.join(map(str, c['skip_speeds'])) or 'nothing'} mm/min.\n"
                  f"Left: {', '.join(map(str, left))} mm/min.{part}\n\nSame spots as the first map. Keep job zero "
                  "where it was (don't move the lid or reset the controller). 'Hottest first' makes one pass per "
                  "patch: with 'Pause after each pass' on you can let the lid cool between them.").result
        if not d:
            return
        c["order"] = next(k for k, v in ladder.ORDERS.items() if v == d["order"])
        self._before_exact = self._opened_placement = None
        self._repeat_reference = None
        self.grid_spec = c
        self.mat = self.base_mat = ladder.lid_material(self.mat, c.get("material", ""))
        self._show_material()
        self.piece_key = "custom"
        self.piece = ladder.lid_piece(c["diameter"], c["safe"])
        self.piece_user_set = True
        self.fit_var.set("whole")
        self.picture_path = None
        self.dx = self.dy = 0.0
        self.art_w = None
        self.pic_info.configure(text=f"Continuing {c['from_job']}")
        self.sync_place_fields()
        self.changed()
        self.goto(3)
        self.say("Continuation ready: check it (step 4) and save it for the map ('5 LADDER MAP', red = burning now). "
                 "In step 5 keep the same job zero, then start with 'Pause after each pass' on.", "ok")

    def lid_ladder(self):
        from . import ladder
        d = LidLadderDialog(self.root).result
        if not d:
            return
        self._before_exact = self._opened_placement = None
        self._repeat_reference = None
        self.grid_spec = d
        self.mat = self.base_mat = ladder.lid_material(self.mat, d.get("material", ""))   # the lid, not step 2's pick
        self._show_material()
        self.piece_key = "custom"
        self.piece = ladder.lid_piece(d["diameter"], d["safe"])
        self.piece_user_set = True
        self.fit_var.set("whole")
        self.picture_path = None
        self.dx = self.dy = 0.0
        self.art_w = None
        self.pic_info.configure(text=f"Lid ladder (no picture): {d['material']}")
        self.sync_place_fields()
        self.changed()
        self.goto(3)
        self.say("Lid ladder ready: check it (step 4), save it (the folder gets '5 LADDER MAP' to print), then "
                 "perimeter check and burn (step 5) with 'Pause after each pass' on.", "ok")

    # ================================================================ background build / check
    def changed(self, delay=350):
        if self._loading:
            return
        self._dismiss_material_choice()
        self.gen += 1                  # reject old build/check results immediately, before debounce
        self.completed_checks.clear()
        self.layout_error = None
        self.layout_pending = True
        if hasattr(self, "clearance_lbl"):
            self.clearance_lbl.configure(text="Updating layout — edge clearances are not current yet.")
        self.report = None
        if self._build_after:
            self.root.after_cancel(self._build_after)
        self._build_after = self.root.after(delay, self._start_build)
        if self.check_mode == "image":
            self.preview.refresh()
        self.refresh_laser_page()

    def job_name(self):
        if self.grid_spec and self.grid_spec.get("kind") == "lid":
            m = self.grid_spec.get("material", "").split()
            return (f"lid-ladder-{'-'.join(m[:2]).lower() or 'lid'}-{self.grid_spec.get('lid', 1)}"
                    + ("-continued" if self.grid_spec.get("from_job") else ""))
        if self.grid_spec:
            return f"test-grid-{self.mat.key}"
        stem = self.picture_path.stem if self.picture_path else "job"
        return f"{stem}-{self.mat.key}"

    def _start_build(self):
        self._build_after = None
        if self.picture is None and not self.grid_spec:
            self.layout_pending = False
            self.layout_error = (('No editable picture loaded. Open saved Studio picture job or the original picture. '
                                  'A finished job injected without its source cannot use picture controls.')
                                 if self.job is not None else None)
            self.report = None
            self.refresh_laser_page()
            self.say(self.layout_error or 'Open a picture or saved Studio picture job.', 'warn')
            return
        gen = self.gen
        try:
            mat, placement, look = self.build_params()
        except (ValueError, tk.TclError) as exc:
            self.layout_pending = False
            self.layout_error = 'Invalid layout setting: ' + str(exc)
            self.report = None
            self.refresh_laser_page()
            self.say(self.layout_error, 'warn')
            return
        pic, grid, name = self.picture, self.grid_spec, self.job_name()
        self.say("Updating preview...")

        def work():
            try:
                if grid and grid.get("kind") == "lid":
                    from . import ladder
                    job = ladder.build_lid_ladder(mat, placement, grid["powers"], grid["speeds"], grid["lid"],
                                                  grid["material"], name=name,
                                                  skip_speeds=grid.get("skip_speeds", ()),
                                                  skip_patches=grid.get("skip_patches", ()),
                                                  patch=grid.get("patch"), spread=grid.get("spread", False),
                                                  ramp=grid.get("ramp", False), combos=grid.get("combos"),
                                                  avoid=grid.get("avoid", ()),
                                                  done_rows={int(k): v for k, v in grid.get("done_rows", {}).items()},
                                                  order=grid.get("order", "fast"), mark=grid.get("mark", True))
                elif grid:
                    job = planner.build_test_grid(mat, placement, grid["powers"], grid["speeds"], grid["patch"],
                                                  grid["gap"], grid["content"], name=name)
                else:
                    job = planner.build_job(pic, mat, placement, look, name=name)
                job.trace_paths()
                self.events.put(("built", gen, job, None))
            except Exception:
                self.events.put(("built", gen, None, traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()

    def check_job(self):
        if self.job is None or self.layout_pending or self.layout_error:
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
        if self.nb.index("current") != 1:
            self._dismiss_material_choice()
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
        finally:
            self.root.after(60, self._drain)

    def _event(self, ev):
        kind = ev[0]
        if kind == "built":
            _, gen, job, err = ev
            if gen != self.gen:
                return
            if err:
                self.layout_pending = False
                self.layout_error = 'Layout failed. Correct the source/settings before setting job zero.'
                self.report = None
                self.refresh_laser_page()
                self.say("Couldn't build the job - see details.", "bad")
                messagebox.showerror("Build failed", err[-1500:])
                return
            old, self.job = self.job, job
            self.layout_pending = False
            self.report = None
            if old is not None and planner.piece_rect(old.piece)[:2] != planner.piece_rect(job.piece)[:2]:
                self.start_point_moved()
            self.remember_setup()
            self.preview.set_job(job)
            self.update_check_panel()
            self.refresh_laser_page()
            self.say("Preview updated." + ("" if self.nb.index("current") >= 3 else " Next: size & placement."))
            if self.nb.index("current") >= 3:
                self.check_job()
        elif kind == "compiled":
            _, gen, job, rep = ev
            if gen != self.gen or (job is not None and job is not self.job):
                return
            if job is None:
                self.say("Check failed - see details.", "bad")
                messagebox.showerror("Check failed", str(rep)[-1500:])
                return
            self.report = rep
            self.compiled_gen = gen
            self.update_check_panel()
            self.refresh_laser_page()
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
            saved = dict(self.settings, **d)
            try:
                jobs.save_settings(saved)
            except OSError as exc:
                messagebox.showerror("Settings could not be saved", jobs.settings_write_problem(exc), parent=self.root)
                return
            self.settings = saved
            self.port_var.set(self.settings["port"])
            self.saved_port_desc.configure(text=f"Saved port: {self.settings['port']}")
            self.say("Settings saved.", "ok")

    def on_close(self):
        if self._closing:
            return
        self._closing = True
        if self.worker is not None:
            self.disconnect()
        self._finish_close()

    def _finish_close(self):
        if self.worker is None:
            self.root.destroy()
        else:
            self.root.after(60, self._finish_close)


def adv_hint(key: str, text: str) -> str:
    """The same setting in the other units you'll meet: S value in the G-code, lines per inch, inches."""
    try:
        v = float(text)
    except ValueError:
        return ""
    if key in ("power", "power_min", "tp1", "tp2", "tp3"):
        return f"= S{v * 10:g}"
    if key == "pitch" and v > 0:
        return f"= {25.4 / v:.0f} lines/in"
    if key == "feed":
        return f"= {v / 25.4:.0f} in/min"
    if key in ("halftone_cell", "runup"):
        return f"= {v / 25.4:.3f} in"
    return ""


def speed_value(raw: float) -> tuple:
    """Advanced-settings speed: any whole mm/min from 1 to 6000 (the controller's maximum, $110). Returns (value,
    message): the message says what was changed and why, so nothing changes silently."""
    feed = int(round(min(6000.0, max(1.0, raw))))
    if feed != raw:
        why = ("the controller's maximum is 6000 ($110)" if raw > 6000 else
               "the slowest is 1" if raw < 1 else "speeds are whole mm/min")
        return feed, f"Speed {raw:g} mm/min was changed to {feed} mm/min: {why}."
    if feed < 24:
        return feed, (f"Speed {feed} mm/min accepted. Earlier runs suggest this machine may not go slower than about "
                      "24 mm/min; the print timer in step 5 will show the real time.")
    return feed, ""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="Laser Photo Studio")
    ap.add_argument("picture", nargs="?")
    ap.add_argument('--job', help='open an editable saved Studio picture job folder or job.json')
    ap.add_argument('--connect', metavar='PORT', help='explicitly connect after a saved picture job loads; no motion or print')
    ap.add_argument('--startup-report', metavar='JSON', help='write a local loading/connection diagnostic for --job')
    ap.add_argument("--perimeter", nargs="?", const="", default=None, help="open the perimeter check (optional .nc)")
    ap.add_argument("--demo", action="store_true", help="simulated laser")
    args = ap.parse_args(argv)
    if args.job and (args.picture or args.perimeter is not None):
        ap.error('Use --job by itself; do not combine it with picture or perimeter check mode.')
    if args.connect and not args.job:
        ap.error('--connect requires --job; connection is attempted only after successful editable loading.')
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
