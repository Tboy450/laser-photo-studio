"""Steps 3 (size & placement) and 4 (look & check, save, export G-code)."""
from __future__ import annotations

import copy
from math import isfinite
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import imaging, job_package, jobs, picture_jobs, planner, presets, simulate, verify
from .dialogs import FormDialog
from .planner import Placement
from .presets import PIECES
from .preview import fmt_dur
from .ui_common import COLORS, Slider, ToolTip, link, moves_note, paint, wrap_label

PIECE_KEYS = list(PIECES)


class PlaceMixin:
    # ================================================================ step 3
    def page_place(self, f):
        ttk.Label(f, text="3. Size & placement", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Measure your piece. The start point (origin, 0,0) is the spot you'll put the laser head on "
                      "before starting (you set it in step 5).", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        c = ttk.LabelFrame(f, text="Your piece", style="Card.TLabelframe")
        c.pack(fill="x", pady=4)
        self.exact_var = tk.BooleanVar(value=False)
        self.exact_btn = ttk.Checkbutton(c, text="Use exact image size",
                                         variable=self.exact_var, command=self._exact_toggled)
        self.exact_btn.pack(anchor="w")
        self.exact_note = wrap_label(c, "", style="Small.TLabel")
        self.exact_note.pack(anchor="w")
        self.file_has_size = False
        self.saved_btn = ttk.Button(c, text="Use the size saved in the file", command=self.use_saved_size)
        self.saved_btn.pack(anchor="w", pady=(4, 8))
        self.saved_btn.state(["disabled"])
        self.piece_var = tk.StringVar()
        self.piece_box = ttk.Combobox(c, textvariable=self.piece_var, state="readonly", width=42,
                                      values=[PIECES[k]["name"] for k in PIECE_KEYS])
        self.piece_box.pack(anchor="w")
        self.piece_box.bind("<<ComboboxSelected>>", lambda e: self.set_piece(PIECE_KEYS[self.piece_box.current()]))
        wrap_label(c, 'These are physical size templates, not material settings. Margins and corner radius '
                      'are separate measurements; saved measured sizes are kept exactly.',
                   style='Small.TLabel').pack(anchor='w', pady=(4, 0))
        self.piece_note = wrap_label(c, '', style='Small.TLabel')       # what the size is now, and what wins
        self.piece_note.pack(anchor='w', pady=(2, 0))
        self.car_options = ttk.Frame(c)
        b = ttk.Button(self.car_options, text="Customize Hot Wheels...", command=self.toy_car)
        b.pack(anchor="w")
        ToolTip(b, "Pick a body type and measure your car: the windshield and rear window become no-burn zones and "
                   "the start point goes on a spot you can find, like the windshield's front edge.")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(6, 0))
        self.pw_var, self.ph_var, self.corner_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.piece_dimensions = {}
        for i, (axis, var) in enumerate((("w", self.pw_var), ("h", self.ph_var))):
            label = ttk.Label(row)
            label.grid(row=0, column=2 * i, sticky="w")
            sp = ttk.Spinbox(row, from_=1, to=600, increment=0.5, width=7, textvariable=var,
                             command=lambda a=axis:self._piece_edited(a))
            sp.grid(row=0, column=2 * i + 1, padx=(4, 10), sticky="w")
            sp.bind("<FocusOut>", lambda e,a=axis:self._piece_edited(a))
            sp.bind("<Return>", lambda e,a=axis:self._piece_edited(a))
            self.piece_dimensions[axis] = (label, sp)
        ttk.Label(row, text="mm").grid(row=0, column=4, sticky="w")
        self.proportions_var=tk.BooleanVar(value=True)
        self.proportions_btn=ttk.Checkbutton(c,text="Keep proportions (off = stretch W/H)",
                                            variable=self.proportions_var)
        self.proportions_btn.pack(anchor="w",pady=(4,0))
        self.piece_in_lbl = ttk.Label(c, style="Muted.TLabel")
        self.piece_in_lbl.pack(anchor="w", pady=(2, 0))
        row2 = ttk.Frame(c)
        row2.pack(fill="x", pady=(6, 0))
        self.shape_var = tk.StringVar(value="rect")
        self.exact_disabled = []
        for label, value in (("Rectangle", "rect"), ("Circle (lids)", "circle")):
            rb = ttk.Radiobutton(row2, text=label, value=value, variable=self.shape_var, command=self._piece_edited)
            rb.pack(side="left", padx=(0, 8))
            self.exact_disabled.append(rb)
        self.slate_rounding = ttk.Frame(c)
        self.rounding_var = tk.BooleanVar(value=False)
        self.rounding_btn = ttk.Checkbutton(self.slate_rounding, text='Rounded corners (optional)',
            variable=self.rounding_var, command=self._slate_rounding_toggled)
        self.rounding_btn.pack(side='left')
        ttk.Label(self.slate_rounding, text="Radius, mm").pack(side="left", padx=(8, 4))
        sp = ttk.Spinbox(self.slate_rounding, from_=0, to=50, increment=0.5, width=5, textvariable=self.corner_var,
                         command=self._piece_edited)
        sp.pack(side="left")
        sp.bind("<FocusOut>", lambda e: self._piece_edited())
        self.corner_spin = sp
        self.exact_disabled.append(sp)
        o = ttk.LabelFrame(f, text="Start point: where you'll put the laser head", style="Card.TLabelframe")
        o.pack(fill="x", pady=4)
        self.origin_var = tk.StringVar(value="lower-left")
        ttk.Radiobutton(o, text="Lower-left corner of the piece", value="lower-left", variable=self.origin_var,
                        command=self._piece_edited).pack(anchor="w")
        ttk.Radiobutton(o, text="Centre of the piece", value="center", variable=self.origin_var,
                        command=self._piece_edited).pack(anchor="w")
        ttk.Radiobutton(o, text="A spot I pick: click it on the preview", value="spot", variable=self.origin_var,
                        command=self._piece_edited).pack(anchor="w")
        sr = ttk.Frame(o)
        sr.pack(anchor="w", padx=(22, 0), pady=(2, 0))
        self.spot_vars = (tk.StringVar(), tk.StringVar())
        self.spot_spins = []
        for label, v in zip(("from left", "up"), self.spot_vars):
            ttk.Label(sr, text=label).pack(side="left")
            sp = ttk.Spinbox(sr, from_=0, to=600, increment=0.5, width=6, textvariable=v, command=self._piece_edited)
            sp.pack(side="left", padx=(4, 10))
            sp.bind("<FocusOut>", lambda e: self._piece_edited())
            sp.bind("<Return>", lambda e: self._piece_edited())
            self.spot_spins.append(sp)
        ttk.Label(sr, text="mm").pack(side="left")
        ttk.Button(o, text="Plan zero at the image's lower-left corner",
                   command=self.use_image_corner_zero).pack(anchor="w", pady=(4, 0))
        wrap_label(o, "Corners are easiest to find by eye. Lids are usually centred. Or pick a spot you can find on "
                      "the real piece, like the corner of a stripe or the middle of the windshield's edge: the red "
                      "crosshair shows it, and that's where you'll put the laser dot.", style="Small.TLabel").pack(
            anchor="w", pady=(2, 0))
        m = ttk.LabelFrame(f, text="Margins and no-burn zones", style="Card.TLabelframe")
        m.pack(fill="x", pady=4)
        mr = ttk.Frame(m)
        self.edge_margins = mr
        mr.pack(fill="x")
        self.circle_rim = ttk.Frame(m)
        self.rim_var = tk.StringVar()
        ttk.Label(self.circle_rim, text="Unprinted rim all around (mm)").pack(side="left")
        rim = ttk.Spinbox(self.circle_rim, from_=0, to=100, increment=.1, width=7,
                          textvariable=self.rim_var, command=self._piece_edited)
        rim.pack(side="left", padx=6)
        for event in ("<Return>", "<FocusOut>"):
            rim.bind(event, lambda _event: self._piece_edited())
        self.rim_note = ttk.Label(self.circle_rim)
        self.rim_note.pack(side="left")
        self.margin_vars = []
        for i, label in enumerate(("Left", "Bottom", "Right", "Top")):
            ttk.Label(mr, text=label).grid(row=i // 2, column=(i % 2) * 2, sticky="w", pady=1)
            v = tk.StringVar()
            sp = ttk.Spinbox(mr, from_=0, to=100, increment=0.5, width=6, textvariable=v, command=self._piece_edited)
            sp.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(4, 16), pady=1)
            sp.bind("<FocusOut>", lambda e: self._piece_edited())
            self.margin_vars.append(v)
            self.exact_disabled.append(sp)
        ttk.Label(mr, text="mm").grid(row=0, column=4, sticky="w")
        wrap_label(m, "Margins reserve unprinted space inside the piece. Whole picture fits within that area; "
                      "Fill crops source edges. Nudging can move art into a margin, where its marks are masked. "
                      "Margins do not remove a border drawn inside the image.",
                   style="Small.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(m, text="No-burn zones (holes, twine, screws, existing art):").pack(anchor="w", pady=(8, 2))
        self.ko_list = paint(tk.Listbox(m, height=4, activestyle="none", exportselection=False), background="field", foreground="ink",
                             selectbackground="select", selectforeground="select_ink", highlightbackground="border")
        self.ko_list.pack(fill="x")
        self.ko_list.bind("<<ListboxSelect>>", lambda e: self.preview.refresh())
        self.ko_list.bind("<Double-Button-1>", lambda e: self.edit_keepout())
        kr = ttk.Frame(m)
        kr.pack(fill="x", pady=(4, 0))
        ttk.Button(kr, text="+ Hole / circle", command=lambda: self.add_keepout("circle")).pack(side="left")
        ttk.Button(kr, text="+ Rectangle", command=lambda: self.add_keepout("rect")).pack(side="left", padx=4)
        ttk.Button(kr, text="Edit selected", command=self.edit_keepout).pack(side="left", padx=4)
        ttk.Button(kr, text="Remove", command=self.remove_keepout).pack(side="left")
        self.zone_edit_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(m, text="Move / resize no-burn zones on the preview", variable=self.zone_edit_var,
                        command=lambda: self.preview.refresh()).pack(anchor="w", pady=(6, 0))
        wrap_label(m, "Select a window or zone, then drag inside it to move it or drag a corner to resize. "
                      "Double-click a zone for measurements. This edits the mask; it never moves the laser.",
                   style="Small.TLabel").pack(anchor="w")
        a = ttk.LabelFrame(f, text="Picture size", style="Card.TLabelframe")
        a.pack(fill="x", pady=4)
        self.fit_var = tk.StringVar(value="whole")
        for label, value in (("Whole picture", "whole"), ("Fill the area (crops the edges)", "fill"),
                             ("Set engraved width (outside marks)", "marks")):
            rb = ttk.Radiobutton(a, text=label, value=value, variable=self.fit_var, command=self._fit_changed)
            rb.pack(anchor="w")
            self.exact_disabled.append(rb)
        ar = ttk.Frame(a)
        ar.pack(fill="x", pady=(6, 0))
        self.artw_label = ttk.Label(ar, text="Requested width")
        self.artw_label.pack(side="left")
        self.artw_var = tk.StringVar()
        self.artw_spin = ttk.Spinbox(ar, from_=2, to=600, increment=1, width=7, textvariable=self.artw_var,
                                     command=self._artw_edited)
        self.artw_spin.pack(side="left", padx=4)
        self.artw_spin.bind("<FocusOut>", lambda e: self._artw_edited())
        self.artw_spin.bind("<Return>", lambda e: self._artw_edited())
        ttk.Label(ar, text="mm").pack(side="left")
        b = ttk.Button(ar, text="Largest that fits", command=self._artw_fit)
        b.pack(side="left", padx=8)
        self.exact_disabled.append(b)
        self.arth_lbl = wrap_label(a, "", style="Muted.TLabel")
        self.arth_lbl.pack(anchor="w", pady=(4, 0))
        self.clearance_lbl = wrap_label(a, "Open a picture to see edge clearances.", style="Small.TLabel")
        self.clearance_lbl.pack(anchor="w", pady=(4, 0))
        p = ttk.LabelFrame(f, text="Move the picture (the machine doesn't move)", style="Card.TLabelframe")
        p.pack(fill="x", pady=4)
        self.nudge_step = tk.StringVar(value="1")
        self._nudge_pad(p, self.nudge)
        self.offset_lbl = ttk.Label(p, style="Muted.TLabel")
        self.offset_lbl.pack(anchor="w", pady=(4, 0))
        wrap_label(p, "Left/right and up/down move the artwork from its fitted position. They do not move "
                      "the head or change job zero. Set the physical head at the selected start point in step 5.",
                   style="Small.TLabel").pack(anchor="w", pady=(4, 0))
        self._next(f, "Next: look & check  >", 3)
        self.sync_place_fields()

    def _nudge_pad(self, parent, fn):
        moves_note(parent, "art", "Moves the picture on the piece (its dashed box). Nothing moves on the "
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
        if self.fit_var.get() == "exact":
            self.say("Exact size: the picture fills its box, so there's nothing to nudge. Move the head, or tick "
                     "'Move the picture with the head' in step 5.", "warn")
            return
        if dx is None:
            self.dx = self.dy = 0.0
        else:
            st = float(self.nudge_step.get())
            self.dx = round(self.dx + dx * st, 2)
            self.dy = round(self.dy + dy * st, 2)
        self.sync_place_fields()
        self.changed(150)

    def _exact_toggled(self, size=None):
        old_zero = planner.piece_rect(self.piece)[:2]
        if self.protect_piece_outline() or self.fit_var.get() == "art-exact":
            if self.exact_var.get():
                if self.fit_var.get() != "art-exact":
                    self._before_art_exact = (self.fit_var.get(), self.art_w)
                    if self.fit_var.get() == "marks":
                        self.art_w = (self.job.geom.art_w if self.job and not self.layout_pending else None)
                self.fit_var.set("art-exact")
                if size is not None:
                    self.art_w = size[0]
            else:
                fit, self.art_w = self._before_art_exact or ("whole", self.art_w)
                self.fit_var.set(fit)
                self._before_art_exact = None
            self.piece_user_set = True
            self.sync_place_fields()
            self.changed()
            return
        if self.exact_var.get():
            if self.fit_var.get() != "exact":
                self._before_exact = (copy.deepcopy(self.piece), self.piece_key, self.piece_user_set,
                                      self.fit_var.get(), self.art_w, self.dx, self.dy, self.proportions_var.get())
            w, h = size or (self.piece["w"], self.piece["h"])
            if size is None and self.picture is not None and self.proportions_var.get():
                if self.fit_var.get() != "exact":
                    _, placement, _ = self.build_params()
                    w = planner.layout(self.picture.size, placement, self.mat.pitch).art_w
                h = w * self.picture.height / self.picture.width
            self.piece_key = "custom"
            # Keep explicitly placed window masks; default the new box to its lower-left.
            self.piece = dict(copy.deepcopy(self.piece), name="Exact size", shape="rect", w=w, h=h,
                              origin="lower-left", margins=(0.0, 0.0, 0.0, 0.0), corner=0.0)
            self.piece_user_set = True
            self.fit_var.set("exact")
            self.dx = self.dy = 0.0
            self.art_w = None
        elif self._before_exact is not None:
            (self.piece, self.piece_key, self.piece_user_set, fit, self.art_w,
             self.dx, self.dy, proportions) = self._before_exact
            self._before_exact = None
            self.fit_var.set(fit)
            self.proportions_var.set(proportions)
        else:
            self.fit_var.set("whole")
            self.art_w = None
        self.sync_place_fields()
        if old_zero != planner.piece_rect(self.piece)[:2]:
            self.start_point_moved()
        self.changed()

    def protect_piece_outline(self):
        return self.fit_var.get() != "exact" and (
            self.piece.get("shape") == "circle" or bool(self.piece.get("outline")))

    def saved_size(self):
        """The size stored in the open picture's file, turned with the picture."""
        s = imaging.saved_size_mm(self.picture_path) if self.picture_path else None
        return (s[1], s[0]) if s and self.rotate % 2 else s

    def show_saved_size(self):
        s = self.saved_size()
        self.file_has_size = s is not None
        self.saved_btn.configure(text=f"Use the size saved in the file: {s[0]:g} x {s[1]:g} mm" if s else
                                 "Use the size saved in the file")
        self.saved_btn.state(["!disabled"] if s else ["disabled"])

    def use_saved_size(self):
        if size := self.saved_size():
            self.exact_var.set(True)
            self._exact_toggled(size)

    def set_piece(self, key, user=True):
        self._before_art_exact = None
        self._before_exact = None
        if self.fit_var.get() in ("exact", "art-exact"):
            self.fit_var.set("whole")
        self.piece_key = key
        self.piece = copy.deepcopy(PIECES[key])
        if user:
            self.piece_user_set = True
        self.art_w = None
        self.dx = self.dy = 0.0
        self.sync_place_fields()
        self.changed()
        if key == "car" and user:
            self.root.after(100, self.toy_car)

    def toy_car(self):
        from .dialogs import CarDialog
        d = CarDialog(self.root, self.piece.get("car") or presets.car_values("mustang")).result
        if d:
            self.use_car(d)

    def use_car(self, values):
        self._before_art_exact = None
        self._before_exact = None
        if self.fit_var.get() in ("exact", "art-exact"):
            self.fit_var.set("whole")
        self.piece_key = "car"
        self.piece = presets.car_piece(values)
        self.piece_user_set = True
        self.art_w = None
        self.dx = self.dy = 0.0
        self.sync_place_fields()
        self.changed()
        self.say(f"{self.piece['name']}: windows are no-burn zones. The labeled Job zero crosshair is the origin.", "ok")

    def sync_place_fields(self):
        if not hasattr(self, "pw_var"):
            return
        old, self._loading = self._loading, True
        try:
            pc = self.piece
            self._displayed_fit = self.fit_var.get()
            self.piece_var.set(f"Exact image {pc['w']:g} x {pc['h']:g} mm" if self.fit_var.get() == 'exact'
                               else presets.piece_choice_label(pc))
            if hasattr(self, 'piece_note'):
                self.piece_note.configure(text=presets.piece_explanation(
                    pc, self.fit_var.get(), loaded_job=bool(getattr(self, 'source_provenance', None))))
            self.pw_var.set(f"{pc['w']:g}")
            self.ph_var.set(f"{pc['h']:g}")
            exact = self.fit_var.get() == "exact"
            art_exact = self.fit_var.get() == "art-exact"
            circle = pc.get("shape") == "circle" and not exact
            self.saved_btn.state(["!disabled"] if self.file_has_size else ["disabled"])
            self.exact_note.configure(text=(
                "Set Requested width under Picture size. Exact image size keeps the image proportions, rim, "
                "job zero and placement. The usable face can limit the size. Turning Exact off restores your "
                "previous sizing choice." if self.protect_piece_outline() or art_exact else
                "Exact image size creates a rectangular image box with zero margins and a lower-left job zero. "
                "Use Whole picture to keep the piece "
                "and its margins. Keep proportions on to avoid stretching."))
            self.piece_dimensions["w"][0].configure(text="Outside diameter" if circle else
                                                    "Image width" if exact else "Outside width")
            self.piece_dimensions["h"][0].configure(text="Image height" if exact else "Outside height")
            for widget in self.piece_dimensions["h"]:
                widget.grid_remove() if circle else widget.grid()
            self.shape_var.set(pc.get("shape", "rect"))
            self.corner_var.set(f"{pc.get('corner', 0):g}")
            self.rounding_var.set(pc.get('corner', 0) > 0)
            self.origin_var.set(pc.get("origin", "lower-left"))
            spot = pc.get("spot") or (pc["w"] / 2, pc["h"] / 2)
            for v, val in zip(self.spot_vars, spot):
                v.set(f"{val:g}")
            for sp in self.spot_spins:
                sp.state(["!disabled"] if pc.get("origin") == "spot" else ["disabled"])
            for v, val in zip(self.margin_vars, pc.get("margins", (0, 0, 0, 0))):
                v.set(f"{val:g}")
            margins = pc.get("margins", (0, 0, 0, 0))
            if circle:
                self.edge_margins.pack_forget()
                if not self.circle_rim.winfo_manager():
                    self.circle_rim.pack(fill="x", before=self.circle_rim.master.pack_slaves()[0])
                uniform = len(set(margins)) == 1
                self.rim_var.set(f"{margins[0]:g}" if uniform else "")
                self.rim_note.configure(text=(f"Usable diameter {pc['w'] - 2*margins[0]:g} mm" if uniform
                                              else "Unequal saved margins. Enter one rim to refit."))
            else:
                self.circle_rim.pack_forget()
                if not self.edge_margins.winfo_manager():
                    self.edge_margins.pack(fill="x", before=self.edge_margins.master.pack_slaves()[0])
            self.ko_list.delete(0, "end")
            for k in pc.get("keepouts", []):
                if k.get("kind") == "circle":
                    self.ko_list.insert("end", f"Hole: centre {k['x']:g}, {k['y']:g} mm, radius {k['r']:g} mm")
                else:
                    self.ko_list.insert("end", f"Rectangle: from {k['x']:g}, {k['y']:g} mm, {k['w']:g} x {k['h']:g} mm")
            can_set_width = self.fit_var.get() in ("whole", "art-exact", "marks")
            self.artw_label.configure(text="Engraved width" if self.fit_var.get() == "marks" else "Requested width")
            self.artw_var.set(f"{self.art_w:g}" if self.art_w is not None and can_set_width else "")
            inches = (f"{pc['w'] / 25.4:.2f} in across" if circle else
                      f"{pc['w'] / 25.4:.2f} x {pc['h'] / 25.4:.2f} in"
                      f" | corner radius {pc.get('corner', 0):g} mm")
            self.piece_in_lbl.configure(text=f"= {inches}")
            self.offset_lbl.configure(text=("Centred." if not (self.dx or self.dy) else
                                            f"Moved {abs(self.dx):g} mm {'right' if self.dx >= 0 else 'left'}, "
                                            f"{abs(self.dy):g} mm {'up' if self.dy >= 0 else 'down'} from centre."))
            self.exact_var.set(exact or art_exact)
            self.proportions_btn.state(["!disabled"] if exact else ["disabled"])
            self.artw_spin.state(["!disabled"] if can_set_width else ["disabled"])
            for widget in self.exact_disabled:
                widget.state(["disabled"] if exact else ["!disabled"])
            self.sync_piece_options()
        finally:
            self._loading = old

    def sync_piece_options(self):
        if not hasattr(self, 'car_options'):
            return
        car = self.piece_key == 'car' or bool(self.piece.get('car'))
        slate = self.piece_key == 'coaster100' or (
            self.piece_key == 'custom' and self.mat.look == 'slate' and self.piece.get('shape') == 'rect')
        for frame, visible in ((self.car_options, car), (self.slate_rounding, slate and not car)):
            if visible and not frame.winfo_manager():
                frame.pack(anchor='w', pady=(6, 0))
            elif not visible and frame.winfo_manager():
                frame.pack_forget()
        self.rounding_btn.state(['disabled'] if self.exact_var.get() else ['!disabled'])
        self.corner_spin.state(['!disabled'] if self.rounding_var.get() and not self.exact_var.get() else ['disabled'])

    def _slate_rounding_toggled(self):
        self.corner_var.set(str(float(self.corner_var.get() or 0) or 8) if self.rounding_var.get() else '0')
        self._piece_edited()

    def _piece_edited(self, axis=None):
        if self._loading:
            return
        def number(var, label, minimum=0):
            try:
                value = float(var.get())
            except ValueError:
                value = float('nan')
            if not isfinite(value) or value < minimum:
                raise ValueError(f"Enter a number of at least {minimum:g} mm for {label}.")
            return value

        try:
            pc = self.piece.copy()
            ratio=pc['w']/pc['h']
            pc["w"] = number(self.pw_var, "width", 1)
            pc["h"] = number(self.ph_var, "height", 1)
            if self.fit_var.get()=='exact' and self.proportions_var.get():
                if axis=='w': pc['h']=pc['w']/ratio
                elif axis=='h': pc['w']=pc['h']*ratio
            pc["shape"] = self.shape_var.get()
            if pc["shape"] == "circle":
                pc["h"] = pc["w"]
            pc["corner"] = number(self.corner_var, "corner radius")
            pc["origin"] = self.origin_var.get()
            if pc["origin"] == "spot":
                pc["spot"] = [round(min(limit, number(v, label)), 6)
                              for limit, v, label in zip((pc["w"], pc["h"]), self.spot_vars, ("zero X", "zero Y"))]
            pc["margins"] = tuple(number(v, label + " margin") for v, label in
                                  zip(self.margin_vars, ("left", "bottom", "right", "top")))
            if pc["shape"] == "circle":
                rim = (number(self.rim_var, "the circular rim") if self.piece.get("shape") == "circle"
                       else max(pc["margins"]))
                if 2 * rim >= pc["w"]:
                    raise ValueError("The rim must leave a positive usable diameter.")
                pc["margins"] = (rim,) * 4
            if self.fit_var.get() == "exact":
                pc.update(shape="rect", corner=0.0, margins=(0.0, 0.0, 0.0, 0.0))
        except ValueError as exc:
            self.sync_place_fields()
            self.say(f"{exc} Restored the previous piece dimensions and placement.", "warn")
            return
        if pc["shape"] == "circle" and self.piece.get("shape") != "circle" and len(set(self.piece.get("margins", ()))) > 1:
            self.say(f"The circle uses the largest previous edge margin, {pc['margins'][0]:g} mm, "
                     "all around. Edit Unprinted rim to change it.", "ok")
        self.piece = pc
        self.piece_user_set = True
        self.sync_place_fields()
        self.changed()

    def use_image_corner_zero(self):
        if (self._picture_job_in_use() or self.layout_pending or not self.job or self.picture is None or
                self.gfile or self.grid_spec):
            self.say("Wait for the current operation and image layout first.", "warn")
            return
        piece, geom = self.piece, self.job.geom
        ax, ay = geom.x0 - geom.piece_rect[0], geom.y0 - geom.piece_rect[1]
        if (piece.get("shape") != "rect" or piece.get("outline") or piece.get("corner", 0) > 0 or
                not (-1e-7 <= ax <= piece["w"] + 1e-7 and -1e-7 <= ay <= piece["h"] + 1e-7)):
            self.say("Choose a point on the piece. This image corner is only supported inside a rectangular piece.",
                     "warn")
            return
        previous_zero = planner.piece_rect(piece)[:2]
        piece.update(origin="spot", spot=[round(ax, 6), round(ay, 6)])
        self.piece_user_set = True
        self.sync_place_fields()
        if previous_zero != planner.piece_rect(piece)[:2]:
            self.start_point_moved()
        self.changed()
        self.say("Image corner selected. Check travel around the image and set the physical job zero in step 5.")

    def pick_spot(self, from_left, from_bottom):
        """The preview was clicked in step 3 with 'A spot I pick' on: that spot becomes the start point."""
        pc = self.piece
        pc["origin"] = "spot"
        pc["spot"] = [round(min(pc["w"], max(0.0, from_left)), 1), round(min(pc["h"], max(0.0, from_bottom)), 1)]
        self.piece_user_set = True
        self.sync_place_fields()
        self.changed()
        self.say(f"Start point: {pc['spot'][0]:g} mm from the left edge, {pc['spot'][1]:g} mm up from the bottom "
                 "(Job zero). Put the laser dot there in step 5.", "ok")

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

    def zone_editing(self):
        return self.nb.index("current") == 2 and self.zone_edit_var.get() and not self.gfile

    def selected_keepout(self):
        selected = self.ko_list.curselection()
        return selected[0] if selected and selected[0] < len(self.piece.get("keepouts", [])) else None

    def select_keepout(self, index):
        self.ko_list.selection_clear(0, "end")
        self.ko_list.selection_set(index)
        self.ko_list.see(index)

    def update_keepout(self, index, zone, *, live=False):
        self.piece["keepouts"][index] = zone
        self.piece_user_set = True
        self.completed_checks.clear()
        self.report = None
        if live:
            self.gen += 1
            self.layout_pending = True
            self.refresh_laser_page()
            self.preview.redraw()
        else:
            self.sync_place_fields()
            self.select_keepout(index)
            self.changed(0)

    def edit_keepout(self):
        index = self.selected_keepout()
        if index is None:
            self.say("Select a window or no-burn zone first.", "warn")
            return
        zone = self.piece["keepouts"][index]
        fields = [("x", "X from the piece's left edge (mm)", zone["x"], "float"),
                  ("y", "Y up from the piece's bottom edge (mm)", zone["y"], "float")]
        dimensions = [("r", "Radius")] if zone["kind"] == "circle" else [("w", "Width"), ("h", "Height")]
        for key, label in dimensions:
            fields.append((key, label + " (mm)", zone[key], "float"))
        values = FormDialog(self.root, "Edit no-burn zone", fields,
                            intro="Only the no-burn mask changes. The laser head does not move.").result
        if values is not None:
            from .keepouts import constrain_zone
            try:
                zone = constrain_zone(dict(zone, **values), self.piece["w"], self.piece["h"])
            except ValueError as e:
                messagebox.showerror("Check the zone", str(e))
                return
            self.update_keepout(index, zone)

    def _fit_changed(self):
        if self.fit_var.get() == self._displayed_fit:
            return
        marks = self.job.burn_bbox() if self.fit_var.get() == "marks" and self.job and not self.layout_pending else None
        self.art_w = round(marks[2] - marks[0], 3) if marks else None
        self.piece_user_set |= self.fit_var.get() == "marks"
        self.sync_place_fields()
        self.changed()

    def _artw_edited(self):
        if self._loading or self.fit_var.get() not in ("whole", "art-exact", "marks"):
            return
        text = self.artw_var.get().strip()
        if not text:
            self._artw_fit()
            return
        try:
            v = float(text)
        except ValueError:
            v = float('nan')
        if not isfinite(v) or v <= 1:
            self.sync_place_fields()
            self.say("Requested width must be greater than 1 mm. Previous width restored.", "warn")
            return
        if v != self.art_w:
            self.art_w = v
            self.piece_user_set = True
            self.changed()

    def _artw_fit(self):
        if self.fit_var.get() not in ("whole", "art-exact", "marks"):
            return
        self.artw_var.set("")
        if self.art_w is None:
            return
        self.art_w = None
        self.changed()

    @staticmethod
    def width_limit_note(geom, fit, requested):
        if fit == "saved-whole":
            return "Reproducing the original saved grid. Select Whole picture to refit proportionally."
        if fit == "art-exact" and requested is not None:
            if geom.art_w + 1e-8 < requested:
                return "The usable face limits the requested size. The image keeps its proportions."
            return "Exact artwork width. Row and column spacing adjust to fit this size."
        if fit != "whole" or requested is None:
            return ""
        rounded = round(requested / geom.x_pitch) * geom.x_pitch
        if geom.art_w + 1e-8 < rounded:
            return f"Width limited by the usable face to {geom.cols} columns."
        if abs(geom.art_w - requested) > 1e-8:
            return "Requested width rounded to the nearest grid column."
        return ""

    def after_build_place(self):
        """Called when a new job arrives: show the actual art size."""
        if self.layout_pending:
            self.arth_lbl.configure(text="Calculating grid size…")
            self.clearance_lbl.configure(text="Updating layout — edge clearances are not current yet.")
            return
        if self.job is None:
            self.arth_lbl.configure(text="")
            self.clearance_lbl.configure(text="Open a picture to see edge clearances.")
            return
        g = self.job.geom
        width_note = self.width_limit_note(g, self.fit_var.get(), self.art_w)
        if self.fit_var.get() in ("whole", "art-exact") and self.art_w is None:
            width_note = "Requested width is blank for automatic fit."
        if self.fit_var.get() == "marks":
            marks = self.job.burn_bbox()
            actual = f"Engraved width: {marks[2] - marks[0]:.2f} mm." if marks else "No powered marks fit."
            request = f" Requested: {self.art_w:g} mm." if self.art_w is not None else ""
            width_note = " ".join(line for line in (actual + request, self.job.sizing_note) if line)
        footprint = "Actual grid" if self.job.gray is not None else "Art"
        self.arth_lbl.configure(text=f"{footprint}: {g.art_w:.2f} x {g.art_h:.2f} mm ({g.art_w / 25.4:.2f} x "
                                     f"{g.art_h / 25.4:.2f} in). Laser-off run-ups add a few mm left "
                                     "and right (grey dashes in the preview).\n"
                                     f"Picture lower-left: X {g.x0:.3f}, Y {g.y0:.3f} mm from start 0,0. "
                                     "Blank space inside the file stays inside this box."
                                     + (f"\n{width_note}" if width_note else ""))
        px0, py0, px1, py1 = g.piece_rect
        gaps = (g.x0 - px0, g.y0 - py0, px1 - g.x1, py1 - g.yt)
        text = "Picture-box gaps to outside edges (mm): " + ", ".join(
            f"{side} {value:.2f}" for side, value in zip(("Left", "Bottom", "Right", "Top"), gaps))
        ux0, uy0, ux1, uy1 = g.usable_rect
        if min(g.x0 - ux0, g.y0 - uy0, ux1 - g.x1, uy1 - g.yt) < -0.001:
            text += "\nPicture enters a margin or extends outside the piece; affected marks are masked."
        text += ("\nNegative gap = extends outside the piece. These are box clearances, not the nearest marks. "
                 "Round edges and no-burn zones can clip marks inside the box. Image Trace follows the remaining marks. "
                 "Total travel includes laser-off run-ups.")
        self.clearance_lbl.configure(text=text)

    # ================================================================ step 4
    def page_check(self, f):
        ttk.Label(f, text="4. Look & check", style="H1.TLabel").pack(anchor="w")
        self.edit_mode_lbl = wrap_label(f, '', style='Small.TLabel')
        self.edit_mode_lbl.pack(anchor='w', pady=(2, 4))
        wrap_label(f, "Adjust the picture while watching the preview, then check the job. Nothing reaches the "
                      "laser until it passes the check.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        c = ttk.LabelFrame(f, text="Picture adjustments", style="Card.TLabelframe")
        c.pack(fill="x", pady=4)
        self.v_bright, self.v_contrast = tk.DoubleVar(), tk.DoubleVar()
        self.v_gamma, self.v_sharpen = tk.DoubleVar(value=1.0), tk.DoubleVar()
        self.v_auto, self.v_neg = tk.BooleanVar(), tk.BooleanVar()
        self.v_black, self.v_white = tk.DoubleVar(value=0), tk.DoubleVar(value=255)
        self.look_mode = wrap_label(c, 'Manual controls. Release a slider to update the preview.', style='Small.TLabel')
        self.look_mode.pack(anchor='w')
        self.slate_compare_btn = ttk.Button(c, text='Compare darker slate tones...', command=self.compare_slate_tones)
        self.glass_compare_btn = ttk.Button(c, text='Compare glass dot patterns...', command=self.compare_glass_patterns)
        ch = self._manual_look_changed
        Slider(c, 'Black point', self.v_black, 0, 254, command=ch).pack(fill='x', pady=2)
        Slider(c, 'White point', self.v_white, 1, 255, command=ch).pack(fill='x', pady=2)
        Slider(c, "Brightness", self.v_bright, -100, 100, command=ch,
               tip="Brightens the source photo before inversion. Negative determines whether light or dark parts burn.").pack(fill="x", pady=2)
        Slider(c, "Contrast", self.v_contrast, -100, 100, command=ch).pack(fill="x", pady=2)
        Slider(c, "Mid-tones (gamma)", self.v_gamma, 0.3, 3.0, fmt="{:.2f}", resolution=0.05, command=ch,
               tip="Above 1 lightens the middle tones; below 1 darkens them.").pack(fill="x", pady=2)
        Slider(c, "Detail (sharpen)", self.v_sharpen, 0, 150, command=ch,
               tip="Crisper edges. The proven pine recipe uses 70.").pack(fill="x", pady=2)
        ttk.Button(c, text='Auto levels - set visible controls', command=self.auto_levels).pack(anchor='w', pady=(4, 0))
        wrap_label(c, 'Auto sets the Black/White point sliders and resets brightness/contrast/gamma to neutral. '
                      'Later edits are Manual. There is no hidden Auto correction left running.',
                   style='Small.TLabel').pack(anchor='w', pady=(2, 0))
        ttk.Checkbutton(c, text="Negative - burn the light parts", variable=self.v_neg,
                        command=self.changed).pack(anchor="w")
        wrap_label(c, "Use Negative when the laser makes LIGHT marks (black anodized aluminum, slate, black "
                      "acrylic). On wood, keep it off: burn the art's dark parts. Black-on-white "
                      "artwork meant to be marked as drawn (like the card IMPORT files) also needs it off.\n"
                      "The preview shows the expected material finish and the separate burn map, "
                      "so you can check polarity before saving.", style="Small.TLabel").pack(
                          anchor="w", pady=(2, 0))
        link(c, "Negative & previews explained",
             lambda: self.open_help("Negative & previews")).pack(anchor="w", pady=(4, 0))
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
        self.check_section = k
        self.look_frames = (c, t)
        self._locked_picture_widgets = {}
        k.pack(fill="x", pady=4)
        ttk.Button(k, text="Check job", command=self.check_job).pack(anchor="w")
        self.check_text = wrap_label(k, "Open a picture first.")
        self.check_text.pack(anchor="w", pady=(6, 0))
        pair = ttk.Frame(k)
        pair.pack(fill="x", pady=(6, 0))
        self.btn_pair = ttk.Button(pair, text="Compare another pass…", command=self.choose_pair)
        self.btn_pair.pack(side="left")
        self.btn_clear_pair = ttk.Button(pair, text="Clear pair", command=self.clear_pair)
        self.btn_clear_pair.pack(side="left", padx=6)
        s = ttk.LabelFrame(f, text="Save / export", style="Card.TLabelframe")
        s.pack(fill="x", pady=4)
        row = ttk.Frame(s)
        row.pack(fill="x")
        self.btn_save = ttk.Button(row, text="Save job", command=self.save_current_job)
        self.btn_save.pack(side="left")
        self.btn_export = ttk.Button(row, text="Export G-code (.nc)...", command=self.export_gcode)
        self.btn_export.pack(side="left", padx=6)
        self.btn_package = ttk.Button(s, text="Save editable Studio package...", command=self.export_studio_package)
        self.btn_package.pack(anchor="w", pady=(6, 0))
        self.saved_lbl = wrap_label(s, "", style="Small.TLabel")
        self.saved_lbl.pack(anchor="w", pady=(4, 0))
        wrap_label(s, "Engrave checked jobs in step 5 for progress, photo pauses and verified "
                      "resume. Exported G-code is for compatible external workflows; always verify "
                      "the origin and machine settings before using it elsewhere.",
                   style="Small.TLabel").pack(anchor="w", pady=(6, 0))
        self._next(f, "Next: laser  >", 4)

    def _set_cuts(self, cuts):
        for v, c in zip(self.v_cut, cuts):
            v.set(c)
        self.changed()

    def sync_picture_edit_mode(self):
        if not hasattr(self, 'look_frames'):
            return
        locked = bool(self.gfile or self.picture is None)
        editable = not locked and not self.grid_spec
        for frame, visible in zip(self.look_frames, (editable, editable and self.mat.style == "layers")):
            if visible and not frame.winfo_manager():
                frame.pack(fill="x", pady=4, before=self.check_section)
            elif not visible and frame.winfo_manager():
                frame.pack_forget()
        slate = self.mat.look == 'slate' and not locked and not self.grid_spec
        if slate and not self.slate_compare_btn.winfo_manager():
            self.slate_compare_btn.pack(anchor='w', before=self.look_mode, pady=(0, 5))
        elif not slate:
            self.slate_compare_btn.pack_forget()
        glass = self.mat.look == 'glass' and not locked and not self.grid_spec
        if glass and not self.glass_compare_btn.winfo_manager():
            self.glass_compare_btn.pack(anchor='w', before=self.look_mode, pady=(0, 5))
        elif not glass:
            self.glass_compare_btn.pack_forget()
        if self.gfile:
            message = ('G-code check only: movement/power are already encoded. Picture, material and size controls '
                       'cannot edit these commands. Open saved Studio picture job or the original picture in step 1.')
        elif self.picture is None or self.grid_spec:
            message = ('No editable picture loaded. Open saved Studio picture job or the original picture in step 1. '
                       'Generated grids use their own grid parameters, not these picture sliders.')
        else:
            message = 'Editable source picture: adjustments rebuild the preview and must pass verification before printing.'
            source = (self.source_provenance or {}).get('source') or {}
            if glass and isinstance(source, dict) and 'mapped to marking' in str(source.get('transform', '')):
                message += '\nThis prepared input already maps bright details to marks. Leave Negative off to keep that mapping.'
        self.edit_mode_lbl.configure(text=message)
        for i in (1, 2):
            self.nb.tab(i, state='disabled' if self.gfile else 'normal')
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        for frame in self.look_frames:
            for widget in descendants(frame):
                if widget.winfo_class() not in ('TScale', 'TCheckbutton', 'TButton', 'TEntry'):
                    continue
                if locked:
                    if widget not in self._locked_picture_widgets:
                        self._locked_picture_widgets[widget] = widget.instate(['disabled'])
                    widget.state(['disabled'])
                elif widget in self._locked_picture_widgets:
                    widget.state(['disabled'] if self._locked_picture_widgets.pop(widget) else ['!disabled'])

    def reset_look_from_material(self):
        m = self.mat
        self.look_mode.configure(text="Starting picture adjustments from the current recipe. Edit a control to update the preview.")
        self.v_bright.set(m.brightness)
        self.v_contrast.set(m.contrast)
        self.v_gamma.set(m.gamma)
        self.v_sharpen.set(m.sharpen)
        self.v_auto.set(m.autolevel)
        self.v_black.set(m.black_point)
        self.v_white.set(m.white_point)
        prepared=bool(self.picture_path and self.picture_path.stem.upper().endswith('IMPORT'))
        self.v_neg.set(False if prepared else m.negative)
        self.expose_legacy_auto()

    def _manual_look_changed(self, *_):
        if self._loading:
            return
        self.look_mode.configure(text='Manual: preview uses the visible controls. Release a slider to update.')
        self.changed()

    def apply_slate_comparison(self, generation, value, point='black_point'):
        if point not in ('black_point','white_point'):
            return False
        if (generation != self.gen or self.mat.look != 'slate' or self.picture is None or self.gfile
                or self.grid_spec or jobs.active_runner() or self.perim_running):
            self.say('Settings changed or a job is active. Reopen the comparison when ready.', 'warn')
            return False
        (self.v_black if point == 'black_point' else self.v_white).set(value)
        self._manual_look_changed()
        return True

    def compare_slate_tones(self):
        if (self.mat.look != 'slate' or self.picture is None or self.gfile or self.grid_spec
                or self.layout_pending or self.layout_error or jobs.active_runner() or self.perim_running):
            self.say('Open an editable slate photo and finish active operations before comparing.', 'warn')
            return
        from . import slate_tones
        from .planner import layout
        from PIL import ImageTk
        try:
            material, placement, look = self.build_params()
            crop = layout(self.picture.size, placement, material.pitch).crop
            choices = slate_tones.options(look)
            previews = [slate_tones.preview(self.picture, values, crop) for _, values in choices]
        except (ValueError, tk.TclError) as exc:
            self.say(str(exc), 'warn')
            return
        generation = self.gen
        point = 'black_point' if look['negative'] else 'white_point'
        point_label = 'Black point' if point == 'black_point' else 'White point'
        win = tk.Toplevel(self.root)
        win.title('Compare slate photo shadows')
        win.transient(self.root)
        win.resizable(False, False)
        outer = ttk.Frame(win, padding=14); outer.pack(fill='both', expand=True)
        wrap_label(outer, 'Tone comparison before dithering - not a physical-result prediction. Darker shadows affect '
            'the whole photo, including dark fur and clothing. Background-only editing is not applied.', width=750).pack(fill='x')
        tiles = ttk.Frame(outer); tiles.pack(pady=10)
        selected = tk.IntVar(win, value=0)
        win._tone_images = []
        for i, ((title, values), im) in enumerate(zip(choices, previews)):
            tile = ttk.Frame(tiles, padding=5); tile.grid(row=0, column=i, sticky='n')
            photo = ImageTk.PhotoImage(im, master=win); win._tone_images.append(photo)
            ttk.Label(tile, image=photo).pack()
            ttk.Radiobutton(tile, text=f'{title}\n{point_label} {values.get(point, 0 if point == "black_point" else 255)}',
                variable=selected, value=i).pack(anchor='w', pady=(5, 0))
        buttons = ttk.Frame(outer); buttons.pack(fill='x')
        def apply():
            if selected.get() == 0 or self.apply_slate_comparison(generation, choices[selected.get()][1][point], point):
                win.destroy()
        ttk.Button(buttons, text='Keep current / Cancel', command=win.destroy).pack(side='left')
        ttk.Button(buttons, text='Apply selected to visible ' + point_label, command=apply).pack(side='right')

    def compare_glass_patterns(self):
        from PIL import Image, ImageOps, ImageTk

        if self.layout_pending or not self.job or self.gfile or self.grid_spec:
            self.say("Wait for the editable glass preview before comparing patterns.", "warn")
            return
        try:
            previews = simulate.glass_pattern_previews(self.job)
        except ValueError as exc:
            self.say(str(exc), "warn")
            return
        win = tk.Toplevel(self.root)
        win.title("Glass dot patterns")
        win.transient(self.root)
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)
        wrap_label(frame, "Black shows laser firing. Both views use the current size, tone and polarity. "
                          "Click either image to zoom both to the same area. Compare on scrap before choosing a recipe.",
                   width=690).pack(fill="x")
        tiles = ttk.Frame(frame)
        tiles.pack(pady=8)
        images = []
        for i, (label, _picture) in enumerate(previews):
            col = ttk.Frame(tiles, padding=3)
            col.grid(row=0, column=i, sticky="n")
            ttk.Label(col, text=label).pack()
            images.append(ttk.Label(col, cursor="crosshair"))
            images[-1].pack()

        def show(box=None):
            for widget, (_label, picture) in zip(images, previews):
                view = picture.crop(box) if box else picture
                tile = ImageOps.contain(view, (330, 230), Image.Resampling.NEAREST)
                widget.photo = ImageTk.PhotoImage(tile, master=win)
                widget.configure(image=widget.photo)
                if box:
                    widget.unbind("<Button-1>")
                else:
                    widget.bind("<Button-1>", lambda event, im=picture, tile_size=tile.size:
                                zoom(event.x, event.y, im.size, tile_size))

        def zoom(x, y, size, thumb):
            w, h = size
            cw, ch = min(w, 110), min(h, 82)
            left = max(0, min(w - cw, int(x * w / thumb[0]) - cw // 2))
            top = max(0, min(h - ch, int(y * h / thumb[1]) - ch // 2))
            show((left, top, left + cw, top + ch))

        show()
        ttk.Button(frame, text="Whole image", command=show).pack(side="left")
        ttk.Button(frame, text="Close", command=win.destroy).pack(side="right")
        win.bind("<Escape>", lambda _event: win.destroy())

    def auto_levels(self):
        if self.picture is None:
            self.say('Open an editable picture before using Auto levels.', 'warn')
            return
        from .planner import layout
        crop = layout(self.picture.size, self.build_params()[1], self.mat.pitch).crop
        self._set_visible_levels(crop, reset_manual=True)
        self.changed()

    def _set_visible_levels(self, crop=None, reset_manual=False):
        lo, hi = imaging.auto_level_points(self.picture, crop)
        self.v_black.set(lo)
        self.v_white.set(hi)
        self.v_auto.set(False)
        if reset_manual:
            self.v_bright.set(0); self.v_contrast.set(0); self.v_gamma.set(1)
        self.look_mode.configure(text=f'Auto applied: Black {lo}, White {hi}. All adjustments are visible; '
                                      'editing a slider switches to Manual.')

    def expose_legacy_auto(self, crop=None):
        if self.v_auto.get() and self.picture is not None:
            if crop is None:
                from .planner import layout
                crop = layout(self.picture.size, self.build_params()[1], self.mat.pitch).crop
            self._set_visible_levels(crop)

    def build_params(self):
        look = dict(brightness=round(self.v_bright.get()), contrast=round(self.v_contrast.get()),
                    gamma=round(self.v_gamma.get(), 2), sharpen=round(self.v_sharpen.get()),
                    autolevel=self.v_auto.get(), negative=self.v_neg.get(),
                    black_point=round(self.v_black.get()), white_point=round(self.v_white.get()))
        mat = self.mat
        if mat.style == "layers":
            c = sorted((int(v.get()) for v in self.v_cut), reverse=True)
            mat = mat.copy(tone_cuts=(c[0], min(c[1], c[0] - 1), min(c[2], c[1] - 2)))
        art_width = self.art_w if self.fit_var.get() in ("whole", "saved-whole", "art-exact", "marks") else None
        placement = Placement(copy.deepcopy(self.piece), art_w=art_width,
                              fit=self.fit_var.get(), dx=self.dx, dy=self.dy)
        return mat, placement, look

    @staticmethod
    def picture_recipe(job):
        return presets.describe_recipe(job.material, len(job.passes))

    @staticmethod
    def placement_summary(job, report, placement):
        """Describe the checked job in work coordinates shared by Check and Start."""
        g = job.geom
        fit = placement.fit
        def size(w, h):
            return f"{w:.2f} x {h:.2f} mm ({w / 25.4:.2f} x {h / 25.4:.2f} in)"
        def bounds(box):
            return f"X {box[0]:+.2f} to {box[2]:+.2f}, Y {box[1]:+.2f} to {box[3]:+.2f} mm"
        marks = job.burn_bbox()
        fit_names = {"whole": "Whole image", "saved-whole": "Original saved grid (choose Whole picture to refit proportionally)", "fill": "Fill (crop)", "exact": "Exact size",
                     "art-exact": "Exact image on stock", "marks": "Engraved width"}
        lines = [f"Fit: {fit_names.get(fit, fit)}. "
                 f"Zero: {jobs.origin_text(job.piece)}.",
                 f"Piece: {size(job.piece['w'], job.piece['h'])}."]
        if job.gray is not None:
            lines.insert(1, PlaceMixin.picture_recipe(job))
            usable = g.usable_rect
            width, height = usable[2] - usable[0], usable[3] - usable[1]
            requested = placement.art_w if fit in ("whole", "saved-whole", "art-exact", "marks") else job.piece["w"] if fit == "exact" else None
            width_name = "Requested engraved width" if fit == "marks" else "Requested artwork width"
            lines.append(f"{width_name}: {requested:.2f} mm." if requested is not None
                         else f"{width_name}: automatic fit.")
            lines.append(f"Usable face: {size(width, height)}.")
            if note := PlaceMixin.width_limit_note(g, fit, requested):
                lines.append(note)
            if job.sizing_note:
                lines.append(job.sizing_note)
        footprint = (f"Actual engraving grid: {size(g.art_w, g.art_h)} ({g.cols} x {g.rows} cells)"
                     if job.gray is not None else f"Image: {size(g.art_w, g.art_h)}")
        lines.extend([f"{footprint}. Lower left: X {g.x0:+.2f}, Y {g.y0:+.2f} mm.",
                 (f"Marks: {size(marks[2] - marks[0], marks[3] - marks[1])}. " + bounds(marks)
                  if marks else "Marks: none.")])
        if job.gray is not None:
            lines.append(f"Row spacing: {job.material.pitch:g} mm setting, {g.y_pitch:.3f} mm actual.")
        if report and (travel := report.get("travel")):
            envelope = (min(0, travel[0]), min(0, travel[1]), max(0, travel[2]), max(0, travel[3]))
            lines.append(f"Total travel (includes beam-off run-up and return): {bounds(envelope)}.")
            p = g.piece_rect
            if any(distance < -0.005 for distance in (envelope[0] - p[0], envelope[1] - p[1],
                                                       p[2] - envelope[2], p[3] - envelope[3])):
                lines.append("Travel extends beyond the piece box. Check Total travel (off) for clearance.")
        return "\n".join(lines)

    def placement_review_text(self, job, report):
        current = self.placement_summary(job, report, self.build_params()[1])
        if self._opened_placement and self._opened_placement != current and job.gray is not None:
            saved = self._opened_placement.splitlines()
            saved_grid = next(line for line in saved if line.startswith("Actual engraving grid:"))
            current = f"Saved setup: {saved[0]} {saved_grid}\nCurrent setup:\n{current}"
        if job.gray is not None and not self.grid_spec:
            direction = "Left to right" if job.material.scan_direction == "forward" else "Alternating"
            current += f"\n{presets.STYLES[job.material.style]['name']} · {direction}."
            if self._repeat_reference:
                folder, original, original_look = self._repeat_reference
                changes = presets.settings_changes(presets.print_settings(original), presets.print_settings(job.material))
                photo = self.picture_changes(original_look, self.build_params()[2])
                current += f"\nReference job: {folder.name}."
                current += ("\nPrint changes: " + ", ".join(changes) + "." if changes else " Print settings match.")
                if photo:
                    current += "\nPicture changes: " + ", ".join(photo) + "."
        return current

    @staticmethod
    def picture_changes(before, after):
        def display(look):
            return {key.replace("_", " ").capitalize(): ("On" if value else "Off") if isinstance(value, bool)
                    else f"{value:g}" for key, value in look.items()}
        return presets.settings_changes(display(before), display(after))

    def choose_pair(self):
        filename = filedialog.askopenfilename(parent=self.root, title="Compare with a saved pass",
                                              initialdir=self._picker_folder("job"),
                                              filetypes=[("Studio saved job", "job.json")])
        if not filename:
            return
        path = Path(filename).resolve()
        if path.name.lower() != "job.json":
            messagebox.showinfo("Choose a saved job", "Select the other pass's job.json file.", parent=self.root)
            return
        current = self.saved.get(self.gen) or (self.source_provenance or {}).get("folder")
        if current and path.parent.resolve() == Path(current).resolve():
            messagebox.showinfo("Choose the other pass", "Select the saved job for the other pass.", parent=self.root)
            return
        try:
            fingerprint = jobs.sha256(path)
            _, _, partner, _, _, _, _ = picture_jobs.read(path)
            if fingerprint != jobs.sha256(path):
                raise ValueError("The selected job changed while it was being read.")
        except Exception as exc:
            messagebox.showerror("Cannot compare pass", str(exc), parent=self.root)
            return
        self._pair = (path, fingerprint, partner)
        self._pair_review_required = False
        self.saved.pop(self.gen, None)
        self.update_check_panel()

    def clear_pair(self):
        self._pair = None
        self._pair_review_required = False
        self.saved.pop(self.gen, None)
        self.update_check_panel()

    def pair_blocker(self, recheck=False):
        if self._pair_review_required:
            return "The paired artwork needs a fresh comparison. Choose Compare another pass in Check."
        if self._pair is None:
            return ""
        if not self.verified_layout() or self.job.gray is None or self.grid_spec:
            return "Check the current picture job before comparing its paired pass."
        path, fingerprint, partner = self._pair
        if recheck:
            try:
                if fingerprint != jobs.sha256(path):
                    raise ValueError("Choose the paired job again after reviewing its changes.")
                _, _, partner, _, _, _, _ = picture_jobs.read(path)
                if fingerprint != jobs.sha256(path):
                    raise ValueError("The paired job changed while it was being read.")
            except Exception as exc:
                return f"Cannot verify the saved paired pass: {exc}"
        return "\n".join(picture_jobs.registration_conflicts(self.job, partner))

    def update_check_panel(self):
        self.after_build_place()
        job, rep = self.job, self.report
        ok = bool(rep and rep["ok"] and self.compiled_gen == self.gen)
        self.btn_pair.state(["!disabled"] if ok and self.picture is not None and not self.grid_spec and not self.gfile
                            else ["disabled"])
        self.btn_clear_pair.state(["!disabled"] if self._pair or self._pair_review_required else ["disabled"])
        for b in (self.btn_save, self.btn_export):
            b.state(["!disabled"] if ok else ["disabled"])
        self.btn_package.state(["!disabled"] if ok and self.picture is not None and not self.grid_spec and not self.gfile
                               else ["disabled"])
        if job is None:
            self.check_text.configure(text="Open a picture first.")
            return
        if rep is None or self.compiled_gen != self.gen:
            self.check_text.configure(text="Not checked yet (it runs automatically on this page).")
            return
        lines = [("OK - " if rep["ok"] else "PROBLEM - ") + verify.summary_text(rep)]
        lines.append(self.placement_review_text(job, rep))
        pair_problem = self.pair_blocker()
        if self._pair_review_required:
            lines.insert(0, "Start is blocked. " + pair_problem)
        elif self._pair:
            pairing = [f"Paired pass: {self._pair[2].name}."]
            pairing.append("Pair mismatch — Start is blocked.\n" + pair_problem if pair_problem else
                           "Pair geometry matches. Keep the same physical zero and lid position for both passes.")
            lines = pairing + lines
        for p, r in zip(job.passes, rep["passes"]):
            lines.append(f"  {p.title}: {r['cells']:,} dots, about {fmt_dur(p.est_s)}  ({p.explain})")
        lines.append(f"Total: about {fmt_dur(job.est_s)} of laser time"
                     + (", plus photo pauses." if len(job.passes) > 1 else "."))
        hint = self.negative_hint()
        if hint:
            lines.append(hint)
        self.check_text.configure(text="\n".join(lines),
                                  foreground=COLORS["ok"] if rep["ok"] and not pair_problem else COLORS["bad"])
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
                     picture_file=str(self.picture_path) if self.picture_path else None, grid=self.grid_spec,
                     source_provenance=self.source_provenance or dict(
                         original_picture=str(self.picture_path) if self.picture_path else None,
                         original_sha256=jobs.sha256(self.picture_path) if self.picture_path else None,
                         rotate=self.rotate, mirror=self.mirror),
                     saved_source_transform=dict(file=str(self.picture_path) if self.picture_path else None,
                         rotate=self.rotate, mirror=self.mirror),
                     keep_proportions=self.proportions_var.get(),
                     pair_check_required=bool(self._pair or self._pair_review_required))
        if self._repeat_reference and job.gray is not None and not self.grid_spec:
            extra["based_on_job"] = str(self._repeat_reference[0])
        previews = {"1 LOOKS LIKE - finished piece": simulate.mark_spots(simulate.appearance(job), job),
                    "2 LASER INPUT - black means the laser fires": simulate.laser_input(job),
                    "3 TOOLPATH - powered marks on dark": simulate.toolpath_view(job),
                    "4 burn map - colour per pass": simulate.mark_spots(simulate.burn_map(job), job)}
        if getattr(job, "ladder", None):
            from . import ladder
            previews["5 LADDER MAP - print this"] = ladder.ladder_map(job)
        folder = jobs.save_job(job, self.report, picture=None if self.grid_spec else self.picture, previews=previews,
                               extra=extra)
        self.saved[self.gen] = folder
        self.saved_lbl.configure(text=f"Saved in {folder}")
        if not quiet:
            self.say(f"Saved the job in {folder}", "ok")
        return folder

    def export_studio_package(self):
        if self._picture_job_in_use() or self.gfile or self.grid_spec or self.picture is None:
            self.say("Open a checked editable image job and finish any active operation first.", "warn")
            return
        destination = filedialog.asksaveasfilename(
            title="Save editable package (includes source artwork)", defaultextension=".lpsjob",
            filetypes=[("Editable Studio package", "*.lpsjob")],
            initialfile=jobs.safe_name(self.job.name) + ".lpsjob")
        if destination:
            try:
                folder = self.save_current_job(quiet=True)
                if folder is not None:
                    job_package.export_job(folder, Path(destination))
                    self.say(f"Editable Studio package saved: {destination}", "ok")
            except (OSError, ValueError) as exc:
                messagebox.showerror("Cannot save editable package", str(exc), parent=self.root)

    def export_gcode(self):
        folder = self.save_current_job(quiet=True)
        if not folder:
            return
        dest = filedialog.asksaveasfilename(title="Export G-code", defaultextension=".nc",
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
        messagebox.showinfo("G-code exported", f"Saved {dest.name}" +
                            (f"\n\nIndividual passes are in:\n{layers}" if len(self.job.passes) > 1 else "") +
                            "\n\nBefore using external G-code, confirm the intended origin, "
                            "machine settings and framing on the target controller.", parent=self.root)
