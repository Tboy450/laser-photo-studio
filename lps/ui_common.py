"""Small Tk helpers: theme, scrollable pages, tooltips, labelled sliders."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

FONT = ("Segoe UI", 10)

# Colour themes. Every colour the app draws comes from here, by role:
#   bg / panel / field: page, card and input backgrounds; face: plain Tk widgets on ttk frames; ink / muted / dim: text, quieter text, disabled text
#   accent: highlights and perimeter points; ok / warn / bad: good / careful / stop; blue: links
#   canvas: behind the preview; art: the picture's box; head: the real laser head; header / status: top and bottom bars
#   grid: the preview's squares; grid_back: a thin line behind them so they show on any material ("" = none)
# 'light' is the original look. 'dragonfly' matches the NASA Dragonfly site. The others are high-contrast pairs.
THEMES = {
    "light": dict(name="Light (original)", face="SystemButtonFace", bg="#f4f2ee", panel="#ffffff", field="#ffffff", ink="#1f2328",
                  muted="#5f6670", dim="#9aa0a6", accent="#c2410c", ok="#147a3a", warn="#ad4f08", bad="#b91c1c",
                  blue="#1d4ed8", canvas="#d9d4cc", art="#2563eb", head="#7c3aed", header="#2b2622",
                  header_ink="#ffffff", header_muted="#cbbfb2", status="#e7e2da", select="#c2410c",
                  select_ink="#ffffff", border="#c9c2b8", tip="#fffbe6", ok_bg="#dcfce7", warn_bg="#fef3c7",
                  bad_bg="#fee2e2", blue_bg="#dbeafe", piece_edge="#6b5b4b", usable="#9a8f80", travel="#7c8aa0", grid="#5f6b80", grid_back="",
                  keepout="#f3c7c7", pill="#6b7280"),
    "dragonfly": dict(name="Dragonfly dark (navy)", face="#061019", bg="#061019", panel="#0d1d2b", field="#0a1622", ink="#ecf5ff",
                      muted="#8fa8bb", dim="#4f6577", accent="#ffb457", ok="#80f2ae", warn="#ffb457", bad="#ff6f91",
                      blue="#7ce7ff", canvas="#0a1622", art="#7ce7ff", head="#bba4ff", header="#03090f",
                      header_ink="#ecf5ff", header_muted="#7ce7ff", status="#0a1622", select="#1f4a66",
                      select_ink="#ecf5ff", border="#2a4256", tip="#13283a", ok_bg="#0f3324", warn_bg="#3a2a10",
                      bad_bg="#3a1020", blue_bg="#0f2d3d", piece_edge="#8fa8bb", usable="#5b7488",
                      travel="#6c7f95", grid="#5f9db8", grid_back="", keepout="#5a1830", pill="#34495a"),
    "yellow-black": dict(name="Contrast: yellow on black", face="#000000", bg="#000000", panel="#000000", field="#000000",
                         ink="#ffff00", muted="#ffff00", dim="#8a8a00", accent="#ffffff", ok="#00ff66",
                         warn="#ffcc00", bad="#ff4d4d", blue="#00ffff", canvas="#000000", art="#00ffff",
                         head="#ff66ff", header="#000000", header_ink="#ffff00", header_muted="#ffff00",
                         status="#000000", select="#ffff00", select_ink="#000000", border="#ffff00", tip="#000000",
                         ok_bg="#003b17", warn_bg="#3d3000", bad_bg="#4d0000", blue_bg="#003333",
                         piece_edge="#ffff00", usable="#ffff00", travel="#ffff00", grid="#ffff00", grid_back="#000000", keepout="#4d0000", pill="#333333"),
    "black-white": dict(name="Contrast: black on white", face="#ffffff", bg="#ffffff", panel="#ffffff", field="#ffffff",
                        ink="#000000", muted="#000000", dim="#767676", accent="#b00000", ok="#006400",
                        warn="#8a4b00", bad="#c00000", blue="#0000cc", canvas="#ffffff", art="#0000cc",
                        head="#7a00a8", header="#000000", header_ink="#ffffff", header_muted="#ffffff",
                        status="#ffffff", select="#000000", select_ink="#ffffff", border="#000000", tip="#ffffff",
                        ok_bg="#ffffff", warn_bg="#ffffff", bad_bg="#ffffff", blue_bg="#ffffff",
                        piece_edge="#000000", usable="#000000", travel="#000000", grid="#000000", grid_back="#ffffff", keepout="#ffb3b3", pill="#000000"),
    "black-yellow": dict(name="Contrast: black on yellow", face="#ffff00", bg="#ffff00", panel="#ffff00", field="#ffffcc",
                         ink="#000000", muted="#000000", dim="#6b6b00", accent="#b00000", ok="#005a00",
                         warn="#7a3d00", bad="#b00000", blue="#0000aa", canvas="#ffff66", art="#0000cc",
                         head="#7a00a8", header="#000000", header_ink="#ffff00", header_muted="#ffff00",
                         status="#ffff00", select="#000000", select_ink="#ffff00", border="#000000", tip="#ffffcc",
                         ok_bg="#ffff00", warn_bg="#ffff00", bad_bg="#ffff00", blue_bg="#ffff00",
                         piece_edge="#000000", usable="#000000", travel="#000000", grid="#000000", grid_back="#ffff00", keepout="#ff9999", pill="#000000"),
    "white-blue": dict(name="Contrast: white on blue", face="#003a8c", bg="#003a8c", panel="#003a8c", field="#002b66",
                       ink="#ffffff", muted="#ffffff", dim="#8fa6c9", accent="#ffd400", ok="#7dff9e", warn="#ffd400",
                       bad="#ff9a9a", blue="#ffffff", canvas="#002b66", art="#7fe3ff", head="#ffb3ff",
                       header="#002147", header_ink="#ffffff", header_muted="#ffffff", status="#002b66",
                       select="#ffffff", select_ink="#003a8c", border="#ffffff", tip="#002147", ok_bg="#0b4d2a",
                       warn_bg="#4d4000", bad_bg="#5c1020", blue_bg="#002147", piece_edge="#ffffff",
                       usable="#ffffff", travel="#ffffff", grid="#ffffff", grid_back="#003a8c", keepout="#5c1020", pill="#1b4f9c"),
    "blue-black": dict(name="Contrast: blue on black", face="#000000", bg="#000000", panel="#000000", field="#000000",
                       ink="#66ccff", muted="#66ccff", dim="#2f6a87", accent="#ffcc33", ok="#66ff99", warn="#ffcc33",
                       bad="#ff6666", blue="#99e0ff", canvas="#000000", art="#66ccff", head="#ff80ff",
                       header="#000000", header_ink="#66ccff", header_muted="#66ccff", status="#000000",
                       select="#66ccff", select_ink="#000000", border="#66ccff", tip="#000000", ok_bg="#003b17",
                       warn_bg="#3d3000", bad_bg="#4d0000", blue_bg="#002233", piece_edge="#66ccff",
                       usable="#66ccff", travel="#99e0ff", grid="#66ccff", grid_back="#000000", keepout="#4d0000", pill="#222222"),
}
COLORS = {k: v for k, v in THEMES["light"].items() if k != "name"}   # the current theme; changed in place
BADGE_ROLES = {"PROVEN": ("ok_bg", "ok"), "START": ("warn_bg", "warn"), "EXPERIMENTAL": ("bad_bg", "bad"),
               "MINE": ("blue_bg", "blue")}
_PAINTED = []     # (widget, {option: role}) for classic Tk widgets, repainted when the theme changes


def badge_colors(kind: str) -> tuple:
    bg, fg = BADGE_ROLES.get(kind, ("panel", "ink"))
    return COLORS[bg], COLORS[fg]


def paint(widget, **roles):
    """Colour a widget by role (e.g. background='header') and keep it in step with the theme."""
    _PAINTED.append((widget, roles))
    widget.configure(**{opt: COLORS[role] for opt, role in roles.items()})
    return widget


def apply_theme(root, name: str):
    """Switch every colour to theme `name`: ttk styles, painted widgets and later drawings."""
    COLORS.update({k: v for k, v in THEMES.get(name, THEMES["light"]).items() if k != "name"})
    setup_style(root, name)
    alive = []
    for w, roles in _PAINTED:
        try:
            if w.winfo_exists():
                w.configure(**{opt: COLORS[role] for opt, role in roles.items()})
                alive.append((w, roles))
        except tk.TclError:
            pass
    _PAINTED[:] = alive


def setup_style(root: tk.Tk, theme: str = "light"):
    import tkinter.font as tkfont
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family="Segoe UI", size=10)
        except tk.TclError:
            pass
    st = ttk.Style(root)
    C = COLORS
    if theme == "light":
        try:
            st.theme_use("vista")      # the original, native Windows look
        except tk.TclError:
            st.theme_use("clam")
    else:
        st.theme_use("clam")           # draws with our colours (the native look can't be recoloured)
        st.configure(".", background=C["bg"], foreground=C["ink"], fieldbackground=C["field"],
                     bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["bg"], troughcolor=C["field"],
                     focuscolor=C["accent"], selectbackground=C["select"], selectforeground=C["select_ink"],
                     insertcolor=C["ink"], arrowcolor=C["ink"])
        st.map(".", foreground=[("disabled", C["dim"])], background=[("disabled", C["bg"])])
        st.configure("TButton", background=C["panel"], foreground=C["ink"], bordercolor=C["border"])
        st.map("TButton", background=[("pressed", C["select"]), ("active", C["field"]), ("disabled", C["bg"])],
               foreground=[("pressed", C["select_ink"]), ("disabled", C["dim"])])
        for w in ("TEntry", "TSpinbox", "TCombobox"):
            st.configure(w, fieldbackground=C["field"], foreground=C["ink"], background=C["panel"])
            st.map(w, fieldbackground=[("readonly", C["field"]), ("disabled", C["bg"])],
                   foreground=[("disabled", C["dim"]), ("readonly", C["ink"])],
                   selectbackground=[("readonly", C["field"])], selectforeground=[("readonly", C["ink"])])
        for w in ("TCheckbutton", "TRadiobutton"):
            st.configure(w, background=C["bg"], foreground=C["ink"], indicatorbackground=C["field"],
                         indicatorforeground=C["ink"])
            st.map(w, background=[("active", C["bg"])], indicatorbackground=[("selected", C["select"])],
                   foreground=[("disabled", C["dim"])])
        st.configure("TNotebook", background=C["bg"], bordercolor=C["border"])
        st.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], bordercolor=C["border"])
        st.map("TNotebook.Tab", background=[("selected", C["bg"])], foreground=[("selected", C["ink"])])
        st.configure("TLabelframe", background=C["bg"], bordercolor=C["border"])
        st.configure("TLabelframe.Label", background=C["bg"], foreground=C["ink"])
        st.configure("Treeview", background=C["field"], fieldbackground=C["field"], foreground=C["ink"])
        st.map("Treeview", background=[("selected", C["select"])], foreground=[("selected", C["select_ink"])])
        st.configure("Treeview.Heading", background=C["panel"], foreground=C["ink"])
        st.configure("TProgressbar", background=C["accent"], troughcolor=C["field"])
        st.configure("Vertical.TScrollbar", background=C["panel"], troughcolor=C["bg"], arrowcolor=C["ink"])
        st.configure("TPanedwindow", background=C["bg"])
        root.option_add("*TCombobox*Listbox.background", C["field"])
        root.option_add("*TCombobox*Listbox.foreground", C["ink"])
        root.option_add("*TCombobox*Listbox.selectBackground", C["select"])
        root.option_add("*TCombobox*Listbox.selectForeground", C["select_ink"])
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
        self.canvas = paint(tk.Canvas(self, highlightthickness=0, borderwidth=0), background="bg")
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
        tk.Label(self.tip, text=self.text, justify="left", wraplength=self.wrap, background=COLORS["tip"],
                 foreground=COLORS["ink"], relief="solid", borderwidth=1, padx=8, pady=5).pack()

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
        self._dragging = False
        self._notify_after = None
        self.minimum, self.maximum = min(frm, to), max(frm, to)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=label).pack(side="left")
        self.edit_var = tk.StringVar()
        self.val = ttk.Entry(top, textvariable=self.edit_var, width=7, justify='right')
        self.val.bind('<Return>', self._commit_entry)
        self.val.bind('<FocusOut>', self._commit_entry)
        self.val.pack(side="right")
        self.scale = ttk.Scale(self, from_=frm, to=to, variable=var, command=self._moved)
        self.scale.pack(fill="x")
        self.scale.bind('<ButtonPress-1>', lambda e: self._start_drag(), add='+')
        self.scale.bind('<ButtonRelease-1>', lambda e: self._end_drag(), add='+')
        self.bind('<Destroy>', self._cancel_notify, add='+')
        var.trace_add("write", lambda *a: self._show())
        self._show()
        if tip:
            ToolTip(self, tip)

    def _show(self):
        try:
            v = round(self.var.get() / self.res) * self.res
        except tk.TclError:
            return
        self.edit_var.set(self.fmt.format(v))

    def _moved(self, *_):
        v = round(self.var.get() / self.res) * self.res
        self.edit_var.set(self.fmt.format(v))
        self._cancel_notify()
        if not self._dragging:
            self._notify_after = self.after(180, self._notify)

    def _cancel_notify(self, *_):
        if self._notify_after:
            self.after_cancel(self._notify_after)
            self._notify_after = None

    def _start_drag(self):
        self._dragging = True
        self._cancel_notify()

    def _end_drag(self):
        self._dragging = False
        self._cancel_notify()
        self._notify()

    def _notify(self):
        self._notify_after = None
        if self.command:
            self.command(round(self.var.get() / self.res) * self.res)

    def _commit_entry(self, *_):
        try:
            value = float(self.edit_var.get())
            if not math.isfinite(value):
                raise ValueError
            value = round(min(self.maximum, max(self.minimum, value)) / self.res) * self.res
        except ValueError:
            self._show()
            return
        if value != round(self.var.get() / self.res) * self.res:
            self._cancel_notify()
            self.var.set(value)
            self._notify()
        self._show()


def badge(parent, kind: str, text: str):
    bg, fg = badge_colors(kind)
    return tk.Label(parent, text=f" {text} ", background=bg, foreground=fg, font=("Segoe UI", 9, "bold"),
                    padx=4, pady=1)


def link(parent, text: str, command):
    """A small blue 'learn more' link."""
    lab = ttk.Label(parent, text=text, style="Link.TLabel", cursor="hand2")
    lab.bind("<Button-1>", lambda e: command())
    return lab


def moves_note(parent, role: str, text: str):
    """A colour swatch + one line saying what moves when you press the buttons below it ('art' or 'head')."""
    row = ttk.Frame(parent)
    paint(tk.Label(row, text="  "), background=role).pack(side="left", anchor="n", padx=(0, 6), pady=2)
    paint(wrap_label(row, text, font=("Segoe UI", 9, "bold")), foreground=role).pack(side="left", fill="x")
    return row
