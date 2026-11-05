"""Right-hand preview: the piece, the art (as it should look / what each pass burns / the source picture), no-burn
zones, laser-off run-up area, the start point, perimeter dots and the live head position."""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import Image, ImageTk

from . import gcodeinfo, planner, simulate
from .presets import LOOKS
from .ui_common import COLORS, paint, wrap_label


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
        for text, val in (("Looks like", "look"), ("What burns", "map"), ("In LaserGRBL", "lgrbl"),
                          ("Picture", "pic")):
            ttk.Radiobutton(bar, text=text, value=val, variable=self.view, command=self.refresh).pack(side="left",
                                                                                                      padx=4)
        self.show_box = ttk.Combobox(bar, textvariable=self.show, state="readonly", width=18)
        self.show_box.pack(side="right")
        self.show_box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.show_lbl = ttk.Label(bar, text="Show:")
        self.show_lbl.pack(side="right", padx=4)
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
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda e: self.canvas.delete("cursor"))
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
        fill = {"look": hexrgb(look[0]), "lgrbl": hexrgb(simulate.LASERGRBL_BG)}.get(self.view.get(), "#ffffff")
        if piece.get("shape") == "circle":
            c.create_oval(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline=COLORS["piece_edge"], width=2)
        else:
            c.create_rectangle(tx(px0), ty(py1), tx(px1), ty(py0), fill=fill, outline=COLORS["piece_edge"], width=2)
        if job is not None:
            g = job.geom
            ux0, uy0, ux1, uy1 = g.usable_rect
            c.create_rectangle(tx(ux0), ty(uy1), tx(ux1), ty(uy0), outline=COLORS["usable"], dash=(3, 3))
            if app.report and app.report.get("travel"):
                t = app.report["travel"]
                c.create_rectangle(tx(t[0]), ty(t[3]), tx(t[2]), ty(t[1]), outline=COLORS["travel"], dash=(2, 4))
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
            c.create_rectangle(tx(g.x0), ty(g.yt), tx(g.x1), ty(g.y0), outline=COLORS["art"], dash=(4, 2))
            for k in piece.get("keepouts", []):
                kx, ky = px0 + float(k["x"]), py0 + float(k["y"])
                if k.get("kind") == "circle":
                    r = float(k["r"])
                    c.create_oval(tx(kx - r), ty(ky + r), tx(kx + r), ty(ky - r), outline=COLORS["bad"], width=2,
                                  fill=COLORS["keepout"], stipple="gray50")
                else:
                    c.create_rectangle(tx(kx), ty(ky + float(k["h"])), tx(kx + float(k["w"])), ty(ky),
                                       outline=COLORS["bad"], width=2, fill=COLORS["keepout"], stipple="gray50")
        if app.gfile and app.gfile.get("burn_bbox"):
            b = app.gfile["burn_bbox"]
            c.create_rectangle(tx(b[0]), ty(b[3]), tx(b[2]), ty(b[1]), outline=COLORS["accent"], width=2)
            c.create_text(tx(b[0]) + 4, ty(b[3]) - 10, anchor="w", text=app.gfile["name"], fill=COLORS["accent"])
        # origin
        x, y = tx(0), ty(0)
        c.create_line(x - 14, y, x + 14, y, fill=COLORS["bad"], width=2)
        c.create_line(x, y - 14, x, y + 14, fill=COLORS["bad"], width=2)
        c.create_text(x + 8, y + 14, anchor="nw", text="start 0,0", fill=COLORS["bad"], font=("Segoe UI", 9, "bold"))
        for i, (px, py, name) in enumerate(app.perim_points):
            col = COLORS["accent"] if app.perim_idx == i else "#ffffff"
            c.create_oval(tx(px) - 7, ty(py) - 7, tx(px) + 7, ty(py) + 7, fill=col, outline=COLORS["accent"], width=2)
            if name != "edge":
                c.create_text(tx(px), ty(py), text=str(i + 1), font=("Segoe UI", 8, "bold"))
        self.draw_head()
        self._update_info()

    def _to_mm(self, e):
        """Canvas pixel -> (work X, work Y, mm from the piece's left edge, mm up from its bottom edge)."""
        ox, oy, s, vx0, vy1 = self.T
        x, y = vx0 + (e.x - ox) / s, vy1 - (e.y - oy) / s
        job = self.app.job
        px0, py0, _, _ = planner.piece_rect(job.piece if job is not None else self.app.piece)
        return x, y, x - px0, y - py0

    def set_cursor_mode(self):
        self.canvas.configure(cursor="crosshair" if self.app.click_mode() else "")
        self.canvas.delete("cursor")

    def _click(self, e):
        if self.T is not None and self.app.click_mode():
            self.app.preview_clicked(*self._to_mm(e))

    def _hover(self, e):
        c = self.canvas
        c.delete("cursor")
        mode = self.app.click_mode()
        c.configure(cursor="crosshair" if mode else "")
        if not mode or self.T is None:
            return
        x, y, fl, fb = self._to_mm(e)
        col = COLORS["bad"] if mode == "spot" else COLORS["head"]
        what = {"spot": f"start point here\n{fl:.1f} mm from left, {fb:.1f} up",
                "goto": f"move the head here\nX {x:.1f}  Y {y:.1f}",
                "here": f"the dot is here\nX {x:.1f}  Y {y:.1f}"}[mode]
        right = e.x > c.winfo_width() * 0.6
        c.create_line(e.x - 18, e.y, e.x + 18, e.y, fill=col, dash=(3, 2), tags="cursor")
        c.create_line(e.x, e.y - 18, e.x, e.y + 18, fill=col, dash=(3, 2), tags="cursor")
        t = c.create_text(e.x - 10 if right else e.x + 10, e.y + 10, anchor="ne" if right else "nw", text=what,
                          fill=col, tags="cursor", font=("Segoe UI", 9, "bold"), justify="right" if right else "left")
        x0, y0, x1, y1 = c.bbox(t)
        c.tag_lower(c.create_rectangle(x0 - 3, y0 - 2, x1 + 3, y1 + 2, fill=COLORS["panel"], outline=col,
                                       tags="cursor"), t)

    def draw_head(self):
        c = self.canvas
        c.delete("head")
        st = self.app.head_position()
        if not st or self.T is None:
            return
        ox, oy, s, vx0, vy1 = self.T
        x, y = ox + (st[0] - vx0) * s, oy + (vy1 - st[1]) * s
        col = COLORS["bad"] if self.app.laser_is_on() else COLORS["head"]
        c.create_oval(x - 9, y - 9, x + 9, y + 9, outline=col, width=3, tags="head")
        c.create_line(x - 13, y, x + 13, y, fill=col, width=1, tags="head")
        c.create_line(x, y - 13, x, y + 13, fill=col, width=1, tags="head")
        c.create_text(x + 12, y - 12, anchor="sw", text="head", fill=col, tags="head", font=("Segoe UI", 9, "bold"))

    def _update_info(self):
        app = self.app
        job = app.job
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
        if app.job is not None:
            items += [("dash", COLORS["art"], "picture (art box)"), ("dash", COLORS["usable"], "usable area")]
            if app.report and app.report.get("travel"):
                items.append(("dash", COLORS["travel"], "laser-off run-ups"))
            if (app.job.piece or {}).get("keepouts"):
                items.append(("keepout", COLORS["bad"], "no-burn zone"))
        if app.gfile and app.gfile.get("burn_bbox"):
            items.append(("box", COLORS["accent"], "where the .nc file burns"))
        items.append(("cross", COLORS["bad"], "start point 0,0 (where the head starts)"))
        if app.perim_points:
            items.append(("dot", COLORS["accent"], "perimeter check points"))
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
            elif kind == "keepout":
                k.create_rectangle(x0, y0, x1, y1, outline=col, width=2, fill=COLORS["keepout"], stipple="gray50")
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
