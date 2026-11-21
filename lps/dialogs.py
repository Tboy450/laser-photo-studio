"""Dialogs: start checklist, resume-after-dropout wizard, test grid, settings, simple forms."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import jobs, machine, presets
from .presets import STYLES, Material
from .ui_common import COLORS, ScrollFrame, wrap_label


class FormDialog(tk.Toplevel):
    """fields: list of (key, label, default, kind) with kind in float/int/str/choice:[...]/bool."""

    def __init__(self, master, title, fields, intro=None, ok_text="OK"):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        if intro:
            wrap_label(body, intro, width=380).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.vars = {}
        for i, (key, label, default, kind) in enumerate(fields, 1):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 10))
            if kind == "bool":
                v = tk.BooleanVar(value=bool(default))
                ttk.Checkbutton(body, variable=v).grid(row=i, column=1, sticky="w")
            elif isinstance(kind, list):
                v = tk.StringVar(value=str(default))
                ttk.Combobox(body, textvariable=v, values=kind, state="readonly", width=26).grid(row=i, column=1,
                                                                                                 sticky="we")
            else:
                v = tk.StringVar(value=str(default))
                ttk.Entry(body, textvariable=v, width=28).grid(row=i, column=1, sticky="we")
            self.vars[key] = (v, kind)
        bar = ttk.Frame(body)
        bar.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text=ok_text, command=self._ok).pack(side="right", padx=6)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()
        self.wait_window()

    def _ok(self):
        out = {}
        for k, (v, kind) in self.vars.items():
            raw = v.get()
            try:
                if kind == "float":
                    out[k] = float(raw)
                elif kind == "int":
                    out[k] = int(float(raw))
                else:
                    out[k] = raw
            except ValueError:
                messagebox.showerror("Check the numbers", f"'{raw}' is not a number.", parent=self)
                return
        self.result = out
        self.destroy()


class StartDialog(tk.Toplevel):
    def __init__(self, master, summary: str, pause_default: bool, multi: bool):
        super().__init__(master)
        self.title("Ready to engrave?")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Ready to engrave?", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, summary, width=460).pack(anchor="w", pady=(6, 10))
        self.checks = []
        for text in ("I ran the perimeter check and the art is where I want it.",
                     "The laser is focused, and air assist and ventilation are on.",
                     "I'll stay with the machine the whole time (fire risk) and wear laser glasses."):
            v = tk.BooleanVar(value=False)
            ttk.Checkbutton(f, text=text, variable=v, command=self._update).pack(anchor="w", pady=2)
            self.checks.append(v)
        self.pause = tk.BooleanVar(value=pause_default and multi)
        cb = ttk.Checkbutton(f, text="Pause after each layer so I can take a photo (head parks at the origin)",
                             variable=self.pause)
        cb.pack(anchor="w", pady=(10, 2))
        if not multi:
            cb.state(["disabled"])
        wrap_label(f, "The job runs in the background: you can close this app and it keeps going. "
                      "If the USB drops out, the app records exactly where it stopped.", style="Small.TLabel",
                   width=460).pack(anchor="w", pady=(6, 0))
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(14, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        self.go = ttk.Button(bar, text="Start engraving", style="Big.TButton", command=self._ok)
        self.go.pack(side="right", padx=8)
        self._update()
        self.grab_set()
        self.wait_window()

    def _update(self):
        self.go.state(["!disabled"] if all(v.get() for v in self.checks) else ["disabled"])

    def _ok(self):
        self.result = dict(pause_between=self.pause.get())
        self.destroy()


class TestGridDialog(tk.Toplevel):
    def __init__(self, master, mat: Material):
        super().__init__(master)
        self.title("Test grid for a new material")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Material test grid", style="H1.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        wrap_label(f, "Burns larger labelled patches: power across, speed down. Each patch has a solid top and a "
                      "dot ramp below, so you can see both solid areas and shading. Pick the best-looking patch, "
                      "then save it as your own preset.", width=430).grid(row=1, column=0, columnspan=2, sticky="w",
                                                                        pady=(4, 10))
        lo, hi = mat.test_power
        p_vals = ", ".join(str(int(round(lo + (hi - lo) * k / 4))) for k in range(5))
        s_lo, s_hi = mat.test_speed
        s_vals = ", ".join(str(int(round((s_lo + (s_hi - s_lo) * k / 2) / 100) * 100)) for k in range(3))
        self.v = {}
        rows = [("powers", "Powers (%)", p_vals), ("speeds", "Speeds (mm/min, max 6000)", s_vals),
                ("patch", "Patch size (mm)", "8"), ("gap", "Gap between patches (mm)", "4")]
        for i, (k, label, val) in enumerate(rows, 2):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", pady=3)
            self.v[k] = tk.StringVar(value=val)
            ttk.Entry(f, textvariable=self.v[k], width=24).grid(row=i, column=1, sticky="we", padx=(10, 0))
        self.content = tk.StringVar(value="solid+ramp")
        ttk.Radiobutton(f, text="Solid top + dot ramp (recommended)", value="solid+ramp",
                        variable=self.content).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Radiobutton(f, text="Solid patches only", value="solid", variable=self.content).grid(
            row=7, column=0, columnspan=2, sticky="w")
        wrap_label(f, f"Suggested range for '{mat.name}'. Speeds above 3000 need longer laser-off run-ups "
                      "(about 10 mm at 6000), which the grid adds automatically.", style="Small.TLabel",
                   width=430).grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        bar = ttk.Frame(f)
        bar.grid(row=9, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Make test grid", command=self._ok).pack(side="right", padx=6)
        self.grab_set()
        self.wait_window()

    def _ok(self):
        try:
            powers = [float(x) for x in self.v["powers"].get().replace(";", ",").split(",") if x.strip()]
            speeds = [int(float(x)) for x in self.v["speeds"].get().replace(";", ",").split(",") if x.strip()]
            patch, gap = float(self.v["patch"].get()), float(self.v["gap"].get())
        except ValueError:
            messagebox.showerror("Check the numbers", "Use numbers separated by commas.", parent=self)
            return
        if not powers or not speeds or any(not 1 <= p <= 100 for p in powers) or any(not 100 <= s <= 6000 for s in speeds):
            messagebox.showerror("Check the numbers", "Powers must be 1-100 % and speeds 100-6000 mm/min.",
                                 parent=self)
            return
        self.result = dict(powers=powers, speeds=speeds, patch=max(3.0, patch), gap=max(1.0, gap),
                           content=self.content.get())
        self.destroy()


class HelpWindow(tk.Toplevel):
    """The Guide: plain-English topics on the left, text on the right."""

    def __init__(self, app, topic=None):
        super().__init__(app.root)
        from . import helptext
        self.app = app
        self.title("Laser Photo Studio - Guide")
        self.geometry("1000x720")
        ico = jobs.APP_DIR / "assets" / "icon.ico"
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self.topics = helptext.topics(app.mat)
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        self.lst = tk.Listbox(body, activestyle="none", exportselection=False, width=26, font=("Segoe UI", 11),
                              borderwidth=0, highlightthickness=0, selectbackground="#c2410c")
        self.lst.pack(side="left", fill="y", padx=(0, 8))
        for title, _ in self.topics:
            self.lst.insert("end", "  " + title)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._render(self.lst.curselection()[0])
                      if self.lst.curselection() else None)
        self.txt = tk.Text(body, wrap="word", padx=18, pady=12, borderwidth=0, font=("Segoe UI", 10),
                           cursor="arrow", background="#fffdf9")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        self.txt.tag_configure("h", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=4)
        self.txt.tag_configure("p", spacing3=4)
        self.txt.tag_configure("li", lmargin1=14, lmargin2=32, spacing3=3)
        self.txt.tag_configure("title", font=("Segoe UI", 16, "bold"), spacing3=6)
        self._img = None
        self.show_topic(topic)

    def show_topic(self, topic=None):
        idx = next((i for i, (t, _) in enumerate(self.topics) if t == topic), 0)
        self.lst.selection_clear(0, "end")
        self.lst.selection_set(idx)
        self.lst.see(idx)
        self._render(idx)

    def _render(self, idx):
        title, text = self.topics[idx]
        t = self.txt
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", title + "\n", "title")
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("# "):
                t.insert("end", s[2:] + "\n", "h")
            elif s.startswith("- "):
                t.insert("end", "\u2022  " + s[2:] + "\n", "li")
            elif len(s) > 2 and s[0].isdigit() and s[1:3] == ". ":
                t.insert("end", s + "\n", "li")
            elif s.startswith("[image:") and s.endswith("]"):
                self._image(s[7:-1])
            elif s:
                t.insert("end", s + "\n", "p")
            else:
                t.insert("end", "\n")
        t.configure(state="disabled")
        t.yview_moveto(0)

    def _image(self, rel):
        path = jobs.APP_DIR / rel
        if not path.exists():
            return
        from PIL import Image, ImageTk
        im = Image.open(path)
        width = max(300, self.txt.winfo_width() - 60) if self.txt.winfo_width() > 100 else 700
        im.thumbnail((width, 2000), Image.Resampling.LANCZOS)
        self._img = ImageTk.PhotoImage(im)
        self.txt.insert("end", "\n")
        self.txt.image_create("end", image=self._img, padx=4, pady=6)
        self.txt.insert("end", "\n")


class SettingsDialog(FormDialog):
    def __init__(self, master, settings: dict):
        ports = [p for p, _ in machine.list_ports()] or ["COM4"]
        super().__init__(master, "Settings", [
            ("port", "Laser USB port", settings["port"], ports + (["COM4"] if "COM4" not in ports else [])),
            ("baud", "Baud rate", settings["baud"], "int"),
            ("phone_folder", "Folder where phone photos arrive", settings["phone_folder"], "str"),
            ("lasergrbl", "LaserGRBL.exe", settings["lasergrbl"], "str"),
            ("pulses", "Dot flashes per corner (perimeter check)", settings["pulses"], "int"),
            ("perimeter_feed", "Perimeter travel speed (mm/min)", settings["perimeter_feed"], "int"),
            ("perimeter_spacing", "Extra edge dots every N mm (0 = corners only)", settings["perimeter_spacing"],
             "float"),
        ], intro="Machine: Tronxy Ultrabot U20 (MKS DLC32, Grbl 1.1h). The app checks $30=1000, $31=0, $32=1 and "
                 "$100/$101=100 before any laser output, and never homes.", ok_text="Save")


class RecoveryDialog(tk.Toplevel):
    """Resume after a USB dropout or stop - the brief's recovery, step by step, never homing."""

    def __init__(self, app, folder, state: dict):
        super().__init__(app.root)
        self.app, self.folder, self.state = app, folder, state
        self.res = state.get("resume") or {}
        self.kept = bool(self.res.get("kept_position"))
        self.point = tuple(self.res.get("expected_start", (0.0, 0.0)))
        self.title("Resume the job")
        self.transient(app.root)
        # The recovery checklist can be taller than a laptop screen. Cap the window
        # to the visible display and keep the action buttons outside the scroller.
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(600, max(240, sw - 80))
        height = min(600, max(220, sh - 120))
        self.geometry(f"{width}x{height}")
        self.minsize(min(width, 340), min(height, 260))
        self.resizable(True, True)
        self.declared = False
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Resume the job", style="H1.TLabel").pack(anchor="w")
        scroller = ScrollFrame(shell)
        scroller.pack(fill="both", expand=True, pady=(6, 0))
        f = scroller.inner
        job = jobs.read_json(folder / "job.json", {}) or {}
        npass = len(job.get("passes", []))
        pi = int(self.res.get("start_pass", 0))
        ptitle = job.get("passes", [{}] * (pi + 1))[pi].get("title", f"pass {pi + 1}") if pi < npass else "end"
        wrap_label(f, state.get("message", ""), width=500).pack(anchor="w", pady=(4, 6))
        wrap_label(f, f"It will continue {ptitle} ({pi + 1} of {npass}) from where it stopped, without burning "
                      f"anything twice. Stop point: X {self.point[0]:.2f}, Y {self.point[1]:.2f} mm.",
                   width=500).pack(anchor="w")
        self.steps = ttk.Frame(f)
        self.steps.pack(fill="x", pady=(10, 0))
        s1 = ttk.LabelFrame(self.steps, text="1. Connect", style="Card.TLabelframe")
        s1.pack(fill="x", pady=4)
        wrap_label(s1, "Plug the USB back in. If Windows says the device isn't working, switch the laser off and "
                       "on, then connect. Don't move the head.", width=470).pack(anchor="w")
        row = ttk.Frame(s1)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Connect", command=self.app.connect).pack(side="left")
        ttk.Button(row, text="Unlock ($X, no movement)", command=self.app.unlock).pack(side="left", padx=6)
        self.conn = ttk.Label(s1, style="Muted.TLabel")
        self.conn.pack(anchor="w", pady=(4, 0))
        s2 = ttk.LabelFrame(self.steps, text="2. Tell the controller where the head is", style="Card.TLabelframe")
        s2.pack(fill="x", pady=4)
        txt = ("The job stopped cleanly, so the controller still knows its position. If it shows the stop point "
               "below, skip to step 3." if self.kept else
               "A replug restarts the controller and it forgets where the head is. The head stopped at the end of "
               "the last command sent, so declare that point (this never moves the head).")
        wrap_label(s2, txt, width=470).pack(anchor="w")
        ttk.Button(s2, text=f"The head is at the stop point (X {self.point[0]:.2f}, Y {self.point[1]:.2f})",
                   command=self.declare).pack(anchor="w", pady=(6, 0))
        s3 = ttk.LabelFrame(self.steps, text="3. Check with the 1% dot", style="Card.TLabelframe")
        s3.pack(fill="x", pady=4)
        wrap_label(s3, "Turn the dot on. It should sit right at the end of the last burned line. If it's off, nudge "
                       "the head until it is, then press 'Dot is on the spot'.", width=470).pack(anchor="w")
        row = ttk.Frame(s3)
        row.pack(fill="x", pady=(6, 0))
        self.dot_btn = ttk.Button(row, text="Dot on", command=self.app.toggle_dot)
        self.dot_btn.pack(side="left")
        self.step = tk.DoubleVar(value=0.1)
        for t, dx, dy in (("<", -1, 0), (">", 1, 0), ("^", 0, 1), ("v", 0, -1)):
            ttk.Button(row, text=t, width=3, style="Tool.TButton",
                       command=lambda dx=dx, dy=dy: self.app.jog(dx * self.step.get(), dy * self.step.get())
                       ).pack(side="left", padx=1)
        ttk.Combobox(row, textvariable=self.step, values=[0.1, 0.2, 0.5, 1.0], width=5, state="readonly").pack(
            side="left", padx=4)
        ttk.Label(row, text="mm").pack(side="left")
        ttk.Button(s3, text="Dot is on the spot - declare it as the stop point", command=self.declare).pack(
            anchor="w", pady=(6, 0))
        self.pos = ttk.Label(s3, style="Muted.TLabel")
        self.pos.pack(anchor="w", pady=(4, 0))
        s4 = ttk.LabelFrame(self.steps, text="4. Continue", style="Card.TLabelframe")
        s4.pack(fill="x", pady=4)
        self.pause = tk.BooleanVar(value=bool(app.settings.get("pause_between_layers", True)))
        ttk.Checkbutton(s4, text="Pause after each remaining layer for a photo", variable=self.pause).pack(anchor="w")
        # Fixed footer stays visible even when the recovery instructions scroll.
        bar = ttk.Frame(shell)
        bar.pack(fill="x", pady=(8, 0))
        self.go = ttk.Button(bar, text="Resume engraving", style="Big.TButton", command=self.resume)
        self.go.pack(side="left")
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        app.event_hooks.append(self.on_event)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def close(self):
        if self.on_event in self.app.event_hooks:
            self.app.event_hooks.remove(self.on_event)
        self.app.dot_off()
        self.destroy()

    def declare(self):
        if not self.app.connected:
            messagebox.showinfo("Connect first", "Connect to the laser first (step 1).", parent=self)
            return
        self.app.worker.submit("declare", machine.set_origin_here, self.point[0], self.point[1])

    def on_event(self, ev):
        if ev[0] == "done" and ev[1] == "declare":
            self.declared = True
        if ev[0] == "dot":
            self.dot_btn.configure(text="Dot off" if ev[1] else "Dot on")
        self.refresh()

    def at_point(self):
        st = self.app.last_status
        return bool(st and st.wpos and abs(st.wpos[0] - self.point[0]) < 0.05 and abs(st.wpos[1] - self.point[1]) < 0.05)

    def refresh(self):
        if not self.winfo_exists():
            return
        st = self.app.last_status
        if self.app.connected:
            self.conn.configure(text=f"Connected: {st.state if st else '...'}" +
                                (" - locked: press Unlock" if st and st.state == "Alarm" else ""))
        else:
            self.conn.configure(text="Not connected.")
        if st and st.wpos:
            ok = self.at_point()
            self.pos.configure(text=f"Controller says the head is at X {st.wpos[0]:.2f}, Y {st.wpos[1]:.2f}"
                                    + ("  - matches the stop point" if ok else ""))
        ready = self.app.connected and st is not None and st.state == "Idle" and self.at_point()
        self.go.state(["!disabled"] if ready else ["disabled"])

    def resume(self):
        if not messagebox.askokcancel("Resume", "Did the 1% dot sit on the end of the last burned line?\n\n"
                                                "Resume engraving now?", parent=self):
            return
        spec = dict(self.res)
        spec.pop("kept_position", None)
        spec.update(pause_between=self.pause.get(), park=[0.0, 0.0], completed=self.state.get("completed", []))
        self.close()
        self.app.launch(self.folder, spec)
