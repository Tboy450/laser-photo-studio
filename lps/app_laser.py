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
from .ui_common import COLORS, ToolTip, link, moves_note, wrap_label
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
        self.origin_count = 0          # goes up each time a start point is set, so old perimeter checks expire
        self.perim_checked = None      # (burn box, origin_count) of the last finished perimeter check
        self._bbox_cache = (None, None)
        self._ready_shown = None
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
        wrap_label(f, "Connect, set the start point, check the perimeter with the 1% dot, then start. Jobs run in the "
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
        ToolTip(self.btn_unlock, "Clears the controller's alarm lock so it accepts commands again. Nothing moves, "
                                 "and it doesn't home. The position may be unknown afterwards: set the start point "
                                 "again.")
        o = ttk.LabelFrame(f, text="Move the laser head and set the start point", style="Card.TLabelframe")
        o.pack(fill="x", pady=4)
        moves_note(o, COLORS["head"], "These buttons move the real laser head (purple marker), laser off.").pack(
            fill="x", pady=(0, 4))
        self.pos_lbl = tk.Label(o, text="X --   Y --", font=("Consolas", 13, "bold"), fg=COLORS["ink"])
        self.pos_lbl.pack(anchor="w")
        ToolTip(self.pos_lbl, "Where the controller thinks the head is, in mm from the start point. It only "
                              "matches the real spot after you set the start point (and again after a USB "
                              "dropout).")
        self.origin_help = wrap_label(o, "", style="Small.TLabel")
        self.origin_help.pack(anchor="w", pady=(2, 6))
        jr = ttk.Frame(o)
        jr.pack(anchor="w")
        self.jog_step = tk.StringVar(value="1")
        for t, dx, dy, r, cc in (("Up", 0, 1, 0, 1), ("Left", -1, 0, 1, 0), ("Right", 1, 0, 1, 2), ("Down", 0, -1, 2, 1)):
            b = ttk.Button(jr, text=t, width=6, command=lambda dx=dx, dy=dy: self.jog(dx * float(self.jog_step.get()),
                                                                                     dy * float(self.jog_step.get())))
            b.grid(row=r, column=cc)
            ToolTip(b, f"The head moves {t.lower()} by the step, laser off (the 1% dot stays on if it's on). The "
                       "picture stays where it is on the piece.")
        self.btn_dot = ttk.Button(jr, text="Dot on (1%)", width=12, command=self.toggle_dot)
        self.btn_dot.grid(row=1, column=1)
        ToolTip(self.btn_dot, "Turns on the 1% positioning dot so you can see exactly where the beam is. Nothing "
                              "moves. It turns itself off after 60 s.")
        ttk.Label(jr, text="  step").grid(row=1, column=3)
        ttk.Combobox(jr, textvariable=self.jog_step, values=["0.1", "0.5", "1", "5", "10", "50"], width=4,
                     state="readonly").grid(row=1, column=4)
        ttk.Label(jr, text="mm").grid(row=1, column=5)
        self.follow_var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(o, text="Move the picture with the head", variable=self.follow_var)
        cb.pack(anchor="w", pady=(6, 0))
        ToolTip(cb, "On: after each move the head keeps its X/Y, so the whole picture shifts on the real piece "
                    "with the head (like moving the piece under the laser). Off: the head moves over the picture "
                    "to another spot. Needs the start point set first.")
        cr = ttk.Frame(o)
        cr.pack(anchor="w", pady=(6, 0))
        ttk.Label(cr, text="Click on the preview to:").grid(row=0, column=0, sticky="w")
        self.click_var = tk.StringVar(value="none")
        for i, (val, text, tip) in enumerate((
                ("none", "do nothing", "Clicking the preview does nothing."),
                ("goto", "move the head there", "The head moves to the spot you click, laser off. Needs the start "
                                                "point set, so the app knows where the head really is."),
                ("here", "say 'the dot is here'", "Look where the dot really is on your piece and click that spot "
                                                  "on the picture. Nothing moves: the controller learns where the "
                                                  "head is (G10 L20 P1), so the purple marker jumps there."))):
            rb = ttk.Radiobutton(cr, text=text, value=val, variable=self.click_var,
                                 command=lambda: self.preview.set_cursor_mode())
            rb.grid(row=i + 1, column=0, sticky="w", padx=(12, 0))
            ToolTip(rb, tip)
        orow = ttk.Frame(o)
        orow.pack(anchor="w", pady=(8, 0))
        b = ttk.Button(orow, text="Set start point here", command=self.set_origin)
        b.pack(side="left")
        ToolTip(b, "Nothing moves. Tells the controller that the spot under the head is X0 Y0, the start point "
                   "the job is measured from (G10 L20 P1 X0 Y0).")
        b = ttk.Button(orow, text="Move head to start point", command=self.go_origin)
        b.pack(side="left", padx=6)
        ToolTip(b, "The head moves to X0 Y0 with the laser off.")
        p = ttk.LabelFrame(f, text="Perimeter check (1% dot)", style="Card.TLabelframe")
        p.pack(fill="x", pady=4)
        wrap_label(p, "The head visits each corner of the burn area with the laser off and flashes your 1% "
                      "positioning dot there (S10, same safety checks as the Positioning Laser app), then returns "
                      "to the start point.", style="Small.TLabel").pack(anchor="w")
        link(p, "How the start point and perimeter check work",
             lambda: self.open_help("Start point & perimeter check")).pack(anchor="w", pady=(2, 0))
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
        ToolTip(self.btn_perim, "The head moves to each corner of the burn area with the laser off, flashes the "
                                "1% dot there, then goes back to the start point.")
        ttk.Button(br, text="Stop", command=self.stop_perimeter).pack(side="left", padx=6)
        self.perim_lbl = wrap_label(p, "", style="Muted.TLabel")
        self.perim_lbl.pack(anchor="w", pady=(4, 0))
        ttk.Label(p, text="Off by a bit? Move the picture, then check again:").pack(anchor="w", pady=(8, 2))
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
        self.ready_box = ttk.Frame(e)
        self.ready_box.pack(fill="x", pady=(8, 0))
        self.ready_box.columnconfigure(1, weight=1)
        ttk.Label(self.ready_box, text="Ready to start?", style="H2.TLabel").grid(row=0, column=0, columnspan=2,
                                                                                  sticky="w")
        self.ready_rows = []
        for i in range(6):
            mark = ttk.Label(self.ready_box, font=("Segoe UI", 10, "bold"), width=2)
            mark.grid(row=i + 1, column=0, sticky="nw")
            lab = wrap_label(self.ready_box, "")
            lab.grid(row=i + 1, column=1, sticky="w")
            self.ready_rows.append((mark, lab))
        self.btn_start = ttk.Button(e, text="Start engraving", style="Big.TButton", command=self.start_engraving)
        ToolTip(self.btn_start, "Burns the job, starting from the start point. The head must be at X0 Y0.")
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
        self.btn_continue = ttk.Button(pb, text="Continue with the next pass", style="Big.TButton",
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
        if not self.need_connection():
            return
        if self.follow_var.get():
            if not self.origin_set:
                messagebox.showinfo("Set the start point first", "'Move the picture with the head' keeps the "
                                    "picture where the head is, so set the start point first.")
                return
            self.worker.submit("dot_follow" if self.dot_on else "follow", machine.jog_keep_position, dx, dy, 1000)
        else:
            self.worker.submit("dot_jog" if self.dot_on else "jog", machine.jog, dx, dy, 1000)

    def origin_words(self):
        return jobs.origin_text(self.job.piece if self.job is not None else self.piece)

    def start_point_moved(self):
        """The start point now sits somewhere else on the piece, so the controller's X0 Y0 is out of date."""
        if self.origin_set:
            self.origin_set = False
            self.say("The start point moved on the piece: put the head on it and set it again in step 5.", "warn")
            self.refresh_laser_page()

    # ================================================================ clicking the preview
    def click_mode(self):
        """What a click on the preview does right now: 'spot' (step 3), 'goto' / 'here' (step 5) or None."""
        tab = self.nb.index("current")
        if tab == 2 and self.origin_var.get() == "spot":
            return "spot"
        if tab == 4 and self.click_var.get() in ("goto", "here") and not self.gfile:
            return self.click_var.get()
        return None

    def preview_clicked(self, x, y, from_left, from_bottom):
        mode = self.click_mode()
        if mode == "spot":
            self.pick_spot(from_left, from_bottom)
        elif mode in ("goto", "here") and self.need_connection():
            px0, py0, px1, py1 = planner.piece_rect(self.job.piece if self.job is not None else self.piece)
            x, y = round(min(px1, max(px0, x)), 2), round(min(py1, max(py0, y)), 2)   # stay on the piece
            if mode == "goto":
                if not self.origin_set:
                    messagebox.showinfo("Set the start point first", "Until the start point is set the app doesn't "
                                        "know where the head really is, so it can't move it to a spot on the "
                                        "picture.")
                    return
                self.worker.submit("goto", machine.move_off, x, y, 1500)
            elif messagebox.askyesno(
                    "Is the dot here?", f"Is the laser dot exactly on the spot you clicked?\n\nNothing moves. "
                                        f"The controller learns that the head is at X {x:.1f}, Y {y:.1f}, so the "
                                        "picture lines up with where the head really is."):
                self.worker.submit("here", machine.set_origin_here, x, y)

    def set_origin(self):
        if self.need_connection() and messagebox.askyesno(
                "Set start point", f"Is the laser head exactly over the {self.origin_words()}?\n\n(Use the 1% dot to "
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
                txt += " The controller restarted when connecting, so set the start point again."
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
            self.refresh_ready()
        elif kind == "dot":
            self.dot_on = bool(ev[1])
            self.btn_dot.configure(text="Dot OFF" if self.dot_on else "Dot on (1%)")
        elif kind == "done":
            name = ev[1]
            if name in ("follow", "dot_follow"):
                self.origin_count += 1
                self.say("The head and the picture moved together. Run the perimeter check again.", "ok")
            elif name == "here":
                self.origin_set = True
                self.origin_count += 1
                self.say("Got it: the head is where you clicked. The purple marker shows it.", "ok")
            elif name in ("origin", "declare"):
                self.origin_set = True
                self.origin_count += 1
                self.say("Start point set: this spot is now X0 Y0." if name == "origin" else
                         "Position declared at the stop point.", "ok")
            elif name == "perimeter":
                self.perim_running = False
                self.perim_idx = None
                if not self.gfile:
                    self.perim_checked = (self._bbox_key(), self.origin_count)
                self.perim_lbl.configure(text="Done - head is back at the start point. Happy with the corners? Start "
                                              "engraving. Off a little? Move the picture and check again.")
                self.preview.refresh()
            elif name == "unlock":
                self.say("Unlocked. The position may be unknown - set or declare it before burning.", "warn")
                self.btn_unlock.pack_forget()
        elif kind == "failed":
            name, msg = ev[1], ev[2]
            if name == "perimeter":
                self.perim_running = False
                self.perim_idx = None
                self.perim_lbl.configure(text=("Stopped - head returned to the start point." if "cancel" in msg
                                               else f"Stopped: {msg}"))
                self.preview.refresh()
            else:
                messagebox.showwarning("Laser", msg)
        elif kind == "perim":
            _, i, n, name, what = ev
            self.perim_idx = i if i < n else None
            self.perim_lbl.configure(text=f"Point {min(i + 1, n)} of {n} ({name}): "
                                          + {"moving": "moving there, laser off...", "dot": "flashing the 1% dot",
                                             "done": "returning to the start point"}[what])
            self.preview.redraw()
        elif kind == "rebooted":
            self.origin_set = False
            self.say(ev[1] + " Set the start point (or declare the stop point) again before burning.", "bad")
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
                                        "where the beam is), then press 'Set start point here'."
                                        + ("  Start point set." if self.origin_set else ""))
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
            self.btn_start.state(["disabled"] if live else ["!disabled"])
        if self.gfile or live:
            self.ready_box.pack_forget()
        else:
            self.ready_box.pack(fill="x", pady=(8, 0), before=self.btn_start)
        self.refresh_ready()

    # ================================================================ ready to start?
    def _bbox_key(self):
        job = self.job
        if job is None:
            return None
        if self._bbox_cache[0] is not job:
            self._bbox_cache = (job, job.burn_bbox())
        b = self._bbox_cache[1]
        return tuple(round(v, 2) for v in b) if b else None

    def ready_items(self):
        """The 'Ready to start?' list: (done, what, how to get there). The first three must be done to start."""
        job, st = self.job, self.last_status
        checked = bool(job is not None and self.report and self.report["ok"] and self.compiled_gen == self.gen)
        perim = self.origin_set and self.perim_checked == (self._bbox_key(), self.origin_count)
        at_start = bool(self.connected and st and st.state == "Idle" and st.wpos
                        and math.hypot(st.wpos[0], st.wpos[1]) <= 0.05)
        return [
            (job is not None, "Picture open", "open one in step 1."),
            (checked, "Job checked", "open a picture first." if job is None else
             "the check found a problem: see step 4." if self.report and not self.report["ok"] else
             "checking now (it runs by itself)."),
            (self.connected, "Connected to the laser", "press Connect at the top of this step."),
            (self.connected and self.origin_set, "Start point set",
             f"put the head over the {self.origin_words()} and press 'Set start point here'."),
            (perim, "Perimeter check done for this start point and picture",
             "press 'Run perimeter check'." if self.perim_checked is None else
             "the picture or start point changed since the last check: run it again."),
            (at_start, "Head at the start point, machine idle", "press 'Move head to start point'."),
        ]

    def refresh_ready(self):
        if not hasattr(self, "ready_rows"):
            return
        items = self.ready_items()
        if items == self._ready_shown:
            return
        self._ready_shown = items
        for (mark, lab), (done, what, how) in zip(self.ready_rows, items):
            mark.configure(text="\u2713" if done else "\u2717", foreground=COLORS["ok"] if done else COLORS["bad"])
            lab.configure(text=what if done else f"{what}: {how}",
                          foreground=COLORS["ink"] if done else COLORS["muted"])

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
        fill, outline = gcodeinfo.describe_fill(info)
        self.gfile_lbl.configure(text=f"{info['name']}: burns X {b[0]:.2f}..{b[2]:.2f}, Y {b[1]:.2f}..{b[3]:.2f} mm, "
                                      f"max power S{info['max_s']:g}.{warn}\n{fill}",
                                 foreground=COLORS["warn"] if outline else COLORS["ink"])
        self.preview.refresh()
        self.goto(4)
        self.refresh_laser_page()
        if outline:
            self.say("This file only burns OUTLINES - shapes won't fill in. See the warning under the preview.", "warn")
        else:
            self.say("G-code loaded. Connect, set the start point the file expects, then Run perimeter check.", "ok")

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
                "Start point", "You haven't set the start point since connecting. The check uses the controller's current "
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
                                   f"points and flash the 1% dot {pulses}x at each, then return to the start point.\n\n"
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
        items = self.ready_items()
        missing = [f"- {what}: {how}" for done, what, how in items[:3] if not done]
        if missing:
            messagebox.showinfo("Not ready yet", "Before starting:\n\n" + "\n".join(missing))
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
            if messagebox.askyesno("Head not at the start point", "The job starts from the start point (X0 Y0). Move the head "
                                                             "there now with the laser off?"):
                self.go_origin()
            return
        if not self.origin_set and not messagebox.askyesno(
                "Start point", f"You haven't set the start point since connecting. Is the head really over the "
                          f"{self.origin_words()}?"):
            return
        if not items[4][0] and not messagebox.askyesno(
                "Perimeter check", "You haven't run the perimeter check for this start point and picture, so you "
                                   "haven't seen where the corners will land.\n\nStart anyway?"):
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
                  "estop": "EMERGENCY STOP sent.", "continue": "Continuing with the next pass..."}[cmd],
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
            self.say("Job finished. Laser off, head parked at the start point.", "ok")
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
