"""Step 5: connect, origin, 1% dot, perimeter check, start, live progress, photos and recovery."""
from __future__ import annotations

import datetime as dt
import math
import os
import shutil
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import gcodeinfo, imaging, jobs, machine, planner
from .dialogs import RecoveryDialog, StartDialog
from .presets import DATA_DIR
from .preview import fmt_dur
from .ui_common import COLORS, link, wrap_label
from .worker import MachineWorker

DEMO_STATE = DATA_DIR / "demo-state.json"
LIVE = ("starting", "connecting", "running", "paused", "stopping", "waiting_photo")
PHASE_TEXT = dict(starting="Starting", connecting="Connecting", running="Engraving", paused="Paused",
                  stopping="Stopping after this row", waiting_photo="Waiting for your photo", complete="Finished",
                  stopped="Stopped - position kept", dropout="USB dropped out", fault="Stopped by a problem")


class LaserMixin:
    def init_machine_state(self):
        self.worker = None
        self.connected = False
        self.last_status = None
        self.origin_set = False
        self.dot_on = False
        self.perim_running = False
        self.active_folder = None
        self.run_state = None
        self.photo_seen = set()
        self.photo_baseline = 0.0
        self.port_var = tk.StringVar(value=self.settings["port"])
        self.demo = tk.BooleanVar(value=False)

    # ================================================================ page
    def page_laser(self, f):
        ttk.Label(f, text="5. Laser", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Connect, set the origin, check the perimeter with the 1% dot, then start. Jobs run in the "
                      "background, so closing this window doesn't stop the laser.", style="Muted.TLabel").pack(
            anchor="w", pady=(2, 8))
        c = ttk.LabelFrame(f, text="Connect", style="Card.TLabelframe")
        c.pack(fill="x", pady=4)
        row = ttk.Frame(c)
        row.pack(fill="x")
        ttk.Combobox(row, textvariable=self.port_var, width=8,
                     values=[p for p, _ in machine.list_ports()] or ["COM4"]).pack(side="left")
        self.btn_conn = ttk.Button(row, text="Connect", command=self.connect)
        self.btn_conn.pack(side="left", padx=6)
        ttk.Button(row, text="Disconnect", command=self.disconnect).pack(side="left")
        ttk.Checkbutton(c, text="Demo mode (simulated laser - nothing moves)", variable=self.demo).pack(anchor="w",
                                                                                                    pady=(6, 0))
        self.conn_lbl = wrap_label(c, "Not connected.", style="Muted.TLabel")
        self.conn_lbl.pack(anchor="w", pady=(4, 0))
        self.btn_unlock = ttk.Button(c, text="Unlock ($X - doesn't move anything)", command=self.unlock)
        o = ttk.LabelFrame(f, text="Origin (laser off)", style="Card.TLabelframe")
        o.pack(fill="x", pady=4)
        self.pos_lbl = tk.Label(o, text="X --   Y --", font=("Consolas", 13, "bold"), fg=COLORS["ink"])
        self.pos_lbl.pack(anchor="w")
        self.origin_help = wrap_label(o, "", style="Small.TLabel")
        self.origin_help.pack(anchor="w", pady=(2, 6))
        jr = ttk.Frame(o)
        jr.pack(anchor="w")
        self.jog_step = tk.StringVar(value="1")
        for t, dx, dy, r, cc in (("Up", 0, 1, 0, 1), ("Left", -1, 0, 1, 0), ("Right", 1, 0, 1, 2), ("Down", 0, -1, 2, 1)):
            ttk.Button(jr, text=t, width=6, command=lambda dx=dx, dy=dy: self.jog(dx * float(self.jog_step.get()),
                                                                                 dy * float(self.jog_step.get()))
                       ).grid(row=r, column=cc)
        self.btn_dot = ttk.Button(jr, text="Dot on (1%)", width=12, command=self.toggle_dot)
        self.btn_dot.grid(row=1, column=1)
        ttk.Label(jr, text="  step").grid(row=1, column=3)
        ttk.Combobox(jr, textvariable=self.jog_step, values=["0.1", "0.5", "1", "5", "10", "50"], width=4,
                     state="readonly").grid(row=1, column=4)
        ttk.Label(jr, text="mm").grid(row=1, column=5)
        orow = ttk.Frame(o)
        orow.pack(anchor="w", pady=(8, 0))
        ttk.Button(orow, text="Set origin here", command=self.set_origin).pack(side="left")
        ttk.Button(orow, text="Go to origin", command=self.go_origin).pack(side="left", padx=6)
        p = ttk.LabelFrame(f, text="Perimeter check (1% dot)", style="Card.TLabelframe")
        p.pack(fill="x", pady=4)
        wrap_label(p, "The head visits each corner of the burn area with the laser off and flashes your 1% "
                      "positioning dot there (S10, same safety checks as the Positioning Laser app), then returns "
                      "to the origin.", style="Small.TLabel").pack(anchor="w")
        link(p, "How the origin and perimeter check work",
             lambda: self.open_help("Origin & perimeter check")).pack(anchor="w", pady=(2, 0))
        pr = ttk.Frame(p)
        pr.pack(fill="x", pady=(6, 0))
        ttk.Label(pr, text="Flashes per corner").pack(side="left")
        self.pulses_var = tk.StringVar(value=str(self.settings.get("pulses", 3)))
        ttk.Spinbox(pr, from_=1, to=6, width=3, textvariable=self.pulses_var).pack(side="left", padx=(4, 10))
        ttk.Label(pr, text="Edge dots every").pack(side="left")
        sp = self.settings.get("perimeter_spacing", 0) or 0
        self.spacing_var = tk.StringVar(value="corners only" if not sp else f"{sp:g} mm")
        ttk.Combobox(pr, textvariable=self.spacing_var, width=12, state="readonly",
                     values=["corners only", "10 mm", "20 mm", "40 mm"]).pack(side="left", padx=4)
        br = ttk.Frame(p)
        br.pack(fill="x", pady=(8, 0))
        self.btn_perim = ttk.Button(br, text="Run perimeter check", style="Big.TButton", command=self.run_perimeter)
        self.btn_perim.pack(side="left")
        ttk.Button(br, text="Stop", command=self.stop_perimeter).pack(side="left", padx=6)
        self.perim_lbl = wrap_label(p, "", style="Muted.TLabel")
        self.perim_lbl.pack(anchor="w", pady=(4, 0))
        ttk.Label(p, text="Off by a bit? Move the art, then check again:").pack(anchor="w", pady=(8, 2))
        self._nudge_pad(p, self.nudge)
        gr = ttk.Frame(p)
        gr.pack(fill="x", pady=(8, 0))
        ttk.Button(gr, text="Check a G-code file instead...", command=lambda: self.perimeter_mode(None)).pack(
            side="left")
        ttk.Button(gr, text="Back to my picture job", command=self.clear_gfile).pack(side="left", padx=6)
        self.gfile_lbl = wrap_label(p, "", style="Small.TLabel")
        self.gfile_lbl.pack(anchor="w", pady=(4, 0))
        e = ttk.LabelFrame(f, text="Engrave", style="Card.TLabelframe")
        e.pack(fill="x", pady=4)
        self.engrave_lbl = wrap_label(e, "")
        self.engrave_lbl.pack(anchor="w")
        self.btn_start = ttk.Button(e, text="Start engraving", style="Big.TButton", command=self.start_engraving)
        self.btn_start.pack(anchor="w", pady=(8, 0))
        m = ttk.LabelFrame(f, text="Job progress", style="Card.TLabelframe")
        m.pack(fill="x", pady=4)
        self.run_title = ttk.Label(m, text="No job running.", style="H2.TLabel")
        self.run_title.pack(anchor="w")
        self.run_bar = ttk.Progressbar(m, maximum=100)
        self.run_bar.pack(fill="x", pady=4)
        self.laser_lbl = tk.Label(m, text=" laser off ", bg="#dcfce7", fg="#166534", font=("Segoe UI", 10, "bold"))
        self.laser_lbl.pack(anchor="w")
        self.run_lbl = wrap_label(m, "", style="Muted.TLabel")
        self.run_lbl.pack(anchor="w", pady=(4, 0))
        cr = ttk.Frame(m)
        cr.pack(fill="x", pady=(6, 0))
        self.btn_pause = ttk.Button(cr, text="Pause", command=lambda: self.control("pause"))
        self.btn_resume = ttk.Button(cr, text="Resume", command=lambda: self.control("resume"))
        self.btn_stop = ttk.Button(cr, text="Stop after this row", command=lambda: self.control("stop"))
        for b in (self.btn_pause, self.btn_resume, self.btn_stop):
            b.pack(side="left", padx=(0, 4))
        self.btn_estop = tk.Button(m, text="EMERGENCY STOP", bg="#b91c1c", fg="white", activebackground="#7f1d1d",
                                   font=("Segoe UI", 11, "bold"), relief="flat", padx=12, pady=4,
                                   command=lambda: self.control("estop"))
        self.btn_estop.pack(anchor="w", pady=(6, 0))
        self.photo_box = ttk.Frame(m)
        self.photo_lbl = wrap_label(self.photo_box, "")
        self.photo_lbl.pack(anchor="w")
        pb = ttk.Frame(self.photo_box)
        pb.pack(anchor="w", pady=(4, 0))
        self.btn_continue = ttk.Button(pb, text="Continue with the next layer", style="Big.TButton",
                                       command=lambda: self.control("continue"))
        self.btn_continue.pack(side="left")
        ttk.Button(pb, text="Open photos folder", command=self.open_photos).pack(side="left", padx=6)
        self.btn_recover = ttk.Button(m, text="Resume the job...", style="Big.TButton", command=self.open_recovery)
        ttk.Button(m, text="Open job folder", command=self.open_job_folder).pack(anchor="w", pady=(6, 0))
        link(m, "If the USB drops out", lambda: self.open_help("USB dropouts")).pack(anchor="w", pady=(6, 0))

    def start_laser_loops(self):
        latest = jobs.latest_jobs(1)
        if latest and not jobs.active_runner():
            st = jobs.read_json(latest[0] / "state.json")
            if st and st.get("phase") in ("dropout", "fault", "stopped") and st.get("resume"):
                self.active_folder = latest[0]
                self.say(f"Your last job ({st.get('job')}) stopped before finishing. Step 5 can resume it.", "warn")
        self.root.after(300, self._poll_runner)
        self.root.after(3000, self._scan_photos)
        self.refresh_laser_page()

    # ================================================================ connection
    def connect(self):
        if self.worker is not None:
            return
        if jobs.active_runner():
            messagebox.showinfo("A job is running", "A job is running in the background and owns the laser. Use the "
                                                    "Job progress buttons, or wait until it finishes.")
            return
        demo = self.demo.get()
        if not demo:
            others = jobs.running_processes()
            if others and not messagebox.askyesno(
                    "One program at a time", f"{', '.join(others)} is open. Only one program can use the laser at a "
                                             "time - close it (or turn the Positioning Laser OFF) first.\n\n"
                                             "Try to connect anyway?"):
                return
        self.settings["port"] = self.port_var.get() or "COM4"
        jobs.save_settings(self.settings)
        self.worker = MachineWorker(self.events, self.settings["port"], int(self.settings["baud"]), demo,
                                    jobs.read_json(DEMO_STATE, {}) if demo else None)
        self.worker.start()
        self.conn_lbl.configure(text="Connecting...")

    def disconnect(self, wait=False):
        w = self.worker
        if w is None:
            return
        w.stop()
        if wait:
            w.join(5)
            while not self.events.empty():
                self._event(self.events.get_nowait())

    def unlock(self):
        if self.need_connection() and messagebox.askyesno(
                "Unlock", "Unlock the controller with $X? It doesn't move anything.\n\nNever use Home on this "
                          "machine - it has no homing switches."):
            self.worker.submit("unlock", lambda g: g.command("$X"))

    def need_connection(self):
        if not self.connected:
            messagebox.showinfo("Not connected", "Connect to the laser first (top of step 5).")
            return False
        return True

    def toggle_dot(self):
        if self.need_connection():
            self.worker.dot(not self.dot_on)

    def dot_off(self):
        if self.worker is not None and self.dot_on:
            self.worker.dot(False)

    def jog(self, dx, dy):
        if self.need_connection():
            self.worker.submit("dot_jog" if self.dot_on else "jog", machine.jog, dx, dy, 1000)

    def origin_words(self):
        pc = self.job.piece if self.job is not None else self.piece
        return "centre of the piece" if pc.get("origin") == "center" else "lower-left corner of the piece"

    def set_origin(self):
        if self.need_connection() and messagebox.askyesno(
                "Set origin", f"Is the laser head exactly over the {self.origin_words()}?\n\n(Use the 1% dot to "
                              "check.) This makes the current spot X0 Y0. It doesn't move anything."):
            self.worker.submit("origin", machine.set_origin_here, 0.0, 0.0)

    def go_origin(self):
        if self.need_connection():
            self.worker.submit("goto", machine.move_off, 0.0, 0.0, 3000)

    # ================================================================ events
    def machine_event(self, ev):
        kind = ev[0]
        if kind == "connected":
            info = ev[1]
            self.connected = True
            self.origin_set = False
            probs = info.get("settings_problems") or []
            txt = ("Demo laser connected." if self.demo.get() else f"Connected on {self.settings['port']}.")
            if info.get("alarm"):
                txt += " The controller is locked (alarm): press Unlock. Never Home."
                self.btn_unlock.pack(anchor="w", pady=(6, 0))
            elif probs:
                txt += " WARNING - settings differ: " + ", ".join(probs) + ". The laser won't be used."
            else:
                txt += " Settings OK ($30=1000, $31=0, $32=1, 100 steps/mm)."
            if info.get("rebooted"):
                txt += " The controller restarted when connecting, so set the origin again."
            self.conn_lbl.configure(text=txt, foreground=COLORS["bad"] if probs else COLORS["ok"])
            self.say(txt, "warn" if probs or info.get("rebooted") else "ok")
        elif kind == "status":
            self.last_status = ev[1]
            st = ev[1]
            if st.wpos:
                self.pos_lbl.configure(text=f"X {st.wpos[0]:.2f}   Y {st.wpos[1]:.2f}   ({st.state})")
            if st.state != "Alarm":
                self.btn_unlock.pack_forget()
            self.preview.draw_head()
        elif kind == "dot":
            self.dot_on = bool(ev[1])
            self.btn_dot.configure(text="Dot OFF" if self.dot_on else "Dot on (1%)")
        elif kind == "done":
            name = ev[1]
            if name in ("origin", "declare"):
                self.origin_set = True
                self.say("Origin set: this spot is now X0 Y0." if name == "origin" else
                         "Position declared at the stop point.", "ok")
            elif name == "perimeter":
                self.perim_running = False
                self.perim_idx = None
                self.perim_lbl.configure(text="Done - head is back at the origin. Happy with the corners? Start "
                                              "engraving. Off a little? Nudge the art and check again.")
                self.preview.refresh()
            elif name == "unlock":
                self.say("Unlocked. The position may be unknown - set or declare it before burning.", "warn")
                self.btn_unlock.pack_forget()
        elif kind == "failed":
            name, msg = ev[1], ev[2]
            if name == "perimeter":
                self.perim_running = False
                self.perim_idx = None
                self.perim_lbl.configure(text=("Stopped - head returned to the origin." if "cancel" in msg
                                               else f"Stopped: {msg}"))
                self.preview.refresh()
            else:
                messagebox.showwarning("Laser", msg)
        elif kind == "perim":
            _, i, n, name, what = ev
            self.perim_idx = i if i < n else None
            self.perim_lbl.configure(text=f"Point {min(i + 1, n)} of {n} ({name}): "
                                          + {"moving": "moving there, laser off...", "dot": "flashing the 1% dot",
                                             "done": "returning to origin"}[what])
            self.preview.redraw()
        elif kind == "rebooted":
            self.origin_set = False
            self.say(ev[1] + " Set or declare the origin again before burning.", "bad")
        elif kind == "error":
            self.say(ev[1], "bad")
        elif kind == "link_lost":
            self.say(f"Laser connection lost: {ev[1]}", "bad")
            self.conn_lbl.configure(text=f"Disconnected: {ev[1]}", foreground=COLORS["bad"])
        elif kind == "disconnected":
            if ev[1] is not None:
                jobs.write_json(DEMO_STATE, ev[1])
            self.worker = None
            self.connected = False
            self.dot_on = False
            self.last_status = None
            self.btn_dot.configure(text="Dot on (1%)")
            self.pos_lbl.configure(text="X --   Y --")
            if "Disconnected" not in str(self.conn_lbl.cget("text")):
                self.conn_lbl.configure(text="Not connected.", foreground=COLORS["muted"])
            self.preview.draw_head()
        self.refresh_laser_page()

    def head_position(self):
        rs = self.run_state
        if rs and rs.get("phase") in LIVE and rs.get("wpos"):
            return rs["wpos"]
        st = self.last_status
        return st.wpos[:2] if st and st.wpos else None

    def laser_is_on(self):
        rs = self.run_state
        if rs and rs.get("phase") in LIVE and rs.get("laser_on"):
            return True
        return bool(self.last_status and self.last_status.laser_on) or self.dot_on

    def refresh_laser_page(self):
        if not hasattr(self, "pill"):
            return
        rs = self.run_state
        live = bool(rs and rs.get("phase") in LIVE and jobs.active_runner())
        if live:
            on = rs.get("laser_on")
            self.pill.configure(text=f" {'LASER ON - ' if on else ''}Job: {PHASE_TEXT.get(rs['phase'], rs['phase'])} "
                                     f"{int(100 * rs.get('progress', 0))}% ",
                                bg=COLORS["bad"] if on else "#c2410c")
        elif self.connected:
            st = self.last_status
            pos = f" X {st.wpos[0]:.1f} Y {st.wpos[1]:.1f}" if st and st.wpos else ""
            demo = "Demo laser" if self.demo.get() else "Connected"
            self.pill.configure(text=f" {'LASER ON (dot) - ' if self.dot_on else ''}{demo} - "
                                     f"{st.state if st else '...'}{pos} ",
                                bg=COLORS["bad"] if self.dot_on else COLORS["ok"])
        else:
            self.pill.configure(text=" Not connected ", bg="#6b7280")
        self.origin_help.configure(text=f"Move the head over the {self.origin_words()} (use the dot to see exactly "
                                        "where the beam is), then press 'Set origin here'."
                                        + ("  Origin set." if self.origin_set else ""))
        job = self.job
        if self.gfile:
            self.engrave_lbl.configure(text="Checking a G-code file. To burn it, open it in LaserGRBL; this app "
                                            "burns the jobs it made and checked itself.")
            self.btn_start.state(["disabled"])
        elif job is None:
            self.engrave_lbl.configure(text="Open a picture first (step 1).")
            self.btn_start.state(["disabled"])
        else:
            ok = bool(self.report and self.report["ok"] and self.compiled_gen == self.gen)
            self.engrave_lbl.configure(text=f"{job.name}: {len(job.passes)} pass(es), {job.burn_cells:,} dots"
                                            + (f", about {fmt_dur(job.est_s)}." if ok else " - not checked yet."))
            self.btn_start.state(["!disabled"] if ok and not live else ["disabled"])

    # ================================================================ perimeter
    def perimeter_mode(self, path):
        path = path or filedialog.askopenfilename(title="G-code file to check", filetypes=[
            ("G-code", "*.nc *.gcode *.gc *.ngc *.tap *.txt"), ("All files", "*.*")])
        if not path:
            self.goto(4)
            return
        info = gcodeinfo.analyse(path)
        if not info["burn_bbox"]:
            messagebox.showerror("Nothing to check", "No burning moves found in that file.")
            return
        info.update(name=Path(path).name, path=str(path))
        self.gfile = info
        self.perim_points = []
        b = info["burn_bbox"]
        warn = ("  WARNING: " + "; ".join(info["warnings"])) if info["warnings"] else ""
        self.gfile_lbl.configure(text=f"{info['name']}: burns X {b[0]:.2f}..{b[2]:.2f}, Y {b[1]:.2f}..{b[3]:.2f} mm, "
                                      f"max power S{info['max_s']:g}.{warn}")
        self.preview.refresh()
        self.goto(4)
        self.refresh_laser_page()
        self.say("G-code loaded. Connect, set the origin the file expects, then Run perimeter check.", "ok")

    def clear_gfile(self):
        self.gfile = None
        self.gfile_lbl.configure(text="")
        self.perim_points = []
        self.preview.refresh()
        self.refresh_laser_page()

    def run_perimeter(self):
        if not self.need_connection() or self.perim_running:
            return
        bbox = self.gfile["burn_bbox"] if self.gfile else (self.job.burn_bbox() if self.job is not None else None)
        if not bbox:
            messagebox.showinfo("Nothing to check", "Open a picture (or a G-code file) first.")
            return
        if not self.origin_set and not messagebox.askyesno(
                "Origin", "You haven't set the origin since connecting. The check uses the controller's current "
                          "X0 Y0. Continue anyway?"):
            return
        spacing = self.spacing_var.get()
        spacing = None if spacing.startswith("corners") else float(spacing.split()[0])
        pulses = max(1, min(6, int(float(self.pulses_var.get() or 3))))
        pts = planner.perimeter_points(bbox, spacing)
        self.perim_points = pts
        self.preview.redraw()
        if not messagebox.askokcancel(
                "Perimeter check", f"Watch the laser now.\n\nThe head will move with the laser OFF to {len(pts)} "
                                   f"points and flash the 1% dot {pulses}x at each, then return to the origin.\n\n"
                                   "Ready?"):
            return
        self.settings.update(pulses=pulses, perimeter_spacing=spacing or 0)
        jobs.save_settings(self.settings)
        self.perim_running = True
        feed = int(self.settings.get("perimeter_feed", 1500))
        events = self.events
        self.worker.submit("perimeter", machine.perimeter_check, pts, pulses, feed, cancel=self.worker.cancel,
                           progress=lambda i, n, name, what: events.put(("perim", i, n, name, what)))

    def stop_perimeter(self):
        if self.worker is not None:
            self.worker.cancel.set()
            self.dot_off()

    # ================================================================ start / monitor
    def start_engraving(self):
        if jobs.active_runner():
            messagebox.showinfo("Busy", "A job is already running.")
            return
        folder = self.save_current_job(quiet=True)
        if not folder:
            messagebox.showinfo("Check first", "The job needs to pass the check (step 4) first.")
            return
        if not self.need_connection():
            return
        st = self.last_status
        if st is None or st.state != "Idle":
            messagebox.showinfo("Not ready", f"The machine is {st.state if st else 'not reporting'}; it must be Idle.")
            return
        if not st.wpos or math.hypot(st.wpos[0], st.wpos[1]) > 0.05:
            if messagebox.askyesno("Head not at the origin", "The job starts from the origin (X0 Y0). Move the head "
                                                             "there now with the laser off?"):
                self.go_origin()
            return
        if not self.origin_set and not messagebox.askyesno(
                "Origin", f"You haven't set the origin since connecting. Is the head really over the "
                          f"{self.origin_words()}?"):
            return
        job, m = self.job, self.job.material
        summary = (f"{job.name}\nMaterial: {m.name}\n{len(job.passes)} pass(es): "
                   + ", ".join(p.title for p in job.passes) +
                   f"\n{job.burn_cells:,} dots, about {fmt_dur(job.est_s)} of laser time.")
        d = StartDialog(self.root, summary, bool(self.settings.get("pause_between_layers", True)),
                        len(job.passes) > 1).result
        if not d:
            return
        self.settings["pause_between_layers"] = d["pause_between"]
        jobs.save_settings(self.settings)
        self.launch(folder, dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0],
                                 pause_between=d["pause_between"], park=[0.0, 0.0], completed=[]))

    def launch(self, folder, spec):
        if jobs.active_runner():
            messagebox.showerror("Busy", "Another job is already running.")
            return
        spec = dict(spec)
        spec.update(port=self.settings["port"], baud=int(self.settings["baud"]), demo=bool(self.demo.get()))
        if self.worker is not None:
            self.disconnect(wait=True)
        if spec["demo"]:
            spec["demo_state"] = jobs.read_json(DEMO_STATE, {}) or {}
        pid = jobs.launch_runner(Path(folder), spec)
        self.active_folder = Path(folder)
        self.run_state = None
        self.photo_baseline = time.time()
        self.photo_seen = set()
        self.perim_points = []
        self.goto(4)
        self.say(f"Job started (background process {pid}). You can close this window; it keeps running.", "ok")

    def control(self, cmd):
        if self.active_folder is None:
            return
        jobs.send_control(self.active_folder, cmd)
        self.say({"pause": "Pausing...", "resume": "Resuming...", "stop": "Stopping after this row...",
                  "estop": "EMERGENCY STOP sent.", "continue": "Continuing with the next layer..."}[cmd],
                 "bad" if cmd == "estop" else "info")

    def _poll_runner(self):
        try:
            info = jobs.active_runner()
            if info and (self.active_folder is None or Path(info["job"]) != self.active_folder):
                self.active_folder = Path(info["job"])
            if self.active_folder is not None:
                st = jobs.read_json(self.active_folder / "state.json")
                if st:
                    self._show_run(st, bool(info))
        finally:
            self.root.after(500, self._poll_runner)

    def _show_run(self, st, alive):
        prev = (self.run_state or {}).get("phase")
        self.run_state = st
        ph = st.get("phase", "")
        if not alive and ph in LIVE:
            ph = "fault"
            st = dict(st, phase="fault", message="The job process ended unexpectedly. " + st.get("message", ""))
        self.run_title.configure(text=f"{st.get('job', '')}: {PHASE_TEXT.get(ph, ph)}")
        self.run_bar.configure(value=100 * float(st.get("progress", 0)))
        bits = []
        if st.get("pass_title"):
            bits.append(f"{st['pass_title']} ({st.get('pass_index', 0) + 1} of {st.get('pass_count', 1)})")
        bits.append(f"{100 * float(st.get('progress', 0)):.0f}% done")
        if st.get("remaining_s") is not None and ph in LIVE:
            bits.append(f"about {fmt_dur(st['remaining_s'])} left")
        if st.get("wpos"):
            bits.append(f"head X {st['wpos'][0]:.1f} Y {st['wpos'][1]:.1f}")
        self.run_lbl.configure(text="  |  ".join(bits) + "\n" + st.get("message", ""))
        on = bool(st.get("laser_on")) and ph in LIVE
        self.laser_lbl.configure(text=" LASER ON " if on else " laser off ", bg="#fee2e2" if on else "#dcfce7",
                                 fg="#991b1b" if on else "#166534")
        for b, ok in ((self.btn_pause, alive and ph == "running"), (self.btn_resume, alive and ph == "paused"),
                      (self.btn_stop, alive and ph in ("running", "paused", "waiting_photo"))):
            b.state(["!disabled"] if ok else ["disabled"])
        self.btn_estop.configure(state="normal" if alive else "disabled")
        if ph in ("waiting_photo", "complete"):
            n = len(list((self.active_folder / "photos").glob("*"))) if self.active_folder else 0
            self.photo_lbl.configure(text=("Take your photo now - the head is parked and the laser is off. "
                                           if ph == "waiting_photo" else "Finished! Take a final photo. ")
                                          + f"Photos from your phone are saved to the job automatically ({n} so far).")
            self.btn_continue.state(["!disabled"] if ph == "waiting_photo" else ["disabled"])
            self.photo_box.pack(fill="x", pady=(8, 0))
        else:
            self.photo_box.pack_forget()
        if not alive and ph in ("dropout", "fault", "stopped") and st.get("resume"):
            self.btn_recover.pack(anchor="w", pady=(8, 0))
        else:
            self.btn_recover.pack_forget()
        if ph != prev and ph in ("dropout", "fault"):
            self.say(st.get("message", ""), "bad")
            self.goto(4)
        if ph != prev and ph == "complete":
            self.say("Job finished. Laser off, head parked at the origin.", "ok")
        self.preview.draw_head()
        self.refresh_laser_page()

    def open_recovery(self):
        if self.active_folder is None or not self.run_state:
            return
        RecoveryDialog(self, self.active_folder, self.run_state)

    def open_job_folder(self):
        folder = self.active_folder or self.saved.get(self.gen)
        if folder:
            os.startfile(str(folder))

    def open_photos(self):
        if self.active_folder:
            os.startfile(str(self.active_folder / "photos"))

    def _scan_photos(self):
        try:
            st = self.run_state
            if self.active_folder and st and st.get("phase") in ("waiting_photo", "complete"):
                src = Path(self.settings.get("phone_folder", ""))
                since = st.get("photo_wait_since") or st.get("updated")
                t0 = max(self.photo_baseline, dt.datetime.fromisoformat(since).timestamp() - 5) if since else \
                    self.photo_baseline
                if src.exists():
                    label = st.get("pass_key", "final") if st.get("phase") == "waiting_photo" else "final"
                    n = st.get("pass_index", 0) + 1
                    for p in src.iterdir():
                        if p.suffix.lower() in imaging.PICTURE_TYPES and p.name not in self.photo_seen and \
                                p.stat().st_mtime >= t0:
                            dest = self.active_folder / "photos" / f"{n:02d}-after-{label}-{p.name}"
                            shutil.copy2(p, dest)
                            self.photo_seen.add(p.name)
                            self.say(f"Saved photo {p.name} to the job.", "ok")
        except Exception as e:  # never let photo copying disturb anything else
            self.say(f"Photo copy skipped: {e}", "warn")
        finally:
            self.root.after(3000, self._scan_photos)
