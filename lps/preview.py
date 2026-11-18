"""Right-hand preview: the piece, the art (as it should look / what each pass burns / the source picture), no-burn
zones, laser-off run-up area, the start point, perimeter dots and the live head position."""
from __future__ import annotations

import math
import copy
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import Image, ImageTk, ImageDraw, ImageColor

from . import gcodeinfo, jobs, planner, simulate, keepouts, verify
from .presets import LOOKS
from .ui_common import COLORS, paint, wrap_label


def hexrgb(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


GRID_STEPS = (0.5, 1, 2, 5, 10, 20, 50, 100)     # mm


def grid_step(px_per_mm: float, min_px: float = 36.0) -> float:
    """The finest round spacing whose squares are still big enough to see at this zoom."""
    return next((g for g in GRID_STEPS if g * px_per_mm >= min_px), GRID_STEPS[-1])


class PreviewPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(6, 8, 10, 6))
        self.app = app
        self.view = tk.StringVar(value="look")
        self.show = tk.StringVar(value="")
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="Preview:", style="H2.TLabel").pack(side="left")
        for text, val in (("Looks like", "look"), ("What burns", "map"), ("In LaserGRBL", "lgrbl"),
                          ("Picture", "pic")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.view, command=self.refresh).pack(side="left",
                                                                                                      padx=4)
        self.show_box = ttk.Combobox(bar, textvariable=self.show, state="readonly", width=18)
        self.show_box.pack(side="right")
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.show_lbl = ttk.Label(bar, text="Show:")
        self.show_lbl.pack(side="right", padx=4)
        self.grid_on = tk.BooleanVar(value=bool(app.settings.get("grid", True)))
        self.size_guide=tk.BooleanVar(value=False)
        ttk.Checkbutton(bar,text='Size box',variable=self.size_guide,command=self.refresh).pack(side='right',padx=4)
        self.show_centers = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Centers", variable=self.show_centers, command=self.refresh).pack(side="right")
        self.grid_mm = None       # the spacing drawn right now
        ttk.Checkbutton(bar, text="Grid", variable=self.grid_on, command=self._grid_toggled).pack(side="right",
                                                                                                  padx=8)
        self.canvas = paint(tk.Canvas(self, highlightthickness=0), background="canvas")
        self.canvas.pack(fill="both", expand=True, pady=(6, 4))
        self.info = wrap_label(self, "", style="Muted.TLabel", width=900)
        self.info.pack(fill="x")
        self.warn = paint(wrap_label(self, "", width=900), foreground="warn")
        self.key = tk.Canvas(self, height=1, highlightthickness=0,
                             background=ttk.Style(self).lookup("TFrame", "background") or COLORS["bg"])
        self.key.pack(fill="x", pady=(2, 0))
        self.key.bind("<Configure>", lambda e: self._draw_key())
        self._key_items = []
        self.legend = wrap_label(self, "", style="Small.TLabel", width=900)
        self.legend.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self._schedule())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<B1-Motion>", self._zone_motion)
        self.canvas.bind("<ButtonRelease-1>", self._zone_release)
        self.canvas.bind("<Double-Button-1>", self._zone_double_click)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("cursor"))
        self._after = None
        self._cache = {}
        self._photo = None
        self.T = None
        self._zone_drag = None
        self._check_cache = None
        self._check_photo = None

    # ---------------------------------------------------------------- options
    def set_job(self, job):
        self._cache.clear()
        self._contour_cache = None
        if job is None:
            self.show_box.configure(values=[])
            self.show.set("")
        else:
            self._update_choices()
        self.refresh()

    def _update_choices(self):
        job = self.app.job
        if job is None:
            return
        if self.view.get() == "look":
            vals = ["Finished piece"] + [f"After {p.title}" for p in job.passes]
        elif self.view.get() in ("map", "lgrbl"):
            vals = ["All passes"] + [f"Only {p.title}" for p in job.passes]
        else:
            vals = ["Adjusted picture"]
        self.show_box.configure(values=vals)
        if self.show.get() not in vals:
            self.show.set(vals[0])

    def selected_passes(self):
        job = self.app.job
        s = self.show.get()
        if job is None or s in ("", "Finished piece", "All passes", "Adjusted picture"):
            return None
        for i, p in enumerate(job.passes):
            if s == f"After {p.title}":
                return {q.key for q in job.passes[:i + 1]}
            if s == f"Only {p.title}":
                return {p.key}
        return None

    def refresh(self):
        self._update_choices()
        self._schedule()

    def _schedule(self):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(40, self.redraw)

    # ---------------------------------------------------------------- drawing
    def _art_image(self):
        job = self.app.job
        key = (id(job), self.view.get(), self.show.get())
        if key not in self._cache:
            sel = self.selected_passes()
            if self.view.get() == "look":
                im = simulate.appearance(job, sel)
            elif self.view.get() == "map":
                im = simulate.burn_map(job, sel)
            elif self.view.get() == "lgrbl":
                im = simulate.lasergrbl_view(job, sel)
            else:
                im = simulate.source_view(job)
            self._cache = {key: im}
        return self._cache[key]

    def bounds(self):
        app = self.app
        xs, ys = [0.0], [0.0]
        if app.gfile:
            pr=gcodeinfo.frame_bbox(app.gfile)
            if pr:
                xs += [pr[0],pr[2]]
                ys += [pr[1],pr[3]]
        elif app.job is not None:
            pr = app.job.geom.piece_rect
            xs += [pr[0], pr[2]]
            ys += [pr[1], pr[3]]
            b = app.picture_box()
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
            tr = app.report.get("travel") if app.report else None
            if tr:
                xs += [tr[0], tr[2]]
                ys += [tr[1], tr[3]]
        else:
            pr = planner.piece_rect(app.piece)
            xs += [pr[0], pr[2]]
            ys += [pr[1], pr[3]]
        if app.gfile and app.gfile.get("travel_bbox"):
            t = app.gfile["travel_bbox"]
            xs += [t[0], t[2]]
            ys += [t[1], t[3]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = max(4.0, 0.06 * max(x1 - x0, y1 - y0))
        return x0 - pad, y0 - pad, x1 + pad, y1 + pad

    def redraw(self):
        self._after = None
        c = self.canvas
        c.delete("all")
        W, H = max(50, c.winfo_width()), max(50, c.winfo_height())
        vx0, vy0, vx1, vy1 = self.bounds()
        s = min((W - 20) / (vx1 - vx0), (H - 20) / (vy1 - vy0))
        ox = (W - (vx1 - vx0) * s) / 2
        oy = (H - (vy1 - vy0) * s) / 2
        if self._zone_drag is not None:
            ox, oy, s, vx0, vy1 = self._zone_drag["transform"]
        self.T = (ox, oy, s, vx0, vy1)
        tx = lambda x: ox + (x - vx0) * s
        ty = lambda y: oy + (vy1 - y) * s
        app = self.app
        job = None if app.gfile else app.job
        look = LOOKS.get((app.job.material if app.job is not None else app.mat).look, LOOKS["pine"])
        piece = job.piece if job is not None else app.piece
        px0, py0, px1, py1 = planner.piece_rect(piece)
        if app.gfile:
            px0,py0,px1,py1=gcodeinfo.frame_bbox(app.gfile)
        fill = {"look": hexrgb(look[0]), "lgrbl": hexrgb(simulate.LASERGRBL_BG)}.get(self.view.get(), "#ffffff")
        if piece.get("shape") == "circle":
            c.create_oval(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline=COLORS["piece_edge"], width=2)
        else:
            c.create_rectangle(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline=COLORS["piece_edge"], width=2)
        if job is not None:
            g = job.geom
            ux0, uy0, ux1, uy1 = g.usable_rect
            c.create_rectangle(tx(ux0), ty(uy1), tx(ux1), ty(uy0), outline=COLORS["usable"], dash=(3, 3))
            wpx, hpx = max(1, int(g.art_w * s)), max(1, int(g.art_h * s))
            im = self._art_image()
            if self.view.get() == "look":
                mask = None
                if job.allowed is not None:
                    a = (job.allowed * 255).astype("uint8")
                    mask = Image.fromarray(a, "L").resize((wpx, hpx), Image.Resampling.NEAREST)
                im = im.resize((wpx, hpx), Image.Resampling.LANCZOS if wpx < im.width else Image.Resampling.NEAREST)
                base = Image.new("RGB", (wpx, hpx), tuple(look[0]))
                im = Image.composite(im, base, mask) if mask is not None else im
            else:
                im = im.resize((wpx, hpx), Image.Resampling.LANCZOS if wpx < im.width else Image.Resampling.NEAREST)
            self._photo = ImageTk.PhotoImage(im)
            c.create_image(tx(g.x0), ty(g.yt), image=self._photo, anchor="nw")
            if self.size_guide.get():
                c.create_rectangle(tx(g.x0), ty(g.yt), tx(g.x1), ty(g.y0), outline=COLORS["usable"], width=1,
                                   dash=(3,4),tags="size-box")
            c.create_text(tx(g.x1), ty(g.y0) + 12, anchor="ne", fill=COLORS["muted"], font=("Segoe UI", 9),
                          text=f"Image size {g.art_w:g} x {g.art_h:g} mm (size guide only)")
            sel = self.selected_passes()
            for p in job.passes:                       # crawl lines: label the average speed and step once per line
                if p.kind != "crawl" or (sel is not None and p.key not in sel):
                    continue
                seen = []
                for ln in p.lines or []:
                    k = (ln["x0"], ln["x1"], ln["v_avg"], ln["step"])
                    if any(k == q and abs(ln["y"] - qy) < 0.5 for q, qy in seen):
                        continue
                    seen.append((k, ln["y"]))
                    c.create_text(tx(ln["x1"]) + 4, ty(ln["y"]), anchor="w", fill=COLORS["bad"], font=("Segoe UI", 7),
                                  text=f"crawl {ln['v_avg']:g} mm/min avg, {ln['step']:g} mm steps")
            for p in job.passes:                       # burn-in-place spots: one dot each, so ring and label them
                if p.kind != "dwell" or (sel is not None and p.key not in sel):
                    continue
                r = max(5.0, 0.6 * s)
                for sp in p.spots or []:
                    x, y = tx(sp["x"]), ty(sp["y"])
                    c.create_oval(x - r, y - r, x + r, y + r, outline=COLORS["bad"], width=2)
                    c.create_text(x, y + r + 1, anchor="n", justify="center", fill=COLORS["bad"],
                                  font=("Segoe UI", 7), text=simulate.spot_label(sp))
            zones = app.piece.get("keepouts", []) if app.zone_editing() else piece.get("keepouts", [])
            for index, k in enumerate(zones):
                bx0,by0,bx1,by1 = keepouts.zone_bounds(k)
                if bx1 <= 0 or by1 <= 0 or bx0 >= piece['w'] or by0 >= piece['h']:
                    continue  # retained masks from a larger piece must not obscure a smaller picture box
                kx, ky = px0 + float(k["x"]), py0 + float(k["y"])
                if k.get("kind") == "circle":
                    r = float(k["r"])
                    c.create_oval(tx(kx - r), ty(ky + r), tx(kx + r), ty(ky - r), outline=COLORS["bad"], width=2,
                                  fill=COLORS["keepout"], stipple="gray50")
                else:
                    c.create_rectangle(tx(kx), ty(ky + float(k["h"])), tx(kx + float(k["w"])), ty(ky),
                                       outline=COLORS["bad"], width=2, fill=COLORS["keepout"], stipple="gray50")
                if app.zone_editing():
                    c.create_text(tx(kx)+5, ty(ky)-5, text=f"Zone {index+1}", anchor="sw", fill=COLORS["bad"])
                    if app.selected_keepout() == index:
                        for hx, hy, handle in self._zone_handles(k):
                            x, y = tx(px0+hx), ty(py0+hy)
                            c.create_rectangle(x-5, y-5, x+5, y+5, fill=COLORS["panel"],
                                               outline=COLORS["bad"], width=2, tags="zone-handle")
        self.grid_mm = grid_step(s) if self.grid_on.get() else None
        if self.grid_mm:
            self._draw_grid(tx, ty, px0, py0, px1, py1)
        if app.gfile and app.gfile.get("burn_bbox"):
            b = gcodeinfo.frame_bbox(app.gfile)
            c.create_rectangle(tx(b[0]), ty(b[3]), tx(b[2]), ty(b[1]), outline=COLORS["usable"],dash=(3,4))
            c.create_text(tx(b[0]) + 4, ty(b[3]) - 10, anchor="w", text=app.gfile["name"], fill=COLORS["accent"])
        if not app.zone_editing() and (app.gfile or not app.layout_pending):
            self.draw_check(tx, ty, W, H)
        self.draw_centers(tx, ty, piece, job)
        self.draw_head()
        self._update_info()

    def draw_check(self, tx, ty, width, height):
        app, c = self.app, self.canvas
        mode = app.check_mode
        if not mode:
            return
        if mode in ("burn", "dry"):
            if not app.verified_layout():
                return
            key = (mode, app.gen, self.T, width, height, COLORS["art"], COLORS["travel"])
            if key != self._check_cache:
                marks = Image.new("RGBA", (width, height))
                travel = Image.new("RGBA", marks.size)
                mark_draw, travel_draw = ImageDraw.Draw(marks), ImageDraw.Draw(travel)
                travel_color = (*ImageColor.getrgb(COLORS["travel"]), 130)
                prev = (tx(0), ty(0))
                for x, y, _, marking in verify.trace_moves(app.job):
                    point = (tx(x), ty(y))
                    if marking:
                        mark_draw.line((prev, point), fill=COLORS["art"])
                    else:
                        travel_draw.line((prev, point), fill=travel_color)
                    prev = point
                for p in app.job.passes:              # burn-in-place spots: a ring at each, standing still
                    for sp in (p.spots or []) if p.kind == "dwell" else []:
                        px, py = tx(sp["x"]), ty(sp["y"])
                        mark_draw.ellipse((px - 4, py - 4, px + 4, py + 4), outline=COLORS["art"], width=2)
                self._check_photo = ImageTk.PhotoImage(Image.alpha_composite(travel, marks))
                self._check_cache = key
            c.create_image(0, 0, image=self._check_photo, anchor="nw")
            return
        paths = app.check_paths(mode)
        if mode == "sticker":
            key = (mode, app.check_key(), self.T, width, height, COLORS["art"])
            if key != self._check_cache:
                overlay = Image.new("RGBA", (width, height))
                draw = ImageDraw.Draw(overlay)
                for path in paths:
                    draw.line([(tx(x), ty(y)) for x, y in path], fill=COLORS["art"], width=2)
                self._check_photo = ImageTk.PhotoImage(overlay)
                self._check_cache = key
            c.create_image(0, 0, image=self._check_photo, anchor="nw")
            return
        for path in paths:
            coords = [v for x, y in path for v in (tx(x), ty(y))]
            c.create_line(*coords, fill=COLORS["travel"] if mode == "travel" else COLORS["art"], width=2,
                          dash=(4, 4) if mode == "travel" else ())

    def draw_centers(self, tx, ty, piece, job):
        labels = {(0.0, 0.0): ["Job zero (0,0)"]}
        if not self.app.gfile:
            bounds = [("Piece center", planner.piece_rect(piece))]
            if job is not None:
                bounds.append(("Image center", self.app.picture_box()))
            for label, (x0, y0, x1, y1) in bounds:
                point = (round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3))
                if self.show_centers.get() or point == (0.0, 0.0):
                    labels.setdefault(point, []).append(label)
        for (px, py), names in labels.items():
            c = self.canvas
            x, y = tx(px), ty(py)
            zero = (px, py) == (0.0, 0.0)
            color = COLORS["accent"] if zero else COLORS["muted"]
            if zero:
                c.create_line(x - 12, y, x + 12, y, fill=color, width=2)
                c.create_line(x, y - 12, x, y + 12, fill=color, width=2)
            else:
                c.create_polygon(x, y - 5, x + 5, y, x, y + 5, x - 5, y, outline=color, fill="")
            label = "Job zero & both centers" if len(names) == 3 else " / ".join(names)
            c.create_text(x + 7, y + 12, anchor="nw", text=label, fill=color, font=("Segoe UI", 9, "bold"))
    def _draw_grid(self, tx, ty, px0, py0, px1, py1):
        """Squares over the piece, lined up with the start point; the numbers are mm from it, as in step 5's X/Y."""
        c, step, col, back = self.canvas, self.grid_mm, COLORS["grid"], COLORS["grid_back"]
        font = ("Segoe UI", 8)

        def line(x0, y0, x1, y1, zero):
            if back:
                c.create_line(x0, y0, x1, y1, fill=back, tags="grid")
            c.create_line(x0, y0, x1, y1, fill=col, dash=(6, 3) if zero else (3, 3), tags="grid")

        for k in range(math.ceil(px0 / step - 1e-9), math.floor(px1 / step + 1e-9) + 1):
            x = k * step
            line(tx(x), ty(py0), tx(x), ty(py1), k == 0)
            c.create_text(tx(x), ty(py1) - 7, text=f"{x:g}", fill=COLORS["muted"], font=font, tags="grid")
        for k in range(math.ceil(py0 / step - 1e-9), math.floor(py1 / step + 1e-9) + 1):
            y = k * step
            line(tx(px0), ty(y), tx(px1), ty(y), k == 0)
            c.create_text(tx(px0) - 4, ty(y), text=f"{y:g}", anchor="e", fill=COLORS["muted"], font=font, tags="grid")

    def _grid_toggled(self):
        self.app.settings["grid"] = self.grid_on.get()
        jobs.save_settings(self.app.settings)
        self.redraw()

    def _to_mm(self, e):
        """Canvas pixel -> (work X, work Y, mm from the piece's left edge, mm up from its bottom edge)."""
        ox, oy, s, vx0, vy1 = self.T
        x, y = vx0 + (e.x - ox) / s, vy1 - (e.y - oy) / s
        job = self.app.job
        px0, py0, _, _ = planner.piece_rect(job.piece if job is not None else self.app.piece)
        return x, y, x - px0, y - py0

    def set_cursor_mode(self):
        self.canvas.configure(cursor="fleur" if self.app.zone_editing() else "crosshair" if self.app.click_mode() else "")
        self.canvas.delete("cursor")

    def _click(self, e):
        if not self._canvas_click(e):
            return
        if self.app.zone_editing():
            return self._zone_press(e)
        if self.app.click_mode():
            self.app.preview_clicked(*self._to_mm(e))

    def _canvas_click(self, e):
        # A grab can deliver mouse events outside the canvas to its bindings.
        c = self.canvas
        return (not self.app._closing and self.T is not None
                and c.grab_current() in (None, c)
                and 0 <= e.x < c.winfo_width() and 0 <= e.y < c.winfo_height()
                and c.winfo_containing(e.x_root, e.y_root) is c)

    def _hover(self, e):
        c = self.canvas
        c.delete("cursor")
        if self.app.zone_editing():
            c.configure(cursor="fleur")
            return
        mode = self.app.click_mode()
        c.configure(cursor="crosshair" if mode else "")
        if not mode or self.T is None:
            return
        x, y, fl, fb = self._to_mm(e)
        col = COLORS["bad"] if mode == "spot" else COLORS["head"]
        what = {"spot": f"start point here\n{fl:.1f} mm from left, {fb:.1f} up",
                "goto": f"Jog physical head here\nX {x:.1f}  Y {y:.1f}",
                "here": f"Mark observed dot\nX {x:.1f}  Y {y:.1f}"}[mode]
        right = e.x > c.winfo_width() * 0.6
        c.create_line(e.x - 18, e.y, e.x + 18, e.y, fill=col, dash=(3, 2), tags="cursor")
        c.create_line(e.x, e.y - 18, e.x, e.y + 18, fill=col, dash=(3, 2), tags="cursor")
        t = c.create_text(e.x - 10 if right else e.x + 10, e.y + 10, anchor="ne" if right else "nw", text=what,
                          fill=col, tags="cursor", font=("Segoe UI", 9, "bold"), justify="right" if right else "left")
        x0, y0, x1, y1 = c.bbox(t)
        c.tag_lower(c.create_rectangle(x0 - 3, y0 - 2, x1 + 3, y1 + 2, fill=COLORS["panel"], outline=col,
                                       tags="cursor"), t)

    @staticmethod
    def _zone_handles(zone):
        x0, y0, x1, y1 = keepouts.zone_bounds(zone)
        if zone["kind"] == "circle":
            return [(x1, zone["y"], "radius")]
        return [(x0,y0,"sw"), (x0,y1,"nw"), (x1,y1,"ne"), (x1,y0,"se")]

    def _zone_press(self, e):
        if self.app.layout_pending:
            return
        _, _, x, y = self._to_mm(e)
        zones = self.app.piece.get("keepouts", [])
        selected = self.app.selected_keepout()
        radius = 10 / self.T[2]
        found = None
        if selected is not None:
            for hx, hy, handle in self._zone_handles(zones[selected]):
                if math.hypot(x-hx,y-hy) <= radius:
                    found = (selected, handle)
                    break
        if found is None:
            for index in reversed(range(len(zones))):
                z = zones[index]
                x0,y0,x1,y1 = keepouts.zone_bounds(z)
                inside = (math.hypot(x-z["x"],y-z["y"]) <= z["r"] if z["kind"] == "circle"
                          else x0<=x<=x1 and y0<=y<=y1)
                if inside:
                    found = (index, "move")
                    break
        if found is None:
            return
        index, handle = found
        self.app.select_keepout(index)
        self._zone_drag = dict(index=index, handle=handle, original=copy.deepcopy(zones[index]),
                               start=(x,y), transform=self.T, moved=False)
        self.redraw()

    def _zone_motion(self, e):
        drag = self._zone_drag
        if drag is None or not self.app.zone_editing():
            return
        _, _, x, y = self._to_mm(e)
        piece = self.app.piece
        z = keepouts.drag_zone(drag["original"],piece["w"],piece["h"],
                               x-drag["start"][0],y-drag["start"][1],drag["handle"])
        if z != piece["keepouts"][drag["index"]]:
            drag["moved"] = True
            self.app.update_keepout(drag["index"],z,live=True)

    def _zone_release(self, e):
        drag, self._zone_drag = self._zone_drag, None
        if drag and drag["moved"]:
            self.app.update_keepout(drag["index"],self.app.piece["keepouts"][drag["index"]])
        self.refresh()

    def _zone_double_click(self, e):
        if self._canvas_click(e) and self.app.zone_editing():
            self._zone_press(e)
            self._zone_drag = None
            self.app.edit_keepout()

    def draw_head(self):
        app, c = self.app, self.canvas
        c.delete("head")
        if self.T is None:
            return
        ox, oy, s, vx0, vy1 = self.T
        observed = app.current_observation()
        if observed:
            ax, ay = ox + (observed[0] - vx0) * s, oy + (vy1 - observed[1]) * s
            col = COLORS["warn"]
            c.create_polygon(ax, ay-7, ax+7, ay, ax, ay+7, ax-7, ay, fill="", outline=col, tags="head")
            c.create_text(ax + 10, ay + 4, anchor="nw", text="Observed dot", fill=col, tags="head")
        st = app.head_position()
        if not st:
            if app.connected or (app.run_state or {}).get("phase") in ("running", "paused", "stopping"):
                msg = "Laser head · set job zero to locate it" if app.connected and not app.origin_set else (
                    "Laser head · live position is unavailable for this layout")
                c.create_text(8, 8, anchor="nw", text=msg, fill=COLORS["head"], tags="head")
            return
        x, y = ox + (st[0] - vx0) * s, oy + (vy1 - st[1]) * s
        stale = app.status_stale()
        col = COLORS["muted"] if stale else COLORS["bad"] if app.laser_is_on() else COLORS["head"]
        label = "Last reported head" if stale else "Laser head"
        width, height = c.winfo_width(), c.winfo_height()
        if not (10 <= x <= width - 10 and 10 <= y <= height - 10):
            c.create_text(8, 8, anchor="nw", text=f"{label} off view · X {st[0]:.1f} Y {st[1]:.1f}",
                          fill=col, tags="head")
            return
        c.create_oval(x - 9, y - 9, x + 9, y + 9, outline=col, width=3, tags="head")
        c.create_line(x - 13, y, x + 13, y, fill=col, width=1, tags="head")
        c.create_line(x, y - 13, x, y + 13, fill=col, width=1, tags="head")
        right = x > width - 140
        c.create_text(x - 12 if right else x + 12, y - 12 if y > 30 else y + 12,
                      anchor=("s" if y > 30 else "n") + ("e" if right else "w"),
                      text=label, fill=col, tags="head", font=("Segoe UI", 9, "bold"))

    def _update_info(self):
        app = self.app
        job = None if app.gfile else app.job
        gtext, gwarn = gcodeinfo.describe_fill(app.gfile) if app.gfile else ("", False)
        if job is None:
            self.info.configure(text="Open a picture to start." if not app.gfile else
                                f"{app.gfile['name']}: burns X {app.gfile['burn_bbox'][0]:.1f}..{app.gfile['burn_bbox'][2]:.1f}, "
                                f"Y {app.gfile['burn_bbox'][1]:.1f}..{app.gfile['burn_bbox'][3]:.1f} mm"
                                if app.gfile.get("burn_bbox") else "")
            self.legend.configure(text="")
            self._set_warning(gtext if gwarn else "")
            self._set_key(self._overlay_items())
            return
        g = job.geom
        txt = (f"Art {g.art_w:.1f} x {g.art_h:.1f} mm at X {g.x0:.1f}..{g.x1:.1f}, Y {g.y0:.1f}..{g.yt:.1f} from the "
               f"start point  |  {len(job.passes)} pass{'es' if len(job.passes) != 1 else ''}  |  {job.burn_cells:,} dots")
        if app.report:
            txt += f"  |  about {fmt_dur(job.est_s)}"
        self.info.configure(text=txt)
        self._set_warning(
            (gtext if gwarn else "") if app.gfile else
            "Heads-up: the picture burns right to the edge of its box all the way round, so it comes out as a "
            "filled rectangle. Fine for a photo that fills the piece. If the art should be a shape (a sticker, logo "
            "or stripes), its background is burning: see Guide > Backgrounds & stickers."
            if simulate.edge_burn(job) >= 0.6 else "")
        view = self.view.get()
        self._set_key(self._view_items(view) + self._overlay_items())
        self.legend.configure(text={
            "look": "Roughly how the finished piece will look on the material. Not a laser input.",
            "map": "Each pass in its own colour; later passes are drawn on top. Anything coloured gets the laser, "
                   "white is never touched.",
            "lgrbl": "How LaserGRBL draws the .nc (its default dark theme). It doesn't invert anything - wood jobs "
                     "just look like negatives there. 'Looks like' shows the real result.",
            "pic": "The picture after your adjustments, before it becomes laser moves. Darker = more burning "
                   + ("(Negative is on, so it's already flipped)." if job.material.negative else "."),
        }.get(view, ""))

    # ---------------------------------------------------------------- colour key
    def _set_warning(self, text):
        self.warn.configure(text=text)
        if text:
            self.warn.pack(fill="x", before=self.key)
        else:
            self.warn.pack_forget()

    def _view_items(self, view):
        """Key entries for what the art itself shows in this preview mode."""
        job = self.app.job
        if view == "look":
            bare, mark = (hexrgb(c) for c in LOOKS.get(job.material.look, LOOKS["pine"]))
            return [("fill", bare, "untouched material"), ("ramp", (bare, mark), "lighter to fuller marks"),
                    ("fill", mark, "fullest mark")]
        if view == "lgrbl":
            bg, fg = hexrgb(simulate.LASERGRBL_BG), hexrgb(simulate.LASERGRBL_LINE)
            return [("fill", bg, "laser off"), ("ramp", (bg, fg), "laser on: brighter = more power")]
        if view == "pic":
            return [("fill", "#ffffff", "no burn"), ("ramp", ("#ffffff", "#000000"), "darker = more burning")]
        sel = self.selected_passes()
        groups = {}
        for p in job.passes:
            if sel is None or p.key in sel:
                groups.setdefault(simulate.PASS_COLOURS.get(p.key, (25, 25, 25)), []).append(p.title)
        items = [("fill", "#ffffff", "no laser")]
        for col, titles in groups.items():
            text = titles[0] if len(titles) == 1 else f"{titles[0]} to {titles[-1]} (same dots each time)"
            items.append(("fill", hexrgb(col), f"{text}: laser fires"))
        if job.allowed is not None and not job.allowed.all():
            items.append(("fill", hexrgb((236, 225, 225)), "no-burn area (margins, no-burn zones)"))
        return items

    def _overlay_items(self):
        """Key entries for the lines and markers drawn over the art."""
        app = self.app
        items = []
        if self.grid_mm:
            items.append(("grid", COLORS["grid"], f"grid: {self.grid_mm:g} mm squares ({self.grid_mm / 25.4:.2f} in), "
                                                    "numbers = mm from the start point"))
        if app.job is not None and not app.gfile:
            items.append(("dash", COLORS["usable"], "usable area / optional image size guide"))
            if (app.job.piece or {}).get("keepouts"):
                items.append(("keepout", COLORS["bad"], "no-burn zone"))
            if any(p.kind == "dwell" for p in app.job.passes):
                items.append(("dot", COLORS["bad"], "burn-in-place spot: laser on, standing still, for the time shown"))
        if app.check_mode in ("image", "sticker"):
            items.append(("line", COLORS["art"], "image perimeter" if app.check_mode == "image" else "sticker outline"))
        elif app.check_mode == "travel":
            items.append(("dash", COLORS["travel"], "total travel perimeter, beam off"))
        elif app.check_mode == "travel_lit":
            items.append(("line", COLORS["art"], "total travel perimeter, 1% beam; approach/return off"))
        elif app.check_mode in ("burn", "dry"):
            marks = "marking strokes, 2% during trace" if app.check_mode == "burn" else "planned marking strokes, beam off"
            items.extend((("line", COLORS["art"], marks),
                          ("line", COLORS["travel"], "planned laser-off travel")))
        items.append(("cross", COLORS["accent"], "job zero, fixed at X0 Y0"))
        if app.head_position():
            items.append(("head", COLORS["head"], "laser head now (red while the laser is on)"))
        return items

    def _set_key(self, items):
        if items != self._key_items:
            self._key_items = items
            self._draw_key()

    def _draw_key(self):
        """Swatches with words, wrapped to the panel width."""
        k = self.key
        k.delete("all")
        font = ("Segoe UI", 9)
        W = max(200, k.winfo_width())
        x, y, row_h, sw = 2, 3, 20, 14
        fnt = tkfont.Font(font=font)
        for kind, col, text in self._key_items:
            w = sw + 6 + fnt.measure(text) + 16
            if x > 2 and x + w > W:
                x, y = 2, y + row_h
            x0, y0, x1, y1 = x, y + 2, x + sw, y + 2 + sw
            cy = (y0 + y1) / 2
            if kind == "fill":
                k.create_rectangle(x0, y0, x1, y1, fill=col, outline=COLORS["muted"])
            elif kind == "ramp":
                c0, c1 = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in col)
                for i in range(sw):
                    t = i / (sw - 1)
                    k.create_line(x0 + i, y0, x0 + i, y1, fill=hexrgb([a + (b - a) * t for a, b in zip(c0, c1)]))
                k.create_rectangle(x0, y0, x1, y1, outline=COLORS["muted"])
            elif kind == "dash":
                k.create_rectangle(x0, y0, x1, y1, outline=col, dash=(3, 2))
            elif kind == "box":
                k.create_rectangle(x0, y0, x1, y1, outline=col, width=2)
            elif kind == 'line':
                k.create_line(x0,y1,x0+sw/3,y0,x0+2*sw/3,y1,x1,y0,fill=col,width=2)
            elif kind == "keepout":
                k.create_rectangle(x0, y0, x1, y1, outline=col, width=2, fill=COLORS["keepout"], stipple="gray50")
            elif kind == "grid":
                for f in (1 / 3, 2 / 3):
                    k.create_line(x0 + sw * f, y0, x0 + sw * f, y1, fill=col)
                    k.create_line(x0, y0 + sw * f, x1, y0 + sw * f, fill=col)
            elif kind == "cross":
                k.create_line(x0, cy, x1, cy, fill=col, width=2)
                k.create_line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1, fill=col, width=2)
            elif kind == "dot":
                k.create_oval(x0 + 1, y0 + 1, x1 - 1, y1 - 1, fill=COLORS["panel"], outline=col, width=2)
            elif kind == "head":
                k.create_oval(x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline=col, width=2)
            k.create_text(x1 + 6, cy, text=text, anchor="w", font=font, fill=COLORS["ink"])
            x += w
        k.configure(height=y + row_h + 2 if self._key_items else 1)


def fmt_dur(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return "under a minute"
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m} min" if h else f"{m} min"
