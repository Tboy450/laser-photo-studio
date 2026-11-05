"""Step 2 photo strip ('About this setting') and the photo viewer."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from . import jobs, samples
from .dialogs import FormDialog
from .imaging import PICTURE_TYPES
from .ui_common import link, paint, wrap_label

COLS = 3
SHOW = 6


class SampleStrip(ttk.Frame):
    """Up to six thumbnails with their kind and title; click one to open the viewer."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.items, self.mat, self._key, self._refs, self.viewer = [], None, None, [], None
        self._note, self._resize_after = "", None
        scale = max(1.0, app.root.winfo_fpixels("1i") / 96.0)
        self.base = (int(128 * scale), int(96 * scale))
        self.thumb = self.base
        self.gap = int(10 * scale)
        self.grid_box = ttk.Frame(self)
        self.grid_box.pack(fill="x")
        self.note = wrap_label(self, "", style="Small.TLabel")
        self.note.pack(anchor="w", pady=(2, 0))
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(2, 0))
        self.count = ttk.Label(bar, style="Small.TLabel")
        self.count.pack(side="left")
        link(bar, "Add my photo...", self.add_photo).pack(side="right")
        self.bind("<Configure>", self._resized)

    def _resized(self, e):
        """Three thumbnails always fit across the panel."""
        tw = max(80, min(self.base[0], (e.width - (COLS - 1) * self.gap) // COLS - 2))
        if abs(tw - self.thumb[0]) >= 6:
            self.thumb = (tw, tw * 3 // 4)
            if self._resize_after:
                self.after_cancel(self._resize_after)
            self._resize_after = self.after(120, self._render)

    def show(self, mat, force=False):
        key = (mat.key, getattr(mat, "based_on", ""))
        self.mat = mat
        if key == self._key and not force:
            return
        self._key = key
        self.items, self._note = samples.for_material(mat)
        self._render()
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.set_items(self.items, 0)

    def _render(self):
        self._resize_after = None
        for w in self.grid_box.winfo_children():
            w.destroy()
        self._refs = []
        if not self.items:
            ttk.Label(self.grid_box, text="No photos for this setting yet. After a test grid or a finished piece, add "
                                          "your photo here to keep it with the setting.", style="Muted.TLabel",
                      wraplength=COLS * (self.thumb[0] + self.gap), justify="left").grid(row=0, column=0, sticky="w")
        for i, s in enumerate(self.items[:SHOW]):
            self._tile(i, s)
        n = len(self.items)
        self.count.configure(text="" if not n else
                             f"{SHOW} of {n} photos - click to enlarge" if n > SHOW else
                             f"{n} photo{'s' if n != 1 else ''} - click to enlarge")
        self.note.configure(text=self._note)

    def _tile(self, i, s):
        tile = paint(tk.Frame(self.grid_box, cursor="hand2"), background="face")
        tile.grid(row=i // COLS, column=i % COLS, padx=(0, self.gap), pady=(0, self.gap), sticky="nw")
        ph = ImageTk.PhotoImage(samples.thumbnail(s.path, self.thumb))
        self._refs.append(ph)
        paint(tk.Label(tile, image=ph, width=self.thumb[0], height=self.thumb[1], cursor="hand2"),
              background="canvas").pack()
        label, bg, fg = samples.KINDS.get(s.kind, samples.KINDS["test"])
        tk.Label(tile, text=label, font=("Segoe UI", 8, "bold"), foreground=fg, background=bg, padx=3,
                 cursor="hand2").pack(anchor="w", pady=(3, 0))
        paint(tk.Label(tile, text=s.title, font=("Segoe UI", 9), wraplength=self.thumb[0], justify="left",
                       anchor="w", cursor="hand2"), background="face", foreground="ink").pack(anchor="w")
        for w in (tile, *tile.winfo_children()):
            w.bind("<Button-1>", lambda e, i=i: self.open(i))

    def open(self, i):
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.set_items(self.items, i)
            self.viewer.deiconify()
            self.viewer.lift()
        else:
            self.viewer = SampleViewer(self, i)

    def add_photo(self):
        if self.mat is None:
            return
        path = filedialog.askopenfilename(
            title=f"Add a photo to '{self.mat.name}'",
            filetypes=[("Pictures", " ".join("*" + e for e in PICTURE_TYPES)), ("All files", "*.*")])
        if not path:
            return
        labels = [v[0] for v in samples.KINDS.values()]
        d = FormDialog(self.app.root, "Add my photo", [
            ("title", "Title", Path(path).stem, "str"),
            ("kind", "What it shows", samples.KINDS["test"][0], labels),
            ("caption", "Notes (optional)", "", "str")],
            intro=f"The photo is copied into your Laser Photo Studio folder and shown with '{self.mat.name}'. "
                  "Tip: note the settings, e.g. '45% 3000 mm/min, top row'.", ok_text="Add").result
        if not d:
            return
        kind = next((k for k, v in samples.KINDS.items() if v[0] == d["kind"]), "test")
        try:
            samples.add_user_photo(self.mat.key, path, d["title"].strip() or Path(path).stem, kind,
                                   d["caption"].strip())
        except Exception as e:
            messagebox.showerror("Couldn't add the photo", f"{Path(path).name}\n\n{e}")
            return
        self.show(self.mat, force=True)
        self.app.say("Photo added to this setting.", "ok")


class SampleViewer(tk.Toplevel):
    """Big view of one photo with its caption; Previous / Next go through the setting's photos."""

    def __init__(self, strip, index=0):
        super().__init__(strip.app.root)
        self.strip, self.items, self.i = strip, strip.items, index
        self.geometry("1100x840")
        self.minsize(640, 480)
        ico = jobs.APP_DIR / "assets" / "icon.ico"
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self.canvas = tk.Canvas(self, background="#1f2328", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        info = ttk.Frame(self, padding=(14, 10))
        info.pack(fill="x")
        head = ttk.Frame(info)
        head.pack(fill="x")
        self.badge = tk.Label(head, font=("Segoe UI", 9, "bold"), padx=6, pady=1)
        self.badge.pack(side="left")
        self.title_lbl = ttk.Label(head, style="H2.TLabel")
        self.title_lbl.pack(side="left", padx=8)
        self.pos_lbl = ttk.Label(head, style="Muted.TLabel")
        self.pos_lbl.pack(side="right")
        self.caption = wrap_label(info, "", width=1000)
        self.caption.pack(anchor="w", fill="x", pady=(6, 0))
        self.meta = ttk.Label(info, style="Small.TLabel")
        self.meta.pack(anchor="w", pady=(4, 0))
        bar = ttk.Frame(info)
        bar.pack(fill="x", pady=(8, 0))
        self.prev_btn = ttk.Button(bar, text="< Previous", command=lambda: self.step(-1))
        self.prev_btn.pack(side="left")
        self.next_btn = ttk.Button(bar, text="Next >", command=lambda: self.step(1))
        self.next_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=self.destroy).pack(side="right")
        self.remove_btn = ttk.Button(bar, text="Remove my photo", command=self.remove)
        self.remove_btn.pack(side="right", padx=6)
        self.open_btn = ttk.Button(bar, text="Open full size", command=self.open_file)
        self.open_btn.pack(side="right")
        for k, f in (("<Left>", lambda e: self.step(-1)), ("<Right>", lambda e: self.step(1)),
                     ("<Escape>", lambda e: self.destroy())):
            self.bind(k, f)
        self.canvas.bind("<Configure>", lambda e: self._schedule())
        self._pil = self._photo = self._after = None
        self.set_items(self.items, index)

    def set_items(self, items, index):
        self.items = items
        if not items:
            self.destroy()
            return
        self.show(max(0, min(index, len(items) - 1)))

    def show(self, i):
        self.i = i
        s = self.items[i]
        name = self.strip.mat.name if self.strip.mat is not None else ""
        self.title(f"{name} - photos")
        label, bg, fg = samples.KINDS.get(s.kind, samples.KINDS["test"])
        self.badge.configure(text=label, background=bg, foreground=fg)
        self.title_lbl.configure(text=s.title)
        self.pos_lbl.configure(text=f"{i + 1} of {len(self.items)}")
        self.caption.configure(text=s.caption or "(no notes)")
        when = s.date
        self.meta.configure(text=(f"Your photo, added {when}" if s.user else
                                  f"{when} - from the project: {s.source}") if when else "")
        self.prev_btn.state(["!disabled"] if i > 0 else ["disabled"])
        self.next_btn.state(["!disabled"] if i < len(self.items) - 1 else ["disabled"])
        self.remove_btn.pack_forget()
        if s.user:
            self.remove_btn.pack(side="right", padx=6, before=self.open_btn)
        self._pil = Image.open(s.path).convert("RGB")
        self._draw()

    def step(self, d):
        j = self.i + d
        if 0 <= j < len(self.items):
            self.show(j)

    def _schedule(self):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(60, self._draw)

    def _draw(self):
        self._after = None
        if self._pil is None:
            return
        W, H = max(50, self.canvas.winfo_width()), max(50, self.canvas.winfo_height())
        im = self._pil.copy()
        s = min((W - 20) / im.width, (H - 20) / im.height)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                       Image.Resampling.LANCZOS if s < 1 else Image.Resampling.BICUBIC)
        self._photo = ImageTk.PhotoImage(im)
        self.canvas.delete("all")
        self.canvas.create_image(W // 2, H // 2, image=self._photo)

    def open_file(self):
        os.startfile(str(self.items[self.i].path))

    def remove(self):
        s = self.items[self.i]
        if not s.user or not messagebox.askyesno("Remove photo", f"Remove '{s.title}' from this setting?",
                                                 parent=self):
            return
        samples.remove_user_photo(s)
        self.strip.show(self.strip.mat, force=True)
        if self.winfo_exists():
            self.set_items(self.strip.items, min(self.i, len(self.strip.items) - 1))
