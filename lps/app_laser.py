"""Step 5: connect, origin, 1% dot, perimeter check, start, live progress, photos and recovery."""
from __future__ import annotations

import datetime as dt
import copy
from dataclasses import asdict
import math
import os
import shutil
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import gcodeinfo, imaging, jobs, machine, outlines, planner, verify, position_memory, presets
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
CHECK_LABELS = {
    "travel": "Total travel perimeter",
    "image": "Image perimeter",
    "sticker": "Sticker outline",
    "burn": "Full burn trace",
    "dry": "Dry run",
}
CHECK_HELP = {
    "travel": "Laser off. Frames the full travel envelope, including run-ups. It can cross no-burn zones.",
    "image": "1% beam. Frames the placed image, including blank space. On a round piece it follows the usable face.",
    "sticker": "1% beam. Traces the outside edges of the artwork islands. Transfers between islands are laser off.",
    "burn": "2% beam on the planned marking strokes, beam off for travel. Use a test piece if the surface may mark. "
            "This can take as long as the job.",
    "dry": "Laser off for every move. Replays the checked job in order and can take as long as the job.",
}


class LaserMixin:
    def init_machine_state(self):
        self.worker = None
        self.connected = False
        self.last_status = None
        self.origin_set = False
        self.origin_count = 0          # goes up each time a start point is set, so old perimeter checks expire
        self.completed_checks = {}
        self.check_mode = None
        self.active_check = None
        self._sticker_source = None
        self._sticker_paths = []
        self.observed_dot = None
        self._ready_shown = None
        self.dot_on = False
        self.perim_running = False
        self.active_folder = None
        self.run_state = None
        self.photo_seen = set()
        self.photo_baseline = 0.0
        self.port_var = tk.StringVar(value=self.settings["port"])
        self.demo = tk.BooleanVar(value=False)
        self.connection_rebooted = False
        self.inspection_request = None

    # ================================================================ page
    def page_laser(self, f):
        ttk.Label(f, text="5. Laser", style="H1.TLabel").pack(anchor="w")
        wrap_label(f, "Place the picture, set job zero, check the placement, then start. Jobs run in the "
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
        self.btn_disconnect = ttk.Button(row, text="Disconnect", command=self.disconnect)
        self.btn_disconnect.pack(side="left")
        ttk.Checkbutton(c, text="Demo mode (simulated laser - nothing moves)", variable=self.demo).pack(anchor="w",
                                                                                                    pady=(6, 0))
        self.conn_lbl = wrap_label(c, "Not connected.", style="Muted.TLabel")
        self.conn_lbl.pack(anchor="w", pady=(4, 0))
        ttk.Button(c, text="Restore saved setup / position...", command=self.restore_saved_setup).pack(
            anchor="w", pady=(6, 0))
        self.memory_lbl = wrap_label(c, "Setup position is saved locally after setting job zero.", style="Small.TLabel")
        self.memory_lbl.pack(anchor="w", pady=(4, 0))
        self.btn_unlock = ttk.Button(c, text="Unlock ($X - doesn't move anything)", command=self.unlock)
        ToolTip(self.btn_unlock, "Clears the controller's alarm lock so it accepts commands again. Nothing moves, "
                                 "and it doesn't home. The position may be unknown afterwards: set the start point "
                                 "again.")
        o = ttk.LabelFrame(f, text="Move the laser head and set the start point", style="Card.TLabelframe")
        o.pack(fill="x", pady=4)
        moves_note(o, "head", "These buttons move the real laser head (the head marker), laser off.").pack(
            fill="x", pady=(0, 4))
        self.pos_lbl = ttk.Label(o, text="X --   Y --", font=("Consolas", 13, "bold"))
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
        cb = ttk.Checkbutton(o, text="Shift engraving placement when jogging", variable=self.follow_var)
        cb.pack(anchor="w", pady=(6, 0))
        ToolTip(cb, "Arrow buttons only. On: jog the head and shift the job zero by the same amount, moving the "
                    "engraving on the material. Off: jog the head over the existing placement.")
        cr = ttk.Frame(o)
        cr.pack(anchor="w", pady=(6, 0))
        ttk.Label(cr, text="Click on the preview to:").grid(row=0, column=0, sticky="w")
        self.click_var = tk.StringVar(value="none")
        for i, (val, text, tip) in enumerate((
                ("none", "do nothing", "Clicking the preview does nothing."),
                ("goto", "Jog head to clicked point", "Moves the physical head with the beam off. Set job zero first."),
                ("here", "Mark observed dot", "Click where you see the real dot on the piece. This only adds a "
                                              "temporary mark. Apply alignment to update the controller."))):
            rb = ttk.Radiobutton(cr, text=text, value=val, variable=self.click_var,
                                 command=lambda: self.preview.set_cursor_mode())
            rb.grid(row=i + 1, column=0, sticky="w", padx=(12, 0))
            ToolTip(rb, tip)
        self.btn_align = ttk.Button(o, text="Apply alignment", command=self.apply_alignment)
        self.btn_align.pack(anchor="w", pady=(4, 0))
        self.alignment_lbl = wrap_label(o, "", style="Small.TLabel")
        self.alignment_lbl.pack(anchor="w")
        orow = ttk.Frame(o)
        orow.pack(anchor="w", pady=(8, 0))
        b = ttk.Button(orow, text="Set job zero here", command=self.set_origin)
        b.pack(side="left")
        ToolTip(b, "Nothing moves. Tells the controller that the spot under the head is X0 Y0, the start point "
                   "the job is measured from (G10 L20 P1 X0 Y0).")
        b = ttk.Button(orow, text="Move head to job zero", command=self.go_origin)
        b.pack(side="left", padx=6)
        ToolTip(b, "The head moves to X0 Y0 with the laser off.")
        p = ttk.LabelFrame(f, text="Check placement and travel", style="Card.TLabelframe")
        p.pack(fill="x", pady=4)
        wrap_label(p, "Choose a check to preview its path. Confirm to run it and return to job zero.",
                   style="Small.TLabel").pack(anchor="w")
        link(p, "How the start point and perimeter check work",
             lambda: self.open_help("Start point & perimeter check")).pack(anchor="w", pady=(2, 0))
        br = ttk.Frame(p)
        br.pack(fill="x", pady=(8, 0))
        self.check_buttons = {}
        for i, (mode, label) in enumerate(CHECK_LABELS.items()):
            suffix = {"travel": " (off)", "burn": " (2%)", "dry": " (off)"}.get(mode, " (1%)")
            b = ttk.Button(br, text=label + suffix, command=lambda mode=mode: self.run_perimeter(mode))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 5), pady=(0, 4))
            ToolTip(b, CHECK_HELP[mode])
            self.check_buttons[mode] = b
        self.btn_stop_check = ttk.Button(br, text="Stop check", command=self.stop_perimeter)
        self.btn_stop_check.grid(row=2, column=1, sticky="w")
        self.box_lbl = wrap_label(p, "", style="H2.TLabel")
        self.box_lbl.pack(anchor="w", pady=(6, 0))
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
        actions = ttk.Frame(e)
        actions.pack(anchor="w", pady=(8, 0))
        self.btn_start = ttk.Button(actions, text="Start engraving", style="Big.TButton", command=self.start_engraving)
        ToolTip(self.btn_start, "Burns the job, starting from the start point. The head must be at X0 Y0.")
        self.btn_start.pack(side="left")
        self.btn_inspect = ttk.Button(actions, text="Park left 3½ in", command=lambda: self.inspection_move((-88.9, 0.0)))
        self.btn_inspect.pack(side="left", padx=4)
        self.btn_return = ttk.Button(actions, text="Return to zero", command=lambda: self.inspection_move((0.0, 0.0)))
        self.btn_return.pack(side="left")
        ToolTip(self.btn_inspect, "Laser off. Moves to X -88.9 mm, Y 0 from the saved job zero, regardless of the "
                                  "current head position. Repeated clicks do not move farther left. The picture and "
                                  "job zero stay fixed. Keep that left-hand travel clear.")
        ToolTip(self.btn_return, "Laser off. Returns to the same saved X0 Y0. If disconnected, reconnects and "
                                 "offers the saved reference before moving. Does not set a new zero.")
        wrap_label(e, "Inspect: park left of job zero, then return. Picture and zero stay fixed. "
                      "After disconnect, restore the saved reference first.", style="Small.TLabel").pack(
                          anchor="w", pady=(4, 0))
        m = ttk.LabelFrame(f, text="Job progress", style="Card.TLabelframe")
        m.pack(fill="x", pady=4)
        self.run_title = ttk.Label(m, text="No job running.", style="H2.TLabel")
        self.run_title.pack(anchor="w")
        self.run_bar = ttk.Progressbar(m, maximum=100)
        self.run_bar.pack(fill="x", pady=4)
        self.laser_lbl = tk.Label(m, text=" laser off ", bg=COLORS["ok_bg"], fg=COLORS["ok"],
                                  font=("Segoe UI", 10, "bold"))
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
        if self._closing or self.worker is not None:
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
        port = self.port_var.get() or "COM4"
        if port != self.settings["port"]:
            settings = dict(self.settings, port=port)
            try:
                jobs.save_settings(settings)
            except OSError as e:
                messagebox.showerror("Can't save the selected port", str(e))
                return
            self.settings = settings
        self.worker = MachineWorker(self.events, port, int(self.settings["baud"]), demo,
                                    jobs.read_json(DEMO_STATE, {}) if demo else None,
                                    context=self.setup_context())
        self.worker.start()
        self.conn_lbl.configure(text="Connecting...")
        self.refresh_laser_page()

    def disconnect(self, wait=False):
        self.inspection_request = None
        w = self.worker
        if w is None:
            if not wait:
                message = ("Use Stop in Job progress to stop the background engraving."
                           if jobs.active_runner() else "Laser is already disconnected.")
                self.say(message)
            return
        w.stop()
        if not wait:
            self.conn_lbl.configure(text="Letting queued check moves settle before disconnecting..." if self.perim_running
                                    else "Disconnecting...")
            self.refresh_laser_page()
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
        if self._closing:
            return False
        if not self.connected or self.worker is None or self.worker.quit.is_set():
            messagebox.showinfo("Not connected", "Connect to the laser first (top of step 5).")
            return False
        if self.perim_running:
            self.say("Wait for the check to return to job zero, or press Stop check.", "warn")
            return False
        if self.origin_set and not self.layout_pending:
            self.worker.context = self.setup_context()
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
                messagebox.showinfo("Set job zero first", "Shifting engraving placement with the arrow buttons "
                                    "requires an aligned job zero.")
                return
            self.worker.submit("dot_follow" if self.dot_on else "follow", machine.jog_keep_position, dx, dy, 1000)
        else:
            self.worker.submit("dot_jog" if self.dot_on else "jog", machine.jog, dx, dy, 1000)

    def origin_words(self):
        if self.gfile:
            return "origin expected by the G-code file"
        return jobs.origin_text(self.job.piece if self.job is not None else self.piece)

    def start_point_moved(self):
        """The start point now sits somewhere else on the piece, so the controller's X0 Y0 is out of date."""
        self.observed_dot = None
        if self.origin_set:
            self.origin_set = False
            self.say("Job zero moved on the piece. Set it again in step 5.", "warn")
            self.refresh_laser_page()

    # ================================================================ clicking the preview
    def click_mode(self):
        """What a click on the preview does right now: 'spot' (step 3), 'goto' / 'here' (step 5) or None."""
        tab = self.nb.index("current")
        if self.zone_editing():
            return None
        if tab == 2 and self.origin_var.get() == "spot":
            return "spot"
        if tab == 4 and self.click_var.get() in ("goto", "here") and not self.gfile:
            return self.click_var.get()
        return None

    def preview_clicked(self, x, y, from_left, from_bottom):
        mode = self.click_mode()
        if mode == "spot":
            self.pick_spot(from_left, from_bottom)
        elif mode in ("goto", "here") and not self.layout_pending and self.need_connection():
            px0, py0, px1, py1 = planner.piece_rect(self.job.piece if self.job is not None else self.piece)
            if not (px0 <= x <= px1 and py0 <= y <= py1):
                self.say("Click a point on the piece.", "warn")
                return
            x, y = round(x, 2), round(y, 2)
            if mode == "goto":
                if not self.origin_set:
                    self.say("Set job zero before jogging to a point on the preview.", "warn")
                    return
                self.jog_to_work(x, y, 1500)
            else:
                st = self.last_status
                if not st or st.state != "Idle" or not st.wpos or self.status_stale():
                    self.say("Wait for a current idle head position before marking the dot.", "warn")
                    return
                self.observed_dot = (x, y, st, self.gen, self.origin_count)
                self.refresh_laser_page()
                self.preview.draw_head()

    def current_observation(self):
        if self.observed_dot is not None:
            _, _, st, gen, origin = self.observed_dot
            if (self.connected and not self.layout_pending and gen == self.gen and origin == self.origin_count
                    and self.last_status and self.last_status.state == "Idle"
                    and machine.same_position(st, self.last_status)):
                return self.observed_dot
            self.observed_dot = None
        return None

    def apply_alignment(self):
        obs = self.current_observation()
        if obs is None or not self.need_connection():
            return
        x, y, st, _, _ = obs
        dx, dy = st.wpos[0] - x, st.wpos[1] - y
        if messagebox.askokcancel(
                "Apply alignment", f"Update job zero by X {dx:+.2f}, Y {dy:+.2f} mm from the current controller zero.\n\n"
                                   f"The head stays still at the observed X {x:.2f}, Y {y:.2f}. "
                                   "The selected job zero and artwork stay fixed in the preview. "
                                   "This clears the completed placement checks."):
            if self.current_observation() is obs and self.need_connection():
                self.worker.context = self.setup_context()
                self.origin_set = False
                self.observed_dot = None
                self.completed_checks.clear()
                self.worker.submit("here", machine.set_origin_here, x, y, observed=st)

    def set_origin(self):
        if self.layout_pending and not self.gfile:
            self.say("Wait for the placement preview before setting job zero.", "warn")
            return
        if self.need_connection() and messagebox.askyesno(
                "Set job zero", f"Is the laser head exactly over the {self.origin_words()}?\n\n(Use the 1% dot to "
                              "check.) This makes the current spot X0 Y0. It doesn't move anything."):
            self.worker.context = self.setup_context()
            self.origin_set = False
            self.observed_dot = None
            self.completed_checks.clear()
            self.worker.submit("origin", machine.set_origin_here, 0.0, 0.0)

    def go_origin(self):
        if self.need_connection() and self.origin_set:
            self.jog_to_work(0.0, 0.0, 3000)
        elif self.connected and not self.origin_set:
            self.say("Set job zero before moving the head there.", "warn")

    def jog_to_work(self, x, y, feed):
        self.observed_dot = None
        self.worker.submit("goto", machine.jog_to_work, x, y, feed,
                           status=lambda st: self.events.put(("status", st)))

    def inspection_move(self, target):
        """Explicit inspection request; reconnect/reconcile first, never reset zero to the parked head."""
        if self._closing or self.inspection_request:
            return
        if jobs.active_runner() or self.perim_running or self.layout_pending or (
                self.worker and (self.worker.busy or not self.worker.tasks.empty() or self.worker.quit.is_set())):
            self.say("Wait for the current job or movement to finish before inspecting.", "warn")
            return
        self.inspection_request = dict(target=target, deadline=time.monotonic() + 30)
        if not self.connected:
            self.connect()
            if self.worker is None:
                self.inspection_request = None
                return
        self._continue_inspection()

    def _continue_inspection(self):
        request = self.inspection_request
        if not request or self._closing:
            return
        if jobs.active_runner() or self.worker is None or self.worker.quit.is_set():
            self.inspection_request = None
            return
        if time.monotonic() > request["deadline"]:
            self.inspection_request = None
            self.say("Inspection move not started. Wait for an idle connection, then click again.", "warn")
            return
        if not self.connected or self.worker.busy or not self.worker.tasks.empty() or self.layout_pending or self.status_stale():
            self.root.after(100, self._continue_inspection)
            return
        if not self.origin_set:
            # A completed job/manual disconnect retains the frame in the local journal.
            # A reset or uncertain motion still needs reconciliation, never a blind jog.
            if not self.restore_saved_setup():
                self.inspection_request = None
                return
            request["deadline"] = time.monotonic() + 30
            self.root.after(100, self._continue_inspection)
            return
        if not self.last_status.idle_off:
            self.inspection_request = None
            self.say("Turn the positioning dot off and wait for Idle before the inspection move.", "warn")
            return
        self.worker.context = self.setup_context()
        self.inspection_request = None
        self.jog_to_work(*request["target"], 3000)
        self.say("Moving left for inspection; picture and job zero stay fixed."
                 if request["target"][0] else "Returning to the saved job zero, laser off.")

    def setup_context(self):
        mat, placement, look = self.build_params()
        return dict(picture_file=str(self.picture_path) if self.picture_path else None,
                    picture_sha256=jobs.sha256(self.picture_path) if self.picture_path and self.picture_path.exists() else None,
                    rotate=self.rotate, mirror=self.mirror, material=asdict(mat), piece=copy.deepcopy(self.piece),
                    fit=placement.fit, art_w=placement.art_w, dx=self.dx, dy=self.dy, look=look,
                    grid=copy.deepcopy(self.grid_spec), job_folder=str(self.saved[self.gen]) if self.gen in self.saved else None,
                    external_file=self.gfile.get("path") if self.gfile else None,
                    check_mode=self.check_mode, job_name=self.job.name if self.job else None,
                    keep_proportions=self.proportions_var.get())

    def remember_setup(self):
        if self.worker and self.connected and self.origin_set:
            self.worker.submit("remember_setup", self.worker.remember_setup, self.setup_context())

    def saved_position(self):
        return jobs.read_json(position_memory.memory_path(self.port_var.get() or "COM4", self.demo.get()), {}) or {}

    def show_saved_position(self):
        record = self.saved_position()
        last = record.get("last_reported" if record.get("in_flight") else "last_idle") or {}
        p = last.get("wpos")
        if p:
            label = "Last reported during motion" if record.get("in_flight") else "Saved idle position"
            self.memory_lbl.configure(text=f"{label}: X {p[0]:.3f}, Y {p[1]:.3f} from saved job zero. "
                                           "Restore saved setup to reconnect this reference. Nothing moves automatically.")

    def load_setup_context(self, ctx):
        """Restore the exact placement/settings, without importing file DPI or refitting."""
        picture = None if ctx.get("grid") else ctx.get("picture_file")    # grids and ladders have no picture file
        if picture and ctx.get("picture_sha256") and jobs.sha256(Path(picture)) != ctx["picture_sha256"]:
            raise ValueError("The saved source picture has changed. Restore the original file before recovering this setup.")
        raw = imaging.load_picture(picture) if picture else None  # fail before changing the UI
        self.mat = presets.Material.from_dict(ctx["material"])
        self.base_mat = next((m for m in self.materials if m.key == self.mat.key), self.mat)
        self._show_material()
        self.picture_path = Path(picture) if picture else None
        self.picture_raw = raw
        self.rotate, self.mirror = ctx.get("rotate", 0), ctx.get("mirror", False)
        self.picture = imaging.orient(raw, self.rotate, self.mirror) if raw is not None else None
        self.grid_spec = ctx.get("grid")
        self.gfile = None
        self.piece, self.piece_key, self.piece_user_set = copy.deepcopy(ctx["piece"]), "custom", True
        self.dx, self.dy, self.art_w = ctx["dx"], ctx["dy"], ctx.get("art_w")
        self.fit_var.set(ctx["fit"])
        self.proportions_var.set(ctx.get("keep_proportions", False))
        self.follow_var.set(False)
        for var, value in zip(self.v_cut, self.mat.tone_cuts):
            var.set(value)
        for key, var in (("brightness", self.v_bright), ("contrast", self.v_contrast), ("gamma", self.v_gamma),
                         ("sharpen", self.v_sharpen), ("autolevel", self.v_auto), ("negative", self.v_neg)):
            var.set(ctx["look"][key])
        self.pic_info.configure(text=f"Restored: {Path(picture).name if picture else 'test grid'}")
        self.sync_place_fields()
        self.completed_checks.clear()
        self.job = None  # restored origin belongs to this layout, not the previous preview
        self.changed(0)

    def restore_saved_setup(self):
        if not self.need_connection() or self.worker.busy or not self.worker.tasks.empty() or jobs.active_runner():
            return
        rec = self.saved_position()
        ctx = rec.get("context")
        st = self.last_status
        if not ctx or not rec.get("last_idle"):
            messagebox.showinfo("No saved setup", "Set job zero once to begin recording this setup.")
            return
        if not ctx.get("material"):
            messagebox.showinfo("Archived engraving", "This older run has position evidence but no complete setup snapshot. "
                                "Use its saved job and Resume after dropout.\n" + str(ctx.get("job_folder", "")))
            return
        if rec.get("coordinate_uncertain"):
            messagebox.showinfo("Saved reference needs checking", rec["coordinate_uncertain"] +
                                "\nThe previous setup is still recorded, but it cannot be declared at the current head position.")
            return
        if self.status_stale() or not st or not st.idle_off:
            self.say("Wait for a fresh idle, laser-off report before restoring.", "warn")
            return
        keep = False
        point = rec["last_idle"].get("wpos")
        if rec.get("in_flight"):
            old_wco = (rec.get("last_reported") or {}).get("wco")
            if (self.connection_rebooted or rec.get("reset") or not st.wco or not old_wco
                    or math.dist(st.wco[:2], old_wco[:2]) > .011):
                self.show_saved_position()
                messagebox.showinfo("Movement was interrupted",
                    "The saved path and placement are intact, but the controller's coordinate frame changed during motion. "
                    "The last sent endpoint is not a confirmed stop.\n\n"
                    "For an engraving, use Resume after dropout to check the interrupted position. "
                    "The full evidence is saved locally at:\n" + str(position_memory.memory_path(self.port_var.get(), self.demo.get())))
                return
            point, keep = st.wpos, True
            question = ("The saved check/move was interrupted. The controller now reports Idle with the same work offset. "
                        "Has the controller remained powered WITHOUT a reset, and have the head and material stayed untouched? "
                        "Use its current reported position and restore the saved layout?")
        else:
            question = (f"Saved setup: {ctx.get('job_name') or ctx.get('picture_file')}\n"
                        f"Last completed position: X {point[0]:.3f}, Y {point[1]:.3f}.\n\n"
                        "Have the head and material stayed physically in place since that completed move? "
                        "Restore its picture, size, settings and job-zero reference? This does not move the head.")
            keep = not self.connection_rebooted and not rec.get("reset") and position_memory.matches(st, rec["last_idle"])
        if not messagebox.askyesno("Restore saved setup", question):
            return
        if ctx.get("external_file"):
            messagebox.showinfo("External check", "Reopen the saved external file before restoring its placement:\n" + ctx["external_file"])
            return
        try:
            self.load_setup_context(ctx)
        except Exception as e:
            messagebox.showerror("Cannot restore saved picture", str(e))
            return
        self.origin_set = False
        self.worker.submit("restore_position", self.worker.restore_position, point[:2], st, ctx, keep_coordinates=keep)
        return True

    # ================================================================ events
    def machine_event(self, ev):
        kind = ev[0]
        if kind == "connected":
            info = ev[1]
            self.connected = True
            self.origin_set = False
            self.connection_rebooted = bool(info.get("rebooted"))
            self.last_status = info.get("status")
            self.show_saved_position()
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
                txt += " The controller restarted. Use Restore saved setup for a recorded idle position."
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
            self.refresh_laser_page(status_only=True)
            return
        elif kind == "busy":
            pass  # refresh the controls using the worker's current state
        elif kind == "dot":
            self.dot_on = bool(ev[1])
            self.btn_dot.configure(text="Dot OFF" if self.dot_on else "Dot on (1%)")
        elif kind == "done":
            name = ev[1]
            if name in ("follow", "dot_follow"):
                self.origin_count += 1
                self.completed_checks.clear()
                self.say("The head and the picture moved together. Run the perimeter check again.", "ok")
            elif name == "here":
                self.origin_set = True
                self.origin_count += 1
                self.observed_dot = None
                self.completed_checks.clear()
                self.say("Alignment applied. The head stayed still and job zero was updated.", "ok")
            elif name in ("origin", "declare", "restore_position"):
                self.origin_set = True
                self.origin_count += 1
                self.completed_checks.clear()
                self.say("Saved job zero restored; the head stayed still. Move head to job zero when ready."
                         if name == "restore_position" else "Job zero set. This spot is now X0 Y0." if name == "origin" else
                         "Position declared at the stop point.", "ok")
            elif name == "perimeter":
                self.perim_running = False
                mode, key = self.active_check
                valid = key == self.check_key()
                if valid:
                    self.completed_checks[mode] = key
                self.perim_lbl.configure(text=f"{CHECK_LABELS[mode]} finished. Head is back at job zero."
                                              + ("" if valid else " Placement changed. Check it again."))
                self.preview.refresh()
            elif name == "unlock":
                self.origin_set = False
                self.observed_dot = None
                self.say("Unlocked. The position may be unknown - set or declare it before burning.", "warn")
                self.btn_unlock.pack_forget()
            self.preview.draw_head()
        elif kind == "failed":
            self.inspection_request = None
            name, msg = ev[1], ev[2]
            if name == "perimeter":
                self.perim_running = False
                self.perim_lbl.configure(text=f"Check stopped. {msg}")
                self.preview.refresh()
            else:
                if name in ("follow", "dot_follow"):
                    self.origin_set = False
                    self.completed_checks.clear()
                    self.preview.draw_head()
                messagebox.showwarning("Laser", msg)
        elif kind == "perim":
            _, i, n, _, what = ev
            if self.worker is not None and self.worker.cancel.is_set():
                return
            mode, _ = self.active_check
            action = {"tracing": f"{i:,}/{n:,} moves sent", "returning": "returning to job zero",
                      "done": "back at job zero"}.get(what, "checking")
            self.perim_lbl.configure(text=f"{CHECK_LABELS[mode]} • {action}")
            return
        elif kind == "rebooted":
            self.inspection_request = None
            self.connection_rebooted = True
            self.origin_set = False
            self.completed_checks.clear()
            self.observed_dot = None
            self.preview.draw_head()
            self.say(ev[1] + " Set the start point (or declare the stop point) again before burning.", "bad")
        elif kind == "error":
            self.say(ev[1], "bad")
        elif kind == "link_lost":
            self.inspection_request = None
            self.say(f"Laser connection lost: {ev[1]}", "bad")
            self.conn_lbl.configure(text=f"Disconnected: {ev[1]}", foreground=COLORS["bad"])
        elif kind == "disconnected":
            self.inspection_request = None
            self.worker = None
            self.connected = False
            self.origin_set = False
            self.dot_on = False
            self.last_status = None
            self.show_saved_position()
            if self.perim_running:
                self.perim_lbl.configure(text="Check ended when the laser disconnected.")
            self.perim_running = False
            self.completed_checks.clear()
            self.observed_dot = None
            self.btn_dot.configure(text="Dot on (1%)")
            self.pos_lbl.configure(text="X --   Y --")
            if "Disconnected" not in str(self.conn_lbl.cget("text")):
                self.conn_lbl.configure(text="Not connected.", foreground=COLORS["muted"])
            self.preview.draw_head()
            if ev[1] is not None:
                try:
                    DEMO_STATE.parent.mkdir(parents=True, exist_ok=True)
                    jobs.write_json(DEMO_STATE, ev[1])
                except OSError as e:
                    self.say(f"Disconnected. Could not save the demo position: {e}", "warn")
        self.refresh_laser_page()

    def head_position(self):
        rs = self.run_state
        if rs and rs.get("phase") in LIVE:
            if self.active_folder == self.saved.get(self.gen) and not self.gfile:
                return rs.get("wpos")
            return None
        st = self.last_status
        return st.wpos[:2] if self.origin_set and st and st.wpos else None

    def status_stale(self):
        rs = self.run_state
        if rs and rs.get("phase") in LIVE:
            return time.time() - rs.get("position_at", 0) > 2.0
        return self.last_status is None or time.monotonic() - self.last_status.at > 2.0

    def laser_is_on(self):
        rs = self.run_state
        if rs and rs.get("phase") in LIVE and rs.get("laser_on"):
            return True
        return bool(self.last_status and self.last_status.laser_on) or self.dot_on

    def refresh_laser_page(self, status_only=False):
        if not hasattr(self, "pill"):
            return
        rs = self.run_state
        live = bool(rs and rs.get("phase") in LIVE and jobs.active_runner())
        can_disconnect = self.worker is not None and not self.worker.quit.is_set()
        self.btn_conn.state(["!disabled"] if self.worker is None and not live else ["disabled"])
        self.btn_disconnect.state(["!disabled"] if can_disconnect else ["disabled"])
        inspecting_busy = bool(live or self.perim_running or self.layout_pending or self.inspection_request or
                               (self.worker and (self.worker.busy or not self.worker.tasks.empty())))
        for button in (self.btn_inspect, self.btn_return):
            button.state(["disabled"] if inspecting_busy else ["!disabled"])
        if live:
            on = rs.get("laser_on")
            self.pill.configure(text=f" {'LASER ON - ' if on else ''}Job: {PHASE_TEXT.get(rs['phase'], rs['phase'])} "
                                     f"{int(100 * rs.get('progress', 0))}% ",
                                bg=COLORS["bad"] if on else COLORS["accent"], fg=COLORS["bg"])
        elif self.connected:
            st = self.last_status
            pos = f" X {st.wpos[0]:.1f} Y {st.wpos[1]:.1f}" if st and st.wpos else ""
            demo = "Demo laser" if self.demo.get() else "Connected"
            self.pill.configure(text=f" {'LASER ON (dot) - ' if self.dot_on else ''}{demo} - "
                                     f"{st.state if st else '...'}{pos} ",
                                bg=COLORS["bad"] if self.dot_on else COLORS["ok"], fg=COLORS["bg"])
        else:
            self.pill.configure(text=" Not connected ", bg=COLORS["pill"], fg=COLORS["header_ink"])
        self.origin_help.configure(text=f"Job zero is the {self.origin_words()}. "
                                        + ("Aligned to the controller." if self.origin_set else
                                           "Put the head there and press 'Set job zero here'."))
        obs = self.current_observation()
        self.btn_align.state(["!disabled"] if obs and not self.perim_running else ["disabled"])
        self.alignment_lbl.configure(text=(f"Observed dot at X {obs[0]:.2f}, Y {obs[1]:.2f}. "
                                           "Apply alignment to update job zero." if obs else ""))
        if status_only:
            self.refresh_ready()
            return
        job = self.job
        pending = self.layout_pending and not self.gfile
        for button in self.check_buttons.values():
            button.state(["disabled"] if pending or self.perim_running or live else ["!disabled"])
        self.btn_stop_check.state(["!disabled"] if self.perim_running else ["disabled"])
        if self.active_check and not self.perim_running and self.active_check[1] != self.check_key():
            self.active_check = None
            self.perim_lbl.configure(text="Placement or job zero changed. Choose a check for the current setup.")
        b = gcodeinfo.frame_bbox(self.gfile) if self.gfile else self.picture_box() if job is not None else None
        self.box_lbl.configure(text=f"Image size: {b[2] - b[0]:g} x {b[3] - b[1]:g} mm "
                                    f"({(b[2] - b[0]) / 25.4:.2f} x {(b[3] - b[1]) / 25.4:.2f} in)" if b else "")
        if pending:
            self.box_lbl.configure(text="Updating picture box...")
        elif b:
            self.box_lbl.configure(text=self.box_lbl.cget("text") +
                                   f"\nLower-left X {b[0]:.3f}, Y {b[1]:.3f}; "
                                   f"upper-right X {b[2]:.3f}, Y {b[3]:.3f} from start 0,0.")
            marks=self.gfile.get('burn_bbox') if self.gfile else job.burn_bbox() if job else None
            if marks:
                self.box_lbl.configure(text=self.box_lbl.cget('text')+
                                       f"\nActual marks: X {marks[0]:.3f}..{marks[2]:.3f}, "
                                       f"Y {marks[1]:.3f}..{marks[3]:.3f} from start 0,0.")
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
            self.btn_start.state(["disabled"] if live or self.perim_running else ["!disabled"])
        if self.gfile or live:
            self.ready_box.pack_forget()
        else:
            self.ready_box.pack(fill="x", pady=(8, 0), before=self.btn_start)
        self.refresh_ready()

    # ================================================================ ready to start?
    def check_key(self):
        return self.gen, self.origin_count, id(self.gfile) if self.gfile else None

    def picture_box(self):
        """Physical image dimensions, including blank pixels. The check traces actual burn edges separately."""
        g = self.job.geom
        return (g.x0, g.y0, g.x1, g.yt)

    def ready_items(self):
        """The 'Ready to start?' list: (done, what, how to get there). The first three must be done to start."""
        job, st = self.job, self.last_status
        checked = bool(job is not None and self.report and self.report["ok"] and self.compiled_gen == self.gen)
        key = self.check_key()
        perim = (not self.layout_pending and self.origin_set and
                 any(self.completed_checks.get(mode) == key for mode in ("image", "sticker", "burn", "dry")))
        at_start = bool(self.connected and self.origin_set and not self.status_stale() and st and st.state == "Idle" and st.wpos
                        and math.hypot(st.wpos[0], st.wpos[1]) <= 0.05)
        return [
            (job is not None, "Picture open", "open one in step 1."),
            (checked, "Job checked", "open a picture first." if job is None else
             "the check found a problem: see step 4." if self.report and not self.report["ok"] else
             "checking now (it runs by itself)."),
            (self.connected, "Connected to the laser", "press Connect at the top of this step."),
            (self.connected and self.origin_set, "Job zero aligned",
             f"put the head over the {self.origin_words()} and press 'Set job zero here'."),
            (perim, "Placement checked", "run Image perimeter, Sticker outline, Full burn trace, or Dry run."),
            (at_start, "Head at job zero, machine idle", "press 'Move head to job zero'."),
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
        self.completed_checks.clear()
        self.check_mode = None
        self.start_point_moved()
        b = info["burn_bbox"]
        frame = gcodeinfo.frame_bbox(info)
        warn = ("  WARNING: " + "; ".join(info["warnings"])) if info["warnings"] else ""
        fill, outline = gcodeinfo.describe_fill(info)
        self.gfile_lbl.configure(text=f"{info['name']}: burns X {b[0]:.2f}..{b[2]:.2f}, Y {b[1]:.2f}..{b[3]:.2f} mm, "
                                      f"max power S{info['max_s']:g}.{warn}\n{fill}\n"
                                      + ("Actual engraving outlines are available." if info.get('trace_paths') is not None else
                                         "This older/external file has no reconstructable engraving outline; open its source picture.")
                                      + f" Lower-left: X {frame[0]:.3f}, Y {frame[1]:.3f} from start 0,0.",
                                 foreground=COLORS["warn"] if outline else COLORS["ink"])
        self.preview.refresh()
        self.goto(4)
        self.refresh_laser_page()
        if outline:
            self.say("This file only burns OUTLINES - shapes won't fill in. See the warning under the preview.", "warn")
        else:
            self.say("G-code loaded. Connect, set the job zero the file expects, then choose a check.", "ok")

    def clear_gfile(self):
        if self.gfile is None:
            return
        self.start_point_moved()
        self.gfile = None
        self.completed_checks.clear()
        self.check_mode = None
        self.gfile_lbl.configure(text="")
        self.preview.refresh()
        self.refresh_laser_page()

    def verified_layout(self):
        return bool(not self.gfile and not self.layout_pending and self.job and self.report
                    and self.report["ok"] and self.compiled_gen == self.gen)

    def check_paths(self, mode):
        if self.gfile and not self.gfile.get("linear_xy"):
            return []
        if mode == "sticker":
            source = self.gfile.get("trace_paths") if self.gfile else self.job.trace_paths() if self.job else None
            if source is None:
                return []
            if self._sticker_source is not source:
                self._sticker_source = source
                self._sticker_paths = outlines.sticker_paths(source)
            return self._sticker_paths
        if mode == "travel":
            if self.gfile:
                bounds = self.gfile.get("travel_bbox")
            else:
                bounds = self.report["travel"] if self.verified_layout() else None
            if bounds:
                x0, y0, x1, y1 = bounds
                return [outlines.box_path((min(0, x0), min(0, y0), max(0, x1), max(0, y1)))]
        if mode == "image":
            bounds = self.gfile.get("picture_bbox") if self.gfile else self.picture_box() if self.job else None
            if bounds:
                if not self.gfile and self.job.piece.get("shape") == "circle":
                    g = self.job.geom
                    diameter = g.usable_rect[2] - g.usable_rect[0]
                    path = outlines.image_boundary(bounds, g.piece_rect, diameter)
                    return [path] if path else []
                return [outlines.box_path(bounds)]
        return []

    def run_perimeter(self, mode):
        if self.layout_pending and not self.gfile:
            self.say("The picture is updating. Choose a check after the preview refreshes.")
            return
        if self.perim_running or jobs.active_runner():
            return
        paths = self.check_paths(mode)
        replay = mode in ("burn", "dry") and self.verified_layout() and bool(self.report["travel"])
        if not paths and not replay:
            self.check_mode = None
            self.preview.refresh()
            self.perim_lbl.configure(text=f"{CHECK_LABELS[mode]} unavailable. Open the source picture and let Step 4 check it.")
            return
        self.check_mode = mode
        self.perim_lbl.configure(text=CHECK_HELP[mode])
        self.preview.redraw()
        if not self.need_connection():
            return
        if not self.origin_set or self.status_stale() or not self.last_status or self.last_status.state != "Idle":
            self.say("Set job zero and wait for an idle controller before running the check.", "warn")
            return
        key = self.check_key()
        if not messagebox.askokcancel(
                CHECK_LABELS[mode], CHECK_HELP[mode] + "\n\nWatch the head. It returns to job zero after the check."):
            return
        if key != self.check_key() or not self.origin_set or not self.need_connection():
            self.say("Placement or connection changed. Choose the check again.", "warn")
            return
        self.perim_running = True
        if self.verified_layout():
            self.save_current_job(quiet=True)
        self.worker.context = self.setup_context()
        self.completed_checks.pop(mode, None)
        self.active_check = (mode, key)
        self.perim_lbl.configure(text=f"Starting {CHECK_LABELS[mode].lower()}...")
        self.refresh_laser_page()
        feed = int(self.settings.get("perimeter_feed", 1500))
        events = self.events
        moves = verify.trace_moves(self.job) if replay else None
        count = 1 + sum(sum(1 for c in p.commands if c.startswith("G1 ")) for p in self.job.passes) if replay else 0
        self.worker.submit("perimeter", machine.trace_outline, paths, feed, cancel=self.worker.cancel,
                           shutdown=self.worker.quit,
                           progress=self.worker.trace_progress,
                           status=lambda st: events.put(("status", st)),
                           illuminate=mode in ("image", "sticker"), moves=moves, move_count=count,
                           live_trace=mode == "burn")

    def stop_perimeter(self):
        if self.worker is not None and self.perim_running:
            self.worker.cancel.set()
            self.dot_off()
            self.perim_lbl.configure(text="Stopping the check. Waiting for queued moves to settle...")

    # ================================================================ start / monitor
    def start_engraving(self):
        if jobs.active_runner():
            messagebox.showinfo("Busy", "A job is already running.")
            return
        items = self.ready_items()
        missing = [f"- {what}: {how}" for done, what, how in items[:4] if not done]
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
        if st is None or st.state != "Idle" or self.status_stale():
            messagebox.showinfo("Not ready", f"The machine is {st.state if st else 'not reporting'}; it must be Idle.")
            return
        if not st.wpos or math.hypot(st.wpos[0], st.wpos[1]) > 0.05:
            if messagebox.askyesno("Head not at the start point", "The job starts from the start point (X0 Y0). Move the head "
                                                             "there now with the laser off?"):
                self.go_origin()
            return
        if not items[4][0] and not messagebox.askyesno(
                "Placement check", "This job zero and picture have no completed placement check.\n\nStart anyway?"):
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
                                 pause_between=d["pause_between"], park=[0.0, 0.0], completed=[]), fresh_context=True)

    def launch(self, folder, spec, fresh_context=False):
        if self._closing:
            return
        if jobs.active_runner():
            messagebox.showerror("Busy", "Another job is already running.")
            return
        spec = dict(spec)
        spec.update(port=self.settings["port"], baud=int(self.settings["baud"]), demo=bool(self.demo.get()))
        spec["position_memory_path"] = str(position_memory.memory_path(spec["port"], spec["demo"]))
        if fresh_context:
            context = self.setup_context()
        else:
            previous = jobs.read_json(Path(folder) / "run.json", {}) or {}
            recorded = jobs.read_json(Path(folder) / "state.json", {}) or {}
            context = previous.get("setup_context") or (recorded.get("position_record") or {}).get("context") or {}
            if context.get("job_folder") and Path(context["job_folder"]).resolve() != Path(folder).resolve():
                context = {}
        spec["setup_context"] = dict(context, job_folder=str(folder))
        if self.worker is not None:
            self.disconnect(wait=True)
        if spec["demo"]:
            spec["demo_state"] = jobs.read_json(DEMO_STATE, {}) or {}
        pid = jobs.launch_runner(Path(folder), spec)
        self.active_folder = Path(folder)
        self.run_state = None
        self.photo_baseline = time.time()
        self.photo_seen = set()
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
            self.preview.draw_head()
            self.root.after(500, self._poll_runner)

    def _show_run(self, st, alive):
        prev = (self.run_state or {}).get("phase")
        ph = st.get("phase", "")
        if not alive and ph in LIVE:
            ph = "fault"
            st = dict(st, phase="fault", message="The job process ended unexpectedly. " + st.get("message", ""))
        self.run_state = st
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
        self.laser_lbl.configure(text=" LASER ON " if on else " laser off ",
                                 bg=COLORS["bad_bg"] if on else COLORS["ok_bg"], fg=COLORS["bad"] if on else COLORS["ok"])
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
