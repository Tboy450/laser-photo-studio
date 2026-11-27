"""Operator-paced run list for a saved flush jig."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .jig_project import Project
from .jig_runlist import RunList


class RunListWindow(tk.Toplevel):
    def __init__(self, jig):
        super().__init__(jig)
        self.jig = jig
        self.app = jig.app
        self.batch = None
        self.records = {}
        self.title("Jig run list")
        self.geometry("760x445")
        self.transient(jig)
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Button(top, text="New batch of tins…", command=self.new).pack(side="left")
        ttk.Button(top, text="Open saved list…", command=self.open).pack(side="left", padx=4)
        ttk.Button(top, text="Refresh history", command=self.refresh).pack(side="left")
        self.summary = tk.StringVar(value="Create a new batch for fresh tins, or open an existing list to continue.")
        ttk.Label(body, textvariable=self.summary, wraplength=670).pack(anchor="w", pady=5)
        table = ttk.Frame(body)
        table.pack(fill="both", expand=True)
        self.rows = ttk.Treeview(table, show="headings", columns=("pocket", "layer", "name", "state"), selectmode="browse")
        for key, title, width in (("pocket","Pocket",55), ("layer","Layer",50),
                                  ("name","Saved job",275), ("state","Run status",165)):
            self.rows.heading(key, text=title)
            self.rows.column(key, width=width, stretch=key in ("name", "state"))
        scroll = ttk.Scrollbar(table, command=self.rows.yview)
        self.rows.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.rows.pack(fill="both", expand=True)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(6,0))
        ttk.Button(actions,text="Open next ready layer in Check",command=lambda: self.prepare(True)).pack(side="left")
        ttk.Button(actions,text="Open selected in Check",command=lambda: self.prepare(False)).pack(side="left",padx=4)
        ttk.Button(actions,text="View run record",command=self.view_record).pack(side="left")
        self.note = tk.StringVar(value="Each layer opens in Studio's normal Check tab. Start it from Laser when ready.")
        ttk.Label(body,textvariable=self.note,wraplength=675,justify="left").pack(anchor="w",pady=(5,0))
        # Only look for lists alongside this jig, and verify their exact jig path before adopting one.
        files = sorted(jig.file.parent.glob("*.lpsrunlist"), key=lambda p:p.stat().st_mtime_ns, reverse=True)
        for file in files:
            if file.name.startswith(jig.file.stem + " "):
                try:
                    batch = RunList.read(file)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if batch.jig == jig.file.resolve():
                    self.batch = batch
                    self.refresh()
                    break
        self.bind("<FocusIn>", self.focused)

    def focused(self, event):
        if event.widget is self:
            self.refresh()

    def saved(self):
        if self.jig.file is None or self.jig.dirty:
            if not self.jig.save():
                return False
        if self.batch and self.batch.jig != self.jig.file.resolve():
            self.note.set("Open the run list for the currently loaded jig.")
            return False
        return True

    def new(self):
        if not self.saved():
            return
        if not messagebox.askyesno("New batch of tins", "Create a fresh run list for the assigned pockets? "
                                   "Previous batches keep their own history.",parent=self):
            return
        try:
            self.batch = RunList.create(self.jig.file)
            self.refresh()
            self.note.set(f"Run list saved in {self.batch.file}")
        except (OSError, ValueError, KeyError) as exc:
            self.note.set(str(exc))

    def open(self):
        file = filedialog.askopenfilename(parent=self,initialdir=self.jig.file.parent,
                                          filetypes=[("Jig run list","*.lpsrunlist")])
        if not file:
            return
        try:
            batch = RunList.read(file)
            if batch.jig != self.jig.file.resolve():
                raise ValueError(f"Open this list's jig first: {batch.jig}")
            self.batch = batch
            self.refresh()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.note.set(str(exc))

    def refresh(self):
        if not self.batch:
            return
        try:
            project = Project.read(self.batch.jig)
            self.records = self.batch.records()
            states = [self.batch.status(i, project, self.records) for i in range(len(self.batch.entries))]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.note.set(f"Could not read the list or jig. {exc}")
            return
        selected = self.rows.selection()
        self.rows.delete(*self.rows.get_children())
        for i,(row,state) in enumerate(zip(self.batch.entries,states)):
            self.rows.insert("", "end", iid=str(i), values=(row.pocket+1,row.layer+1,row.name,state))
        choice = selected[0] if selected and self.rows.exists(selected[0]) else str(states.index("Ready") if "Ready" in states else 0)
        self.rows.selection_set(choice)
        self.rows.see(choice)
        self.summary.set(f"{self.batch.file.stem} · {states.count('Finished')} of {len(states)} layers finished.")
        self.title(f"Jig run list · {self.batch.file.stem}")

    def prepare(self, next_ready):
        if not self.batch or not self.saved():
            return
        if self.app._picture_job_in_use():
            self.note.set("Finish the active Studio operation first.")
            return
        self.refresh()
        if next_ready:
            row = next((i for i in self.rows.get_children() if self.rows.set(i,"state") == "Ready"), None)
        else:
            selected = self.rows.selection()
            row = selected[0] if selected else None
        if row is None:
            self.note.set("No layer is ready. Review the statuses in the list.")
            return
        try:
            idx = int(row)
            folder = self.batch.prepare(idx)
            if self.app.open_saved_job(folder):
                self.rows.selection_set(row)
                self.app.goto(3)
                self.app.root.lift()
                self.app.say(f"Pocket {self.batch.entries[idx].pocket+1}, layer {self.batch.entries[idx].layer+1} "
                             "opened from the jig run list. Use the shared jig zero.", "ok")
        except Exception as exc:
            self.note.set(str(exc))

    def view_record(self):
        selected = self.rows.selection()
        if not selected or int(selected[0]) not in self.records:
            self.note.set("This layer has no recorded physical run.")
            return
        import os
        _, folder, _ = self.records[int(selected[0])]
        os.startfile(str(folder))
