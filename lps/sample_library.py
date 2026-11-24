"""Browse a local project catalog and use Studio's existing picture/job loaders."""
from __future__ import annotations

import json
import os
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from . import imaging, jobs, samples


MATERIALS = ("Tin", "Slate", "Glass", "Wood")
KINDS = {"reference": "Reference", "image": "Image input", "job": "Saved job"}
PHOTO_ONLY = {".heic", ".heif"}
CATALOG_SETTING = "project_sample_catalog"


def local_path(value: str, directory: Path) -> Path:
    path = Path(value)
    if not value or ":" in str(path)[len(path.drive):] or path.drive.startswith("\\\\"):
        raise ValueError("Use local file paths in the sample catalog.")
    if path.anchor and not path.is_absolute():
        raise ValueError("Use a full path or a path relative to the catalog.")
    return path if path.is_absolute() else directory / path


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    material: str
    kind: str
    path: Path
    project: str
    notes: str

    def unavailable(self) -> str:
        if self.kind == "job":
            if self.path.name.lower() != "job.json":
                return "A saved job must point to its job.json."
        elif self.path.suffix.lower() not in imaging.PICTURE_TYPES:
            return "Unsupported picture type."
        elif self.kind == "image" and self.path.suffix.lower() in PHOTO_ONLY:
            return "HEIC and HEIF catalog items are reference photos."
        try:
            if not self.path.is_file():
                return "File missing or unavailable."
        except OSError:
            return "File unavailable."
        return ""


def read_catalog(path: Path) -> list[Entry]:
    path = local_path(str(path), Path.cwd())
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Expected a version 1 Studio sample catalog.")

    entries, ids = [], set()
    for number, row in enumerate(data["entries"], 1):
        fields = ("id", "title", "material", "kind", "path", "project", "notes")
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) for key in fields):
            raise ValueError(f"Catalog entry {number} has missing or invalid fields.")
        if not row["id"] or row["id"] in ids or not row["title"].strip():
            raise ValueError(f"Catalog entry {number} needs a unique ID and a title.")
        if row["material"] not in MATERIALS or row["kind"] not in KINDS:
            raise ValueError(f"Catalog entry {number} has an unknown material or item type.")
        ids.add(row["id"])
        values = {key: row[key] for key in fields}
        values["path"] = local_path(row["path"], path.parent)
        entries.append(Entry(**values))
    return entries


