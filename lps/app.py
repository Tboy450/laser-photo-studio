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
from .dialogs import FormDialog, LidLadderDialog, TestGridDialog
from .preview import PreviewPanel
from .presets import BADGES, PIECES, STYLES
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
        self._build_after = None
        self.layout_pending = False
        self._loading = False
        self._closing = False
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
        wrap_label(g, "Check where an existing .nc job (from this app, LaserGRBL or earlier projects) will burn, "
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
        if self.picture_path.stem.upper().endswith('IMPORT'):
            self.v_neg.set(False)       # prepared black-on-white laser inputs must not be inverted again
        self.rotate, self.mirror = 0, False
        self.grid_spec = None
        self.gfile = None
        self.dx = self.dy = 0.0
        self.art_w = None
        self._apply_orientation()
        self.say(f"Opened {self.picture_path.name}. Step 2: choose the material.", "ok")
        self.show_saved_size()
        if self.saved_size():
            self.use_saved_size()

    def turn(self, d):
        if self.picture_raw is None:
            return
        self.rotate = (self.rotate + d) % 4
        self.art_w = None
        self._apply_orientation()
        self.show_saved_size()

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
        self.m_lgrbl = wrap_label(card, "", style="Small.TLabel")
        self.m_lgrbl.pack(anchor="w", pady=(4, 0))
        lr = ttk.Frame(card)
        lr.pack(anchor="w", pady=(4, 0))
        link(lr, "Too light or too dark?", lambda: self.open_help("Too light or too dark?")).pack(side="left")
        link(lr, "LaserGRBL settings explained", lambda: self.open_help("Using LaserGRBL")).pack(side="left",
                                                                                                padx=12)
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
        fields = [("feed", "Speed (mm/min)", 1, 6000, 50), ("power", "Power (%)", 1, 100, 1),
                  ("power_min", "Lightest power (%) - grayscale", 0, 100, 1),
                  ("tp1", "Layer power light (%)", 1, 100, 1), ("tp2", "Layer power mid (%)", 1, 100, 1),
                  ("tp3", "Layer power dark (%)", 1, 100, 1), ("pitch", "Row spacing (mm)", 0.05, 0.5, 0.01),
                  ("passes", "Repeat passes", 1, 3, 1), ("interlace", "Cooling row groups (1 = off)", 1, 5, 1),
                  ("halftone_cell", "Halftone dot spacing (mm)", 0.2, 2.0, 0.1), ("runup", "Run-up (mm)", 0.5, 15, 0.1)]
        for i, (k, label, lo, hi, inc) in enumerate(fields):
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
        bg, fg = badge_colors(m.badge)
        self.m_badge.configure(text=f" {BADGES[m.badge]} ", background=bg, foreground=fg)
        self.m_summary.configure(text=m.summary)
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
        self.m_settings.configure(text=f"Power {pw}  |  speed {m.feed} mm/min  |  rows {m.pitch} mm "
                                       f"({25.4 / m.pitch:.0f} lines/inch)  |  {n} "
                                       f"{'layers' if m.style == 'layers' else 'pass' if n == 1 else 'passes'}")
        self.style_var.set(s["name"])
        self.style_help.configure(text=f"{s['what']} {s['why']}\nBest for: {s['best']}")
        self.m_lgrbl.configure(text="In LaserGRBL: File > Open the picture, then " + presets.lasergrbl_recipe(m))
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
        self.scan_var.set("Alternating rows" if m.scan_direction == "alternating" else "Left to right only")
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
        feed, note = speed_value(v["feed"])
        if note:
            self.say(note, "warn")
        if feed != v["feed"]:
            self.adv_vars["feed"][0].set(str(feed))       # show the value that will be used
        changes = dict(feed=feed, power=int(round(v["power"] * 10)),
                       power_min=int(round(v["power_min"] * 10)),
                       tone_power=tuple(int(round(v[k] * 10)) for k in ("tp1", "tp2", "tp3")),
                       pitch=round(max(0.05, v["pitch"]), 3), passes=int(v["passes"]),
                       interlace=int(max(1, v["interlace"])), halftone_cell=v["halftone_cell"],
                       runup=v["runup"], layer_rule=rule, thin_pass=self.thin_var.get())
        if all(getattr(m, k) == val for k, val in changes.items()):
            return
        self._customised(**changes)

    def _scan_pick(self, _=None):
        if self._loading:
            return
        direction = "forward" if self.scan_box.current() == 1 else "alternating"
        if direction != self.mat.scan_direction:
            self._customised(scan_direction=direction)

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
        self.gen += 1                  # reject old build/check results immediately, before debounce
        self.layout_pending = True
        self.report = None
        if self._build_after:
            self.root.after_cancel(self._build_after)
        self._build_after = self.root.after(delay, self._start_build)
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
            return
        gen = self.gen
        mat, placement, look = self.build_params()
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
        if self.job is None or self.layout_pending:
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
        finally:
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
            self.settings.update(d)
            jobs.save_settings(self.settings)
            self.port_var.set(self.settings["port"])
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

