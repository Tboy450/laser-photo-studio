"""Right-hand preview: the piece, the art (as it should look / what each pass burns / the source picture), keep-out
zones, laser-off run-up area, the origin, perimeter dots and the live head position."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from . import planner, simulate
from .presets import LOOKS
from .ui_common import COLORS, wrap_label


def hexrgb(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


class PreviewPanel(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=(6, 8, 10, 6))
        self.app = app
        self.view = tk.StringVar(value="look")
        self.show = tk.StringVar(value="")
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text="Preview:", style="H2.TLabel").pack(side="left")
        for text, val in (("Looks like", "look"), ("What burns", "map"), ("Toolpath", "toolpath"),
                          ("Picture", "pic")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.view, command=self.refresh).pack(side="left",
                                                                                                      padx=4)
        self.show_box = ttk.Combobox(bar, textvariable=self.show, state="readonly", width=18)
        self.show_box.pack(side="right")
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.show_lbl = ttk.Label(bar, text="Show:")
        self.show_lbl.pack(side="right", padx=4)
        self.canvas = tk.Canvas(self, background=COLORS["canvas"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=(6, 4))
        self.info = wrap_label(self, "", style="Muted.TLabel", width=900)
        self.info.pack(fill="x")
        self.legend = wrap_label(self, "", style="Small.TLabel", width=900)
        self.legend.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self._schedule())
        self._after = None
        self._cache = {}
        self._photo = None
        self.T = None

    # ---------------------------------------------------------------- options
    def set_job(self, job):
        self._cache.clear()
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
        elif self.view.get() in ("map", "toolpath"):
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
            elif self.view.get() == "toolpath":
                im = simulate.toolpath_view(job, sel)
            else:
                im = simulate.source_view(job)
            self._cache = {key: im}
        return self._cache[key]

    def bounds(self):
        app = self.app
        xs, ys = [0.0], [0.0]
        if app.job is not None:
            pr = app.job.geom.piece_rect
            xs += [pr[0], pr[2]]
            ys += [pr[1], pr[3]]
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
        self.T = (ox, oy, s, vx0, vy1)
        tx = lambda x: ox + (x - vx0) * s
        ty = lambda y: oy + (vy1 - y) * s
        app = self.app
        job = app.job
        look = LOOKS.get(app.mat.look, LOOKS["pine"])
        piece = job.piece if job is not None else app.piece
        px0, py0, px1, py1 = planner.piece_rect(piece)
        fill = {"look": hexrgb(look[0]), "toolpath": hexrgb(simulate.TOOLPATH_BG)}.get(self.view.get(), "#ffffff")
        if piece.get("shape") == "circle":
            c.create_oval(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline="#6b5b4b", width=2)
        else:
            c.create_rectangle(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline="#6b5b4b", width=2)
        if job is not None:
            g = job.geom
            ux0, uy0, ux1, uy1 = g.usable_rect
            c.create_rectangle(tx(ux0), ty(uy1), tx(ux1), ty(uy0), outline="#9a8f80", dash=(3, 3))
            if app.report and app.report.get("travel"):
                t = app.report["travel"]
                c.create_rectangle(tx(t[0]), ty(t[3]), tx(t[2]), ty(t[1]), outline="#7c8aa0", dash=(2, 4))
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
            c.create_rectangle(tx(g.x0), ty(g.yt), tx(g.x1), ty(g.y0), outline="#3b82f6", dash=(4, 2))
            for k in piece.get("keepouts", []):
                kx, ky = px0 + float(k["x"]), py0 + float(k["y"])
                if k.get("kind") == "circle":
                    r = float(k["r"])
                    c.create_oval(tx(kx - r), ty(ky + r), tx(kx + r), ty(ky - r), outline=COLORS["bad"], width=2,
                                  fill="#f3c7c7", stipple="gray50")
                else:
                    c.create_rectangle(tx(kx), ty(ky + float(k["h"])), tx(kx + float(k["w"])), ty(ky),
                                       outline=COLORS["bad"], width=2, fill="#f3c7c7", stipple="gray50")
        if app.gfile and app.gfile.get("burn_bbox"):
            b = app.gfile["burn_bbox"]
            c.create_rectangle(tx(b[0]), ty(b[3]), tx(b[2]), ty(b[1]), outline=COLORS["accent"], width=2)
            c.create_text(tx(b[0]) + 4, ty(b[3]) - 10, anchor="w", text=app.gfile["name"], fill=COLORS["accent"])
        # origin
        x, y = tx(0), ty(0)
        c.create_line(x - 14, y, x + 14, y, fill=COLORS["bad"], width=2)
        c.create_line(x, y - 14, x, y + 14, fill=COLORS["bad"], width=2)
        c.create_text(x + 8, y + 14, anchor="nw", text="origin 0,0", fill=COLORS["bad"], font=("Segoe UI", 9, "bold"))
        for i, (px, py, name) in enumerate(app.perim_points):
            col = COLORS["accent"] if app.perim_idx == i else "#ffffff"
            c.create_oval(tx(px) - 7, ty(py) - 7, tx(px) + 7, ty(py) + 7, fill=col, outline=COLORS["accent"], width=2)
            if name != "edge":
                c.create_text(tx(px), ty(py), text=str(i + 1), font=("Segoe UI", 8, "bold"))
        self.draw_head()
        self._update_info()

    def draw_head(self):
        c = self.canvas
        c.delete("head")
        st = self.app.head_position()
        if not st or self.T is None:
            return
        ox, oy, s, vx0, vy1 = self.T
        x, y = ox + (st[0] - vx0) * s, oy + (vy1 - st[1]) * s
        col = COLORS["bad"] if self.app.laser_is_on() else COLORS["blue"]
        c.create_oval(x - 9, y - 9, x + 9, y + 9, outline=col, width=3, tags="head")
        c.create_line(x - 13, y, x + 13, y, fill=col, width=1, tags="head")
        c.create_line(x, y - 13, x, y + 13, fill=col, width=1, tags="head")
        c.create_text(x + 12, y - 12, anchor="sw", text="head", fill=col, tags="head", font=("Segoe UI", 9, "bold"))

    def _update_info(self):
        app = self.app
        job = app.job
        if job is None:
            self.info.configure(text="Open a picture to start." if not app.gfile else
                                f"{app.gfile['name']}: burns X {app.gfile['burn_bbox'][0]:.1f}..{app.gfile['burn_bbox'][2]:.1f}, "
                                f"Y {app.gfile['burn_bbox'][1]:.1f}..{app.gfile['burn_bbox'][3]:.1f} mm"
                                if app.gfile.get("burn_bbox") else "")
            self.legend.configure(text="")
            return
        g = job.geom
        txt = (f"Art {g.art_w:.1f} x {g.art_h:.1f} mm at X {g.x0:.1f}..{g.x1:.1f}, Y {g.y0:.1f}..{g.yt:.1f} from the "
               f"origin  |  {len(job.passes)} pass{'es' if len(job.passes) != 1 else ''}  |  {job.burn_cells:,} dots")
        if app.report:
            txt += f"  |  about {fmt_dur(job.est_s)}"
        self.info.configure(text=txt)
        if self.view.get() == "map":
            self.legend.configure(text="Colours: orange = layer 1, red = layer 2, dark red = layer 3, blue = thin "
                                       "lines/labels, black = dots. Pink = no-burn area.")
        elif self.view.get() == "toolpath":
            self.legend.configure(text="Toolpath: bright marks show planned laser power for the selected passes. "
                                       "This is not live head position or a travel-motion trace.")
        else:
            self.legend.configure(text="Blue dashes = art box, grey dashes = usable area and laser-off run-ups, "
                                       "red = keep-out zones and the origin.")


def fmt_dur(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return "under a minute"
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m} min" if h else f"{m} min"