class SampleLibrary(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Samples & Jobs")
        self.transient(app.root)
        self.geometry("760x575")
        self.minsize(560, 475)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.entries = []
        self.catalog_entries = []
        self.current = None
        self.photo = None

        box = ttk.Frame(self, padding=12)
        box.pack(fill="both", expand=True)
        bar = ttk.Frame(box)
        bar.pack(fill="x")
        ttk.Label(bar, text="Material").pack(side="left")
        self.material = ttk.Combobox(bar, values=("All materials", *MATERIALS), state="readonly", width=16)
        self.material.current(0)
        self.material.pack(side="left", padx=6)
        self.material.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.recent = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Recent jobs", variable=self.recent, command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Choose catalog...", command=self.choose_catalog).pack(side="right")
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="right", padx=6)
        self.catalog_label = ttk.Label(box, wraplength=700)
        self.catalog_label.pack(anchor="w", pady=6)

        listing = ttk.Frame(box)
        listing.pack(fill="both", expand=True)
        self.listing = ttk.Treeview(listing, columns=("material", "kind", "availability"), show="tree headings",
                                    selectmode="browse", height=7)
        for key, title, width in (("#0", "Sample", 250), ("material", "Material", 65),
                                  ("kind", "Type", 105), ("availability", "File", 85)):
            self.listing.heading(key, text=title)
            self.listing.column(key, width=width, stretch=key == "#0")
        scroller = ttk.Scrollbar(listing, orient="vertical", command=self.listing.yview)
        self.listing.configure(yscrollcommand=scroller.set)
        scroller.pack(side="right", fill="y")
        self.listing.pack(side="left", fill="both", expand=True)
        self.listing.bind("<<TreeviewSelect>>", lambda _event: self.select())

        details = ttk.Frame(box)
        details.pack(fill="x", pady=8)
        self.preview = ttk.Label(details)
        self.preview.pack(side="right", padx=(8, 0))
        self.details = tk.Text(details, height=6, wrap="word", state="disabled")
        self.details.pack(side="left", fill="x", expand=True)

        actions = ttk.Frame(box)
        actions.pack(fill="x")
        self.open_button = ttk.Button(actions, command=self.open_entry)
        self.open_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="Copy path", command=self.copy_path)
        self.copy_button.pack(side="left", padx=6)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        self.reload()

    def choose_catalog(self):
        previous = self.app.settings.get(CATALOG_SETTING)
        initialdir = str(Path(previous).parent) if previous else None
        path = filedialog.askopenfilename(parent=self, title="Choose project sample catalog", initialdir=initialdir,
                                          filetypes=[("Sample catalog", "*.json")])
        if path and self.load(path):
            settings = dict(self.app.settings, **{CATALOG_SETTING: path})
            try:
                jobs.save_settings(settings)
                self.app.settings = settings
            except OSError as exc:
                messagebox.showerror("Catalog choice could not be saved", jobs.settings_write_problem(exc), parent=self)

    def reload(self):
        self.load(self.app.settings.get(CATALOG_SETTING) or "")

    def load(self, path):
        self.catalog_entries = []
        message = "Choose the shared project catalog to browse samples."
        ok = False
        if path:
            try:
                self.catalog_entries = read_catalog(Path(path))
                message = str(path)
                ok = True
            except (OSError, ValueError) as exc:
                message = f"Catalog unavailable: {path}\n{exc}"
        self.catalog_label.configure(text=message)
        self.refresh()
        return ok

    def refresh(self):
        self.entries = self.recent_entries() if self.recent.get() else self.catalog_entries
        self.listing.delete(*self.listing.get_children())
        material = self.material.get()
        groups = {}
        indexed = enumerate(self.entries)
        if not self.recent.get():
            indexed = sorted(indexed, key=lambda item: (item[1].material, item[1].project.casefold(),
                                                        item[1].title.casefold()))
        for i, entry in indexed:
            if material in ("All materials", entry.material):
                parent = ""
                if not self.recent.get():
                    key = (entry.material, entry.project)
                    if key not in groups:
                        groups[key] = self.listing.insert("", "end", text=f"{entry.material} / {entry.project}",
                                                          open=True)
                    parent = groups[key]
                status = "Unavailable" if entry.unavailable() else "Present"
                self.listing.insert(parent, "end", iid=f"item:{i}", text=entry.title,
                                    values=(entry.material, KINDS[entry.kind], status))
        self.select()

    def recent_entries(self):
        known = {os.path.normcase(str(item.path)): item for item in self.catalog_entries if item.kind == "job"}
        entries = []
        for value in self.app.settings.get("recent_editable_jobs") or []:
            try:
                path = local_path(value, Path.cwd())
            except ValueError:
                continue
            match = known.get(os.path.normcase(str(path)))
            if match:
                entries.append(match)
                continue
            doc = jobs.read_json(path, {}) or {}
            material = doc.get("material", {}).get("look")
            label = {"glass": "Glass", "slate": "Slate", "pine": "Wood",
                     "lightwood": "Wood", "darkwood": "Wood", "tin": "Tin"}.get(material, "")
            entries.append(Entry(str(path), doc.get("name") or path.parent.name, label, "job", path,
                                 "Recent", "Previously opened as an editable Studio job."))
        return entries

    def select(self):
        selection = self.listing.selection()
        item = selection[0] if selection else ""
        self.current = self.entries[int(item[5:])] if item.startswith("item:") else None
        self.photo = None
        self.preview.configure(image="")
        entry = self.current
        problem = entry.unavailable() if entry else ""
        text = "Select a sample to see its notes and file path."
        action = "Open sample"
        if entry:
            text = "\n".join(filter(None, (entry.project, entry.notes, problem, str(entry.path))))
            action = {"reference": "View reference", "image": "Open artwork",
                      "job": "Open editable job"}[entry.kind]
            if not problem and entry.kind != "job" and entry.path.suffix.lower() not in PHOTO_ONLY:
                try:
                    picture = samples.thumbnail(entry.path, (172, 118))
                    self.photo = ImageTk.PhotoImage(picture)
                    self.preview.configure(image=self.photo)
                except (OSError, ValueError, RuntimeError):
                    text += "\nPreview unavailable."
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")
        self.open_button.configure(text=action, state="normal" if entry and not problem else "disabled")
        self.copy_button.configure(state="normal" if entry else "disabled")

    def copy_path(self):
        if self.current:
            self.clipboard_clear()
            self.clipboard_append(str(self.current.path))

    def open_entry(self):
        entry = self.current
        if entry is None:
            return
        problem = entry.unavailable()
        if problem:
            messagebox.showerror("Sample unavailable", problem, parent=self)
            self.refresh()
            return
        if entry.kind == "reference":
            try:
                os.startfile(str(entry.path))
            except OSError as exc:
                messagebox.showerror("Couldn't open the reference", str(exc), parent=self)
        elif self.app._picture_job_in_use():
            messagebox.showinfo("Studio is busy", "Finish the active operation before loading a sample.", parent=self)
        elif entry.kind == "image":
            self.app.open_picture(entry.path)
        elif self.app.open_saved_job(entry.path):
            self.destroy()
