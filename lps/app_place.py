"""Steps 3 (size & placement) and 4 (look & check, save, LaserGRBL)."""
from __future__ import annotations

import copy
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import imaging, jobs, presets, simulate, verify
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
        ttk.Checkbutton(c, text="Use exact image size",
                        variable=self.exact_var, command=self._exact_toggled).pack(anchor="w")
        wrap_label(c, "Normally Width and Height measure the outside of your physical piece. Set the picture's "
                      "width under Picture size below. Exact image size instead makes this box the image itself: "
                      "it uses no margins and can stretch the picture.", style="Small.TLabel").pack(anchor="w")
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
        self.car_options = ttk.Frame(c)
        b = ttk.Button(self.car_options, text="Customize Hot Wheels...", command=self.toy_car)
        b.pack(anchor="w")
        ToolTip(b, "Pick a body type and measure your car: the windshield and rear window become no-burn zones and "
                   "the start point goes on a spot you can find, like the windshield's front edge.")
        row = ttk.Frame(c)
        row.pack(fill="x", pady=(6, 0))
        self.pw_var, self.ph_var, self.corner_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in (("Width", self.pw_var), ("Height", self.ph_var)):
            axis="w" if label=="Width" else "h"
            ttk.Label(row, text=label).pack(side="left")
            sp = ttk.Spinbox(row, from_=1, to=600, increment=0.5, width=7, textvariable=var,
                             command=lambda a=axis:self._piece_edited(a))
            sp.pack(side="left", padx=(4, 10))
            sp.bind("<FocusOut>", lambda e,a=axis:self._piece_edited(a))
            sp.bind("<Return>", lambda e,a=axis:self._piece_edited(a))
        ttk.Label(row, text="mm").pack(side="left")
        self.proportions_var=tk.BooleanVar(value=False)
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
        wrap_label(o, "Corners are easiest to find by eye. Lids are usually centred. Or pick a spot you can find on "
                      "the real piece, like the corner of a stripe or the middle of the windshield's edge: the red "
                      "crosshair shows it, and that's where you'll put the laser dot.", style="Small.TLabel").pack(
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
        for label, value in (("Whole picture", "whole"), ("Fill the area (crops the edges)", "fill")):
            rb = ttk.Radiobutton(a, text=label, value=value, variable=self.fit_var, command=self._fit_changed)
            rb.pack(anchor="w")
            self.exact_disabled.append(rb)
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
        if self.exact_var.get():
            w, h = size or (self.piece["w"], self.piece["h"])
            self.piece_key = "custom"
            # Keep explicitly placed window masks; default the new box to its lower-left.
            self.piece = dict(copy.deepcopy(self.piece), name="Exact size", shape="rect", w=w, h=h,
                              origin="lower-left", margins=(0.0, 0.0, 0.0, 0.0), corner=0.0)
            self.piece_user_set = True
            self.fit_var.set("exact")
            self.dx = self.dy = 0.0
        else:
            self.fit_var.set("whole")
        self.art_w = None
        self.sync_place_fields()
        self.changed()

    def saved_size(self):
        """The size stored in the open picture's file, turned with the picture."""
        s = imaging.saved_size_mm(self.picture_path) if self.picture_path else None
        return (s[1], s[0]) if s and self.rotate % 2 else s

    def show_saved_size(self):
        s = self.saved_size()
        self.saved_btn.configure(text=f"Use the size saved in the file: {s[0]:g} x {s[1]:g} mm" if s else
                                 "Use the size saved in the file")
        self.saved_btn.state(["!disabled"] if s else ["disabled"])
        if s:
            self.say(f"This file says it's {s[0]:g} x {s[1]:g} mm: step 3 can burn it at exactly that size.", "ok")

    def use_saved_size(self):
        self.exact_var.set(True)
        self._exact_toggled(self.saved_size())

    def set_piece(self, key, user=True):
        self.fit_var.set("whole" if self.fit_var.get() == "exact" else self.fit_var.get())
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
        self.fit_var.set("whole" if self.fit_var.get() == "exact" else self.fit_var.get())
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
            self.piece_var.set(f"Exact image {pc['w']:g} x {pc['h']:g} mm" if self.fit_var.get() == 'exact'
                               else presets.piece_choice_label(pc))
            self.pw_var.set(f"{pc['w']:g}")
            self.ph_var.set(f"{pc['h']:g}")
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
            self.ko_list.delete(0, "end")
            for k in pc.get("keepouts", []):
                if k.get("kind") == "circle":
                    self.ko_list.insert("end", f"Hole: centre {k['x']:g}, {k['y']:g} mm, radius {k['r']:g} mm")
                else:
                    self.ko_list.insert("end", f"Rectangle: from {k['x']:g}, {k['y']:g} mm, {k['w']:g} x {k['h']:g} mm")
            if self.art_w:
                self.artw_var.set(f"{self.art_w:g}")
            self.piece_in_lbl.configure(text=f"= {pc['w'] / 25.4:.2f} x {pc['h'] / 25.4:.2f} inches"
                                       f"; corner radius {pc.get('corner', 0):g} mm")
            self.offset_lbl.configure(text=("Centred." if not (self.dx or self.dy) else
                                            f"Moved {abs(self.dx):g} mm {'right' if self.dx >= 0 else 'left'}, "
                                            f"{abs(self.dy):g} mm {'up' if self.dy >= 0 else 'down'} from centre."))
            self.exact_var.set(self.fit_var.get() == "exact")
            self.proportions_btn.state(["!disabled"] if self.exact_var.get() else ["disabled"])
            self.artw_spin.state(["!disabled"] if self.fit_var.get() == "whole" else ["disabled"])
            for widget in self.exact_disabled:
                widget.state(["disabled"] if self.exact_var.get() else ["!disabled"])
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
        try:
            pc = self.piece
            ratio=pc['w']/pc['h']
            pc["w"], pc["h"] = max(1.0, float(self.pw_var.get())), max(1.0, float(self.ph_var.get()))
            if self.fit_var.get()=='exact' and self.proportions_var.get():
                if axis=='w': pc['h']=pc['w']/ratio
                elif axis=='h': pc['w']=pc['h']*ratio
            pc["shape"] = self.shape_var.get()
            if pc["shape"] == "circle":
                pc["h"] = pc["w"]
            pc["corner"] = max(0.0, float(self.corner_var.get() or 0))
            pc["origin"] = self.origin_var.get()
            if pc["origin"] == "spot":
                pc["spot"] = [round(min(pc["w"], max(0.0, float(v.get() or 0))), 2) for v in self.spot_vars]
            pc["margins"] = tuple(max(0.0, float(v.get() or 0)) for v in self.margin_vars)
            if self.fit_var.get() == "exact":
                pc.update(shape="rect", corner=0.0, margins=(0.0, 0.0, 0.0, 0.0))
        except ValueError:
            return
        self.piece_user_set = True
        self.sync_place_fields()
        self.changed()

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
        if self.layout_pending:
            self.clearance_lbl.configure(text="Updating layout — edge clearances are not current yet.")
            return
        if self.job is None:
            self.clearance_lbl.configure(text="Open a picture to see edge clearances.")
            return
        g = self.job.geom
        old, self._loading = self._loading, True
        try:
            self.artw_var.set(f"{g.art_w:g}")
        finally:
            self._loading = old
        self.arth_lbl.configure(text=f"Art {g.art_w:.1f} x {g.art_h:.1f} mm ({g.art_w / 25.4:.2f} x "
                                     f"{g.art_h / 25.4:.2f} in). Laser-off run-ups add a few mm left "
                                     "and right (grey dashes in the preview).\n"
                                     f"Picture lower-left: X {g.x0:.3f}, Y {g.y0:.3f} mm from start 0,0. "
                                     "Blank space inside the file stays inside this box.")
        px0, py0, px1, py1 = g.piece_rect
        gaps = (g.x0 - px0, g.y0 - py0, px1 - g.x1, py1 - g.yt)
        text = "Picture-box gaps to outside edges (mm): " + ", ".join(
            f"{side} {value:.2f}" for side, value in zip(("Left", "Bottom", "Right", "Top"), gaps))
        ux0, uy0, ux1, uy1 = g.usable_rect
        if min(g.x0 - ux0, g.y0 - uy0, ux1 - g.x1, uy1 - g.yt) < -0.001:
            text += "\nPicture enters a margin or extends outside the piece; affected marks are masked."
        text += ("\nNegative gap = extends outside the piece. These are box clearances, not the nearest marks. "
                 "Round edges and no-burn zones can clip marks inside the box. Image perimeter checks the picture; "
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
        self.look_frames = (c, t)
        self._locked_picture_widgets = {}
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

    def sync_picture_edit_mode(self):
        if not hasattr(self, 'look_frames'):
            return
        locked = bool(self.gfile or self.picture is None)
        if self.gfile:
            message = ('G-code check only: movement/power are already encoded. Picture, material and size controls '
                       'cannot edit these commands. Open saved Studio picture job or the original picture in step 1.')
        elif self.picture is None:
            message = ('No editable picture loaded. Open saved Studio picture job or the original picture in step 1. '
                       'Generated grids use their own grid parameters, not these picture sliders.')
        else:
            message = 'Editable source picture: adjustments rebuild the preview and must pass verification before printing.'
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
        self.v_bright.set(m.brightness)
        self.v_contrast.set(m.contrast)
        self.v_gamma.set(m.gamma)
        self.v_sharpen.set(m.sharpen)
        self.v_auto.set(m.autolevel)
        self.v_black.set(m.black_point)
        self.v_white.set(m.white_point)
        prepared=bool(self.picture_path and self.picture_path.stem.upper().endswith('IMPORT'))
        self.v_neg.set(False if prepared else m.negative)
        for v, c in zip(self.v_cut, m.tone_cuts):
            v.set(c)
        self.expose_legacy_auto()

    def _manual_look_changed(self, *_):
        if self._loading:
            return
        self.look_mode.configure(text='Manual: preview uses the visible controls. Release a slider to update.')
        self.changed()

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
        placement = Placement(copy.deepcopy(self.piece), art_w=self.art_w if self.fit_var.get() == "whole" else None,
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
                                  foreground=COLORS["ok"] if rep["ok"] else COLORS["bad"])
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
                     keep_proportions=self.proportions_var.get())
        previews = {"1 LOOKS LIKE - finished piece": simulate.mark_spots(simulate.appearance(job), job),
                    "2 LASER INPUT - black means the laser fires": simulate.laser_input(job),
                    "3 IN LASERGRBL - how its preview draws the nc": simulate.lasergrbl_view(job),
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
