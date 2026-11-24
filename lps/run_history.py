"""Read saved Studio run records and attach private material/result notes."""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from . import imaging, jobs
from .dialogs import FormDialog
from .preview import fmt_dur
from .ui_common import paint


FIELDS = (
    ("stock", "Stock or blank", "str"),
    ("coating", "Coating / preparation", "str"),
    ("finish", "Observed finish", "str"),
    ("before_photo", "Before-cleaning photo", "picture_path"),
    ("after_photo", "After-cleaning photo", "picture_path"),
    ("notes", "Notes", "str"),
)
FINISHED = {"complete", "stopped", "fault", "dropout", "estop", "error"}


def read_run(folder):
    doc = jobs.read_json(folder / "job.json", {}) or {}
    state = jobs.read_json(folder / "state.json", {}) or {}
    times = jobs.read_json(folder / "timing.json", {}) or {}
    attempt = state.get("started")
    timer = (state.get("timer") or {}).get("job_t0")
    if timer is not None:
        attempt = str(timer)
    sidecar = jobs.read_json(folder / "results.json", {}) or {}
    notes = (sidecar.get("attempts") or {}).get(attempt, {})
    return doc, state, times.get("passes", []), attempt, notes


def save_run_result(folder, attempt, edited):
    _, state, _, current, _ = read_run(folder)
    if not attempt or attempt != current or state.get("demo") or state.get("phase") not in FINISHED:
        raise ValueError("This physical run changed or is still active. Reload Run history first.")
    values = {key: str(edited.get(key, "")).strip() for key, _label, _type in FIELDS}
    for key in ("before_photo", "after_photo"):
        path = Path(values[key])
        if values[key] and (not path.is_absolute() or path.suffix.lower() not in imaging.PICTURE_TYPES
                            or not path.is_file()):
            raise ValueError("Choose an existing photo file for each stage you enter.")
    path = folder / "results.json"
    record = jobs.read_json(path, {}) or {}
    if path.exists() and record.get("version") != 1:
        raise ValueError("Existing results.json could not be read as version 1.")
    record.setdefault("attempts", {}).setdefault(attempt, {}).update(values)
    record["version"] = 1
    jobs.write_json(path, record)


class RunHistory(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Studio run history")
        self.transient(app.root)
        self.geometry("760x570")
        self.minsize(585, 400)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        listing = ttk.Frame(body)
        listing.pack(fill="x")
        self.tree = ttk.Treeview(listing, columns=("status", "started"), height=8, selectmode="browse")
        for column, text, width in (("#0", "Job", 380), ("status", "Latest saved state", 130),
                                    ("started", "Started", 180)):
            self.tree.heading(column, text=text)
            self.tree.column(column, width=width, stretch=column == "#0")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.show_record())
        self.details = paint(tk.Text(body, height=8, wrap="word", state="disabled"),
                             background="face", foreground="ink")
        self.details.pack(fill="both", expand=True, pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        self.save_button = ttk.Button(actions, text="Edit result...", command=self.edit)
        self.save_button.pack(side="left")
        self.folder_button = ttk.Button(actions, text="Open run folder", command=self.open_folder)
        self.folder_button.pack(side="left", padx=6)
        ttk.Button(actions, text="Reload", command=self.reload).pack(side="left")
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        self.reload()

    def reload(self):
        try:
            self.folders = jobs.latest_jobs(100)
        except OSError:
            self.folders = []
        self.tree.delete(*self.tree.get_children())
        for i, folder in enumerate(self.folders):
            doc, state, _times, _attempt, _notes = read_run(folder)
            phase = state.get("phase", "Prepared")
            status = f"Demo / {phase}" if state.get("demo") else phase
            self.tree.insert("", "end", iid=str(i), text=doc.get("name", folder.name),
                             values=(status, state.get("started") or "—"))
        if self.folders:
            self.tree.selection_set("0")
        self.show_record()

    def selected(self):
        selection = self.tree.selection()
        return self.folders[int(selection[0])] if selection else None

    def show_record(self):
        folder = self.selected()
        lines, editable = ["Select a saved job. Prepared jobs have no runner record."], False
        if folder:
            doc, state, times, attempt, notes = read_run(folder)
            editable = bool(attempt and not state.get("demo") and state.get("phase") in FINISHED)
            m = doc.get("material") or {}
            lines = [str(folder), f"Saved recipe: {m.get('name', 'unknown')}, "
                     f"S{m.get('power', '?')} at {m.get('feed', '?')} mm/min, {m.get('pitch', '?')} mm rows."]
            if state:
                lines.append(f"Latest runner elapsed: {fmt_dur(state['elapsed_s'])}"
                             if state.get("elapsed_s") is not None else "Runner elapsed unavailable.")
                for entry in times[-20:]:
                    if entry.get("real_s") is not None:
                        lines.append(f"{entry.get('run_start', '')}  {entry.get('title', 'Pass')}: "
                                     f"{entry['real_s']:.3f} s ({entry.get('ended') or 'unconfirmed'}; "
                                     f"{entry.get('start_basis') or 'start basis unavailable'}).")
            else:
                lines.append("Prepared. No run result is recorded.")
            if notes:
                lines.append("Result notes for the latest recorded attempt")
                lines += [f"{label}: {notes.get(key) or 'Not recorded'}" for key, label, _ in FIELDS]
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")
        self.save_button.state(["!disabled"] if editable else ["disabled"])
        self.folder_button.state(["!disabled"] if folder else ["disabled"])

    def open_folder(self):
        folder = self.selected()
        if folder:
            try:
                os.startfile(str(folder))
            except OSError as exc:
                messagebox.showerror("Cannot open the run folder", str(exc), parent=self)

    def edit(self):
        folder = self.selected()
        if not folder:
            return
        _, state, _, attempt, notes = read_run(folder)
        if not attempt or state.get("demo") or state.get("phase") not in FINISHED:
            self.show_record()
            return
        changed = FormDialog(self, "Record physical result",
                             [(key, label, notes.get(key, ""), kind) for key, label, kind in FIELDS],
                             intro="Describe this attempt and link the original photos for each cleaning stage.",
                             ok_text="Save result").result
        if changed is not None:
            try:
                save_run_result(folder, attempt, changed)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Cannot save result", str(exc), parent=self)
            self.show_record()
