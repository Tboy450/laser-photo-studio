"""Small Tk helpers: theme, scrollable pages, tooltips, labelled sliders."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT = ("Segoe UI", 10)
COLORS = dict(bg="#f4f2ee", panel="#ffffff", ink="#1f2328", muted="#5f6670", accent="#c2410c", ok="#15803d",
              warn="#b45309", bad="#b91c1c", blue="#1d4ed8", canvas="#d9d4cc")
BADGE_COLORS = {"PROVEN": ("#dcfce7", "#166534"), "START": ("#fef3c7", "#92400e"),
                "EXPERIMENTAL": ("#fee2e2", "#991b1b"), "MINE": ("#dbeafe", "#1e40af")}


def setup_style(root: tk.Tk):
    import tkinter.font as tkfont
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family="Segoe UI", size=10)
        except tk.TclError:
            pass
    st = ttk.Style(root)
    try:
        st.theme_use("vista")
    except tk.TclError:
        st.theme_use("clam")
    st.configure("TLabel", font=FONT)
    st.configure("TButton", font=FONT)
    st.configure("TCheckbutton", font=FONT)
    st.configure("TRadiobutton", font=FONT)
    st.configure("TNotebook.Tab", padding=(12, 6), font=("Segoe UI", 10, "bold"))
    st.configure("H1.TLabel", font=("Segoe UI", 15, "bold"))
    st.configure("H2.TLabel", font=("Segoe UI", 11, "bold"))
    st.configure("Muted.TLabel", foreground=COLORS["muted"])
    st.configure("Small.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 9))
    st.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))
    st.configure("Tool.TButton", padding=(6, 3))
    st.configure("Card.TLabelframe", padding=10)
    st.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
    st.configure("Link.TLabel", foreground=COLORS["blue"], font=("Segoe UI", 9, "underline"))
    try:
        line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        st.configure("Treeview", rowheight=int(line * 1.45))
    except tk.TclError:
        pass
    return st


class ScrollFrame(ttk.Frame):
    """A vertically scrolling page; put widgets in `.inner`."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background=COLORS["bg"])
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas, padding=(14, 12))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.inner.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.inner.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-e.delta / 120), "units")


class ToolTip:
    def __init__(self, widget, text: str, wrap: int = 320):
        self.widget, self.text, self.wrap, self.tip = widget, text, wrap, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", wraplength=self.wrap, background="#fffbe6",
                 relief="solid", borderwidth=1, padx=8, pady=5).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def wrap_label(parent, text="", style=None, width=360, **kw):
    """A label that wraps to its parent's real width (so text never runs off the panel)."""
    lab = ttk.Label(parent, text=text, wraplength=width, justify="left", style=style or "TLabel", **kw)

    def fit(e, lab=lab):
        try:
            w = max(160, e.width - 28)
            if abs(float(str(lab.cget("wraplength") or 0)) - w) > 4:
                lab.configure(wraplength=w)
        except tk.TclError:
            pass  # the label was destroyed; nothing to fit

    parent.bind("<Configure>", fit, add="+")
    return lab


class Slider(ttk.Frame):
    """Label + slider + live value, calling `command(value)` when released or changed."""

    def __init__(self, master, label, var: tk.DoubleVar, frm, to, fmt="{:.0f}", command=None, tip=None,
                 resolution=1.0):
        super().__init__(master)
        self.var, self.fmt, self.command, self.res = var, fmt, command, resolution
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=label).pack(side="left")
        self.val = ttk.Label(top, style="Muted.TLabel")
        self.val.pack(side="right")
        self.scale = ttk.Scale(self, from_=frm, to=to, variable=var, command=self._moved)
        self.scale.pack(fill="x")
        var.trace_add("write", lambda *a: self._show())
        self._show()
        if tip:
            ToolTip(self, tip)

    def _show(self):
        try:
            v = round(self.var.get() / self.res) * self.res
        except tk.TclError:
            return
        self.val.configure(text=self.fmt.format(v))

    def _moved(self, *_):
        v = round(self.var.get() / self.res) * self.res
        self.val.configure(text=self.fmt.format(v))
        if self.command:
            self.command(v)


def badge(parent, kind: str, text: str):
    bg, fg = BADGE_COLORS.get(kind, ("#eee", "#333"))
    return tk.Label(parent, text=f" {text} ", background=bg, foreground=fg, font=("Segoe UI", 9, "bold"),
                    padx=4, pady=1)


def link(parent, text: str, command):
    """A small blue 'learn more' link."""
    lab = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2")
    lab.bind("<Button-1>", lambda e: command())
    return lab
