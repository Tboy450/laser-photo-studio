"""Steps 3 (size & placement) and 4 (look & check, save, LaserGRBL)."""
from __future__ import annotations

import copy
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import jobs, simulate, verify
from .dialogs import FormDialog
from .planner import Placement
from .presets import PIECES
from .preview import fmt_dur
from .ui_common import COLORS, Slider, ToolTip, link, moves_note, wrap_label

PIECE_KEYS = list(PIECES)


class PlaceMixin:
    # ================================================================ step 3
    def page_place(self, f):
        ttk.Label(f, text="3. Size & placement", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Measure your piece. The start point (origin, 0,0) is the spot you'll put the laser head on "
                      "before starting (you set it in step 5).", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        c = ttk.LabelFrame(f, text="Your piece", style="Card.TLabelframe")
        c.pack(fill="x", pady=4)
        self.piece_var = tk.StringVar()
        self.piece_box = ttk.Combobox(c, textvariable=self.piece_var, state="readonly", width=42,
                                      values=[PIECES[k]["name"] for k in PIECE_KEYS])
        self.piece_box.pack(anchor="w")
        self.piece_box.bind("<<ComboboxSelected>>", lambda e: self.set_piece(PIECE_KEYS[self.piece_box.current()]))
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(6, 0))
        self.pw_var, self.ph_var, self.corner_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in (("Width", self.pw_var), ("Height", self.ph_var)):
            ttk.Label(row, text=label).pack(side="left")
            sp = ttk.Spinbox(row, from_=5, to=600, increment=0.5, width=7, textvariable=var,
                             command=self._piece_edited)
            sp.pack(side="left", padx=(4, 10))
            sp.bind("<FocusOut>", lambda e: self._piece_edited())
            sp.bind("<Return>", lambda e: self._piece_edited())
        ttk.Label(row, text="mm").pack(side="left")
        self.piece_in_lbl = ttk.Label(c, style="Muted.TLabel")
        self.piece_in_lbl.pack(anchor="w", pady=(2, 0))
        row2 = ttk.Frame(c)
        row2.pack(fill="x", pady=(6, 0))
        self.shape_var = tk.StringVar(value="rect")
        ttk.Radiobutton(row2, text="Rectangle", value="rect", variable=self.shape_var,
                        command=self._piece_edited).pack(side="left")
        ttk.Radiobutton(row2, text="Circle (lids)", value="circle", variable=self.shape_var,
                        command=self._piece_edited).pack(side="left", padx=8)
        ttk.Label(row2, text="Corner radius").pack(side="left", padx=(8, 4))
        sp = ttk.Spinbox(row2, from_=0, to=50, increment=0.5, width=5, textvariable=self.corner_var,
                         command=self._piece_edited)
        sp.pack(side="left")
        sp.bind("<FocusOut>", lambda e: self._piece_edited())
        o = ttk.LabelFrame(f, text="Start point: where you'll put the laser head", style="Card.TLabelframe")
        o.pack(fill="x", pady=4)
        self.origin_var = tk.StringVar(value="lower-left")
        ttk.Radiobutton(o, text="Lower-left corner of the piece", value="lower-left", variable=self.origin_var,
                        command=self._piece_edited).pack(anchor="w")
        ttk.Radiobutton(o, text="Centre of the piece", value="center", variable=self.origin_var,
                        command=self._piece_edited).pack(anchor="w")
        wrap_label(o, "Corners are easiest to find by eye. Lids are usually centred.", style="Small.TLabel").pack(
            anchor="w", pady=(2, 0))
        m = ttk.LabelFrame(f, text="Margins and no-burn zones", style="Card.TLabelframe")
        m.pack(fill="x", pady=4)
        mr = ttk.Frame(m)
        mr.pack(fill="x")
        self.margin_vars = []
        for i, label in enumerate(("Left", "Bottom", "Right", "Top")):
            ttk.Label(mr, text=label).grid(row=i // 2, column=(i % 2) * 2, sticky="w", pady=1)
            v = tk.StringVar()
            sp = ttk.Spinbox(mr, from_=0, to=100, increment=0.5, width=6, textvariable=v, command=self._piece_edited)
            sp.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(4, 16), pady=1)
            sp.bind("<FocusOut>", lambda e: self._piece_edited())
            self.margin_vars.append(v)
        ttk.Label(mr, text="mm").grid(row=0, column=4, sticky="w")
        ttk.Label(m, text="No-burn zones (holes, twine, screws, existing art):").pack(anchor="w", pady=(8, 2))
        self.ko_list = tk.Listbox(m, height=4, activestyle="none")
        self.ko_list.pack(fill="x")
        kr = ttk.Frame(m)
        kr.pack(fill="x", pady=(4, 0))
        ttk.Button(kr, text="+ Hole / circle", command=lambda: self.add_keepout("circle")).pack(side="left")
        ttk.Button(kr, text="+ Rectangle", command=lambda: self.add_keepout("rect")).pack(side="left", padx=4)
        ttk.Button(kr, text="Remove", command=self.remove_keepout).pack(side="left")
        a = ttk.LabelFrame(f, text="Picture size", style="Card.TLabelframe")
        a.pack(fill="x", pady=4)
        self.fit_var = tk.StringVar(value="whole")
        ttk.Radiobutton(a, text="Whole picture", value="whole", variable=self.fit_var,
                        command=self._fit_changed).pack(anchor="w")
        ttk.Radiobutton(a, text="Fill the area (crops the edges)", value="fill", variable=self.fit_var,
                        command=self._fit_changed).pack(anchor="w")
        ar = ttk.Frame(a)
        ar.pack(fill="x", pady=(6, 0))
        ttk.Label(ar, text="Width").pack(side="left")
        self.artw_var = tk.StringVar()
        self.artw_spin = ttk.Spinbox(ar, from_=2, to=600, increment=1, width=7, textvariable=self.artw_var,
                                     command=self._artw_edited)
        self.artw_spin.pack(side="left", padx=4)
        self.artw_spin.bind("<FocusOut>", lambda e: self._artw_edited())
        self.artw_spin.bind("<Return>", lambda e: self._artw_edited())
        ttk.Label(ar, text="mm").pack(side="left")
        ttk.Button(ar, text="Largest that fits", command=self._artw_fit).pack(side="left", padx=8)
        self.arth_lbl = wrap_label(a, "", style="Muted.TLabel")
        self.arth_lbl.pack(anchor="w", pady=(4, 0))
        p = ttk.LabelFrame(f, text="Move the picture (the machine doesn't move)", style="Card.TLabelframe")
        p.pack(fill="x", pady=4)
        self.nudge_step = tk.StringVar(value="1")
        self._nudge_pad(p, self.nudge)
        self.offset_lbl = ttk.Label(p, style="Muted.TLabel")
        self.offset_lbl.pack(anchor="w", pady=(4, 0))
        self._next(f, "Next: look & check  >", 3)
        self.sync_place_fields()

    def _nudge_pad(self, parent, fn):
        moves_note(parent, COLORS["art"], "Moves the picture on the piece (blue box). Nothing moves on the "
                                          "machine.").pack(fill="x", pady=(0, 4))
        pad = ttk.Frame(parent)
        pad.pack(anchor="w")
        for t, dx, dy, r, cc in (("Up", 0, 1, 0, 1), ("Left", -1, 0, 1, 0), ("Centre", None, None, 1, 1),
                                 ("Right", 1, 0, 1, 2), ("Down", 0, -1, 2, 1)):
            b = ttk.Button(pad, text=t, width=7 if dx is None else 6, command=lambda dx=dx, dy=dy: fn(dx, dy))
            b.grid(row=r, column=cc)
            ToolTip(b, "Puts the picture back in the middle of the piece. The laser head doesn't move."
                    if dx is None else f"Moves the picture {t.lower()} by one step on the piece. The laser head "
                                       "doesn't move; the job is rebuilt and checked again.")
        ttk.Label(pad, text="  step").grid(row=1, column=3)
        ttk.Combobox(pad, textvariable=self.nudge_step, values=["0.5", "1", "2", "5"], width=4,
                     state="readonly").grid(row=1, column=4)
        ttk.Label(pad, text="mm").grid(row=1, column=5, padx=(2, 0))

    def nudge(self, dx, dy):
        if dx is None:
            self.dx = self.dy = 0.0
        else:
            st = float(self.nudge_step.get())
            self.dx = round(self.dx + dx * st, 2)
            self.dy = round(self.dy + dy * st, 2)
        self.sync_place_fields()
        self.perim_points = []
        self.changed(150)

    def set_piece(self, key, user=True):
        self.piece_key = key
        self.piece = copy.deepcopy(PIECES[key])
        if user:
            self.piece_user_set = True
        self.art_w = None
        self.dx = self.dy = 0.0
        self.sync_place_fields()
        self.changed()

    def sync_place_fields(self):
        if not hasattr(self, "pw_var"):
            return
        old, self._loading = self._loading, True
        try:
            pc = self.piece
            self.piece_var.set(PIECES.get(self.piece_key, PIECES["custom"])["name"])
            self.pw_var.set(f"{pc['w']:g}")
            self.ph_var.set(f"{pc['h']:g}")
            self.shape_var.set(pc.get("shape", "rect"))
            self.corner_var.set(f"{pc.get('corner', 0):g}")
            self.origin_var.set(pc.get("origin", "lower-left"))
            for v, val in zip(self.margin_vars, pc.get("margins", (0, 0, 0, 0))):
                v.set(f"{val:g}")
            self.ko_list.delete(0, "end")
            for k in pc.get("keepouts", []):
                if k.get("kind") == "circle":
                    self.ko_list.insert("end", f"Hole: centre {k['x']:g}, {k['y']:g} mm, radius {k['r']:g} mm")
                else:
                    self.ko_list.insert("end", f"Rectangle: from {k['x']:g}, {k['y']:g} mm, {k['w']:g} x {k['h']:g} mm")
            if self.art_w:
                self.artw_var.set(f"{self.art_w:g}")
            self.piece_in_lbl.configure(text=f"= {pc['w'] / 25.4:.2f} x {pc['h'] / 25.4:.2f} inches")
            self.offset_lbl.configure(text=("Centred." if not (self.dx or self.dy) else
                                            f"Moved {abs(self.dx):g} mm {'right' if self.dx >= 0 else 'left'}, "
                                            f"{abs(self.dy):g} mm {'up' if self.dy >= 0 else 'down'} from centre."))
            self.artw_spin.state(["disabled"] if self.fit_var.get() == "fill" else ["!disabled"])
        finally:
            self._loading = old

    def _piece_edited(self):
        if self._loading:
            return
        try:
            pc = self.piece
            pc["w"], pc["h"] = max(5.0, float(self.pw_var.get())), max(5.0, float(self.ph_var.get()))
            pc["shape"] = self.shape_var.get()
            if pc["shape"] == "circle":
                pc["h"] = pc["w"]
            pc["corner"] = max(0.0, float(self.corner_var.get() or 0))
            pc["origin"] = self.origin_var.get()
            pc["margins"] = tuple(max(0.0, float(v.get() or 0)) for v in self.margin_vars)
        except ValueError:
            return
        self.piece_user_set = True
        self.sync_place_fields()
        self.perim_points = []
        self.changed()

    def add_keepout(self, kind):
        if kind == "circle":
            d = FormDialog(self.root, "Add a hole / round no-burn zone", [
                ("x", "Centre from the left edge (mm)", 10, "float"), ("y", "Centre from the bottom edge (mm)", 10,
                                                                      "float"),
                ("r", "Radius incl. clearance (mm)", 5, "float")],
                intro="Measure from the piece's lower-left corner.").result
            if d:
                self.piece.setdefault("keepouts", []).append(dict(kind="circle", **d))
        else:
            d = FormDialog(self.root, "Add a rectangular no-burn zone", [
                ("x", "Left edge from the piece's left (mm)", 0, "float"), ("y", "Bottom edge from the piece's bottom (mm)",
                                                                           0, "float"),
                ("w", "Width (mm)", 10, "float"), ("h", "Height (mm)", 10, "float")],
                intro="Measure from the piece's lower-left corner.").result
            if d:
                self.piece.setdefault("keepouts", []).append(dict(kind="rect", **d))
        if d:
            self.piece_user_set = True
            self.sync_place_fields()
            self.changed()

    def remove_keepout(self):
        sel = self.ko_list.curselection()
        if sel:
            del self.piece["keepouts"][sel[0]]
            self.sync_place_fields()
            self.changed()

    def _fit_changed(self):
        self.art_w = None
        self.sync_place_fields()
        self.changed()

    def _artw_edited(self):
        if self._loading:
            return
        try:
            v = float(self.artw_var.get())
        except ValueError:
            return
        if v > 1 and v != self.art_w:
            self.art_w = v
            self.changed()

    def _artw_fit(self):
        self.art_w = None
        self.changed()

    def after_build_place(self):
        """Called when a new job arrives: show the actual art size."""
        if self.job is None:
            return
        g = self.job.geom
        old, self._loading = self._loading, True
        try:
            self.artw_var.set(f"{g.art_w:g}")
        finally:
            self._loading = old
        self.arth_lbl.configure(text=f"Art {g.art_w:.1f} x {g.art_h:.1f} mm ({g.art_w / 25.4:.2f} x "
                                     f"{g.art_h / 25.4:.2f} in). Laser-off run-ups add a few mm left "
                                     "and right (grey dashes in the preview).")

    # ================================================================ step 4
    def page_check(self, f):
        ttk.Label(f, text="4. Look & check", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Adjust the picture while watching the preview, then check the job. Nothing reaches the "
                      "laser until it passes the check.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        c = ttk.LabelFrame(f, text="Picture adjustments", style="Card.TLabelframe")
        c.pack(fill="x", pady=4)
        self.v_bright, self.v_contrast = tk.DoubleVar(), tk.DoubleVar()
        self.v_gamma, self.v_sharpen = tk.DoubleVar(value=1.0), tk.DoubleVar()
        self.v_auto, self.v_neg = tk.BooleanVar(), tk.BooleanVar()
        ch = lambda v: self.changed()
        Slider(c, "Brightness", self.v_bright, -100, 100, command=ch,
               tip="Lighter picture = less burning.").pack(fill="x", pady=2)
        Slider(c, "Contrast", self.v_contrast, -100, 100, command=ch).pack(fill="x", pady=2)
        Slider(c, "Mid-tones (gamma)", self.v_gamma, 0.3, 3.0, fmt="{:.2f}", resolution=0.05, command=ch,
               tip="Above 1 lightens the middle tones; below 1 darkens them.").pack(fill="x", pady=2)
        Slider(c, "Detail (sharpen)", self.v_sharpen, 0, 150, command=ch,
               tip="Crisper edges. The proven pine recipe uses 70.").pack(fill="x", pady=2)
        ttk.Checkbutton(c, text="Auto levels (stretch dull photos)", variable=self.v_auto,
                        command=self.changed).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(c, text="Negative - burn the light parts", variable=self.v_neg,
                        command=self.changed).pack(anchor="w")
        wrap_label(c, "Use Negative when the laser makes LIGHT marks (black anodized aluminum, slate, black "
                      "acrylic). On wood, keep it off: burning the art's light lines keeps detail. Black-on-white "
                      "artwork meant to be marked as drawn (like the card IMPORT files) also needs it off.\n"
                      "LaserGRBL never inverts a .nc file: its preview just draws burned areas light on dark, so "
                      "wood jobs look like negatives there. Compare 'In LaserGRBL' with 'Looks like' above the "
                      "preview.", style="Small.TLabel").pack(anchor="w", pady=(2, 0))
        link(c, "Negatives & LaserGRBL's preview explained",
             lambda: self.open_help("Negatives & LaserGRBL")).pack(anchor="w", pady=(4, 0))
        t = ttk.LabelFrame(f, text="Tone cut points (layered wood style)", style="Card.TLabelframe")
        t.pack(fill="x", pady=4)
        self.v_cut = [tk.DoubleVar(), tk.DoubleVar(), tk.DoubleVar()]
        for v, label, tip in zip(self.v_cut, ("Bare wood above", "1 layer above", "2 layers above"),
                                 ("Lighter than this stays bare wood (proven: 110).",
                                  "Between this and 'bare': light tone, layer 1 only (proven: 78).",
                                  "Between this and '1 layer': mid tone; darker than this: dark (proven: 48).")):
            Slider(t, label, v, 0, 255, command=ch, tip=tip).pack(fill="x", pady=2)
        ttk.Button(t, text="Back to the proven values", command=lambda: self._set_cuts((110, 78, 48))).pack(
            anchor="w", pady=(4, 0))
        k = ttk.LabelFrame(f, text="Check", style="Card.TLabelframe")
        k.pack(fill="x", pady=4)
        ttk.Button(k, text="Check job", command=self.check_job).pack(anchor="w")
        self.check_text = wrap_label(k, "Open a picture first.")
        self.check_text.pack(anchor="w", pady=(6, 0))
        s = ttk.LabelFrame(f, text="Save / LaserGRBL", style="Card.TLabelframe")
        s.pack(fill="x", pady=4)
        row = ttk.Frame(s)
        row.pack(fill="x")
        self.btn_save = ttk.Button(row, text="Save job", command=self.save_current_job)
        self.btn_save.pack(side="left")
        self.btn_export = ttk.Button(row, text="Save G-code for LaserGRBL...", command=self.export_lasergrbl)
        self.btn_export.pack(side="left", padx=6)
        self.btn_lgrbl = ttk.Button(s, text="Open in LaserGRBL", command=self.open_lasergrbl)
        self.btn_lgrbl.pack(anchor="w", pady=(6, 0))
        self.saved_lbl = wrap_label(s, "", style="Small.TLabel")
        self.saved_lbl.pack(anchor="w", pady=(4, 0))
        wrap_label(s, "Running in LaserGRBL? If the USB drops out there, don't use its Resume or Home: it can jump "
                      "to old coordinates (that burned the bed on the card). Running from step 5 here records "
                      "exactly where it stopped instead.", style="Small.TLabel").pack(anchor="w", pady=(6, 0))
        self._next(f, "Next: laser  >", 4)

    def _set_cuts(self, cuts):
        for v, c in zip(self.v_cut, cuts):
            v.set(c)
        self.changed()

    def reset_look_from_material(self):
        m = self.mat
        self.v_bright.set(m.brightness)
        self.v_contrast.set(m.contrast)
        self.v_gamma.set(m.gamma)
        self.v_sharpen.set(m.sharpen)
        self.v_auto.set(m.autolevel)
        self.v_neg.set(m.negative)
        for v, c in zip(self.v_cut, m.tone_cuts):
            v.set(c)

    def build_params(self):
        look = dict(brightness=round(self.v_bright.get()), contrast=round(self.v_contrast.get()),
                    gamma=round(self.v_gamma.get(), 2), sharpen=round(self.v_sharpen.get()),
                    autolevel=self.v_auto.get(), negative=self.v_neg.get())
        mat = self.mat
        if mat.style == "layers":
            c = sorted((int(v.get()) for v in self.v_cut), reverse=True)
            mat = mat.copy(tone_cuts=(c[0], min(c[1], c[0] - 1), min(c[2], c[1] - 2)))
        placement = Placement(copy.deepcopy(self.piece), art_w=None if self.fit_var.get() == "fill" else self.art_w,
                              fit=self.fit_var.get(), dx=self.dx, dy=self.dy)
        return mat, placement, look

    def update_check_panel(self):
        self.after_build_place()
        job, rep = self.job, self.report
        ok = bool(rep and rep["ok"] and self.compiled_gen == self.gen)
        for b in (self.btn_save, self.btn_export, self.btn_lgrbl):
            b.state(["!disabled"] if ok else ["disabled"])
        if job is None:
            self.check_text.configure(text="Open a picture first.")
            return
        if rep is None or self.compiled_gen != self.gen:
            self.check_text.configure(text="Not checked yet (it runs automatically on this page).")
            return
        lines = [("OK - " if rep["ok"] else "PROBLEM - ") + verify.summary_text(rep)]
        for p, r in zip(job.passes, rep["passes"]):
            lines.append(f"  {p.title}: {r['cells']:,} dots, about {fmt_dur(p.est_s)}  ({p.explain})")
        lines.append(f"Total: about {fmt_dur(job.est_s)} of laser time"
                     + (", plus photo pauses." if len(job.passes) > 1 else "."))
        hint = self.negative_hint()
        if hint:
            lines.append(hint)
        self.check_text.configure(text="\n".join(lines),
                                  foreground="#15803d" if rep["ok"] else "#b91c1c")
        folder = self.saved.get(self.gen)
        self.saved_lbl.configure(text=f"Saved in {folder}" if folder else "")
        self.refresh_laser_page()

    def negative_hint(self):
        """Mostly-white picture + Negative on = the background gets burned. Right for some photos, wrong for
        black-on-white artwork (like the card *-IMPORT.png files)."""
        job = self.job
        if job is None or job.gray is None or not self.v_neg.get() or self.grid_spec:
            return ""
        original = 255.0 - job.gray
        white = float((original > 225).mean())
        if white < 0.55:
            return ""
        return (f"Note: about {white:.0%} of this picture is white and Negative is on, so the laser will burn that "
                "white background. That's right for a photo on anodized/slate, but for black-on-white artwork "
                "that should be marked as drawn (like the card IMPORT files), turn Negative off.")

    def save_current_job(self, quiet=False):
        if not (self.report and self.report["ok"] and self.compiled_gen == self.gen):
            if not quiet:
                messagebox.showinfo("Check first", "Run the check (step 4) before saving.")
            return None
        if self.gen in self.saved:
            return self.saved[self.gen]
        job = self.job
        mat, placement, look = self.build_params()
        extra = dict(look=look, placement=dict(fit=placement.fit, art_w=placement.art_w, dx=self.dx, dy=self.dy),
                     picture_file=str(self.picture_path) if self.picture_path else None, grid=self.grid_spec)
        previews = {"1 LOOKS LIKE - finished piece": simulate.appearance(job),
                    "2 LASER INPUT - black means the laser fires": simulate.laser_input(job),
                    "3 IN LASERGRBL - how its preview draws the nc": simulate.lasergrbl_view(job),
                    "4 burn map - colour per pass": simulate.burn_map(job)}
        folder = jobs.save_job(job, self.report, picture=None if self.grid_spec else self.picture, previews=previews,
                               extra=extra)
        self.saved[self.gen] = folder
        self.saved_lbl.configure(text=f"Saved in {folder}")
        if not quiet:
            self.say(f"Saved the job in {folder}", "ok")
        return folder

    def export_lasergrbl(self):
        folder = self.save_current_job(quiet=True)
        if not folder:
            return
        dest = filedialog.asksaveasfilename(title="Save G-code for LaserGRBL", defaultextension=".nc",
                                            initialfile=f"{self.job.name}.nc", filetypes=[("G-code", "*.nc")])
        if not dest:
            return
        dest = Path(dest)
        shutil.copyfile(jobs.lasergrbl_path(folder), dest)
        layers = dest.with_name(dest.stem + " - one file per pass")
        if len(self.job.passes) > 1:
            layers.mkdir(exist_ok=True)
            for f in (folder / "passes").glob("*.nc"):
                shutil.copyfile(f, layers / f.name)
        messagebox.showinfo("Saved", f"Saved {dest.name}" + (f"\n\nOne file per pass (for photo pauses) is in:\n"
                                                             f"{layers}" if len(self.job.passes) > 1 else "") +
                            "\n\nIn LaserGRBL: File > Open, put the head on the start point this app expects, and check "
                            "the frame before running.")

    def open_lasergrbl(self):
        folder = self.save_current_job(quiet=True)
        if not folder:
            return
        exe = jobs.find_lasergrbl(self.settings.get("lasergrbl", ""))
        if not exe:
            messagebox.showerror("LaserGRBL not found", "Set the path to LaserGRBL.exe in Settings.")
            return
        if self.worker is not None:
            if not messagebox.askyesno("One sender at a time",
                                       "This app is connected to the laser. Disconnect so LaserGRBL can use it?"):
                return
            self.disconnect(wait=True)
        path = jobs.lasergrbl_path(folder)
        if "LaserGRBL.exe" in jobs.running_processes(("LaserGRBL.exe",)):
            self.root.clipboard_clear()
            self.root.clipboard_append(str(path))
            messagebox.showinfo("LaserGRBL is already open",
                                f"Use File > Open in LaserGRBL and paste this path (already copied):\n\n{path}")
            return
        jobs.open_in_lasergrbl(path, exe)
        self.say("Opened in LaserGRBL.", "ok")
