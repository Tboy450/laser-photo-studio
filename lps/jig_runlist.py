"""A named batch of physical tins. Progress comes from Studio's actual runner records."""
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from . import jobs
from .jig_project import Project


@dataclass(frozen=True)
class Entry:
    pocket: int
    layer: int
    name: str
    digest: str


@dataclass
class RunList:
    file: Path
    jig: Path
    batch: str
    entries: list[Entry]

    @classmethod
    def create(cls, jig_file):
        jig = Path(jig_file).resolve()
        project = Project.read(jig)
        entries = [Entry(i, n, item.name, item.digest) for i in project.layout.queue()
                   for n, item in enumerate(project.layers.get(i, []))]
        if not entries:
            raise ValueError("Assign a checked job to an enabled pocket, then save the jig.")
        batch = uuid4().hex
        file = jig.with_name(f"{jig.stem} {datetime.now():%Y-%m-%d %H%M%S} {batch[:8]}.lpsrunlist")
        jobs.write_json(file, dict(version=1, jig=str(jig), batch=batch, entries=[vars(e) for e in entries]))
        return cls(file, jig, batch, entries)

    @classmethod
    def read(cls, file):
        file = Path(file).resolve()
        data = json.loads(file.read_text(encoding="utf-8"))
        if data["version"] != 1 or not isinstance(data["batch"], str) or not data["batch"]:
            raise ValueError("Unsupported jig run list.")
        entries = [Entry(**row) for row in data["entries"]]
        if not entries or any(type(i) is not int or i < 0 for e in entries for i in (e.pocket,e.layer)):
            raise ValueError("Invalid pocket or layer in the run list.")
        if len({(e.pocket, e.layer) for e in entries}) != len(entries):
            raise ValueError("A pocket and layer appear twice in this list.")
        return cls(file, Path(data["jig"]), data["batch"], entries)

    def tag(self, idx):
        return dict(file=str(self.file), batch=self.batch, row=idx)

    def records(self):
        """Reads only jobs with run instructions; prepared copies and demos do not advance a row."""
        found = {}
        for run in jobs.JOBS_DIR.glob("*/run.json"):
            folder = run.parent
            doc = jobs.read_json(folder / "job.json", {}) or {}
            ref = doc.get("jig_reference") or {}
            tag = ref.get("run_list") or {}
            if tag.get("batch") != self.batch:
                continue
            idx = tag.get("row")
            if type(idx) is not int or not 0 <= idx < len(self.entries):
                continue
            row = self.entries[idx]
            if ref.get("pocket") != row.pocket or ref.get("layer_digest") != row.digest:
                continue
            spec = jobs.read_json(run, {}) or {}
            state = jobs.read_json(folder / "state.json", {}) or {}
            if spec.get("demo") is True or state.get("demo") is True:
                continue
            # Once a send is requested, missing startup/status evidence requires inspection.
            phase = state.get("phase", "unconfirmed")
            if phase == "complete" and state.get("demo") is not False:
                phase = "unconfirmed"
            previous = found.get(idx)
            # A recorded completion survives any earlier stopped attempt.
            if previous and (previous[0] == "complete" or
                             (phase != "complete" and previous[1].name >= folder.name)):
                continue
            found[idx] = phase, folder, ref.get("key")
        return found

    def status(self, idx, project, records):
        row = self.entries[idx]
        current = records.get(idx)
        if current:
            return "Finished" if current[0] == "complete" else f"Review run ({current[0]})"
        if row.pocket >= len(project.layout.slots):
            return "Pocket removed"
        slot = project.layout.slots[row.pocket]
        if not slot.enabled or slot.done:
            return "Skipped"
        layers = project.layers.get(row.pocket, [])
        if row.layer >= len(layers) or layers[row.layer].digest != row.digest:
            return "Assignment changed"
        for other, record in records.items():
            if self.entries[other].pocket == row.pocket:
                if record[0] != "complete":
                    return "Review pocket run"
                if record[2] != project.placement_key(row.pocket):
                    return "Placement changed after printing"
        if any(e.pocket == row.pocket and e.layer < row.layer and records.get(i, ("",))[0] != "complete"
               for i, e in enumerate(self.entries)):
            return "Waiting for earlier layer"
        return "Ready"

    def prepare(self, idx):
        project = Project.read(self.jig)
        status = self.status(idx, project, self.records())
        if status != "Ready":
            raise ValueError(f"This row cannot be prepared. {status}.")
        row = self.entries[idx]
        return project.prepare(self.jig, row.pocket, row.layer, run_list=self.tag(idx))


def check_row(ref, project, resume_folder=None):
    tag = ref["run_list"]
    batch = RunList.read(tag["file"])
    idx = tag["row"]
    if batch.batch != tag["batch"] or batch.jig != Path(ref["file"]) or type(idx) is not int or not 0 <= idx < len(batch.entries):
        raise ValueError("The saved run list differs. Reopen it in Flush tin jig.")
    entry = batch.entries[idx]
    if entry.pocket != ref["pocket"] or entry.digest != ref.get("layer_digest"):
        raise ValueError("The pocket or layer differs from its saved run list.")
    records = batch.records()
    if resume_folder is not None and idx in records:
        phase, folder, _ = records[idx]
        if phase not in ("complete", "unconfirmed") and folder.resolve() == Path(resume_folder).resolve():
            # The normal recovery checks still apply to this same interrupted run.
            records.pop(idx)
    status = batch.status(idx, project, records)
    if status != "Ready":
        raise ValueError(f"Pocket {entry.pocket+1}, layer {entry.layer+1}: {status}. See the jig run list.")
