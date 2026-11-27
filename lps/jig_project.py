"""A local jig plan refers to checked Studio jobs. No controller is acquired here."""
from __future__ import annotations

import json
import math
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import imaging, job_package, jobs, picture_jobs, planner, tinjig, verify


def command_digest(job):
    body = [[p.key, p.commands] for p in job.passes]
    return hashlib.sha256(json.dumps(body, separators=(",", ":")).encode()).hexdigest()


def rotated_placement(source, placement, rotation):
    dx, dy = placement.get("dx", 0), placement.get("dy", 0)
    for _ in range(rotation):
        dx, dy = dy, -dx
    result = dict(placement, dx=dx, dy=dy)
    if rotation % 2 and placement.get("art_w"):
        if placement["fit"] in ("whole", "art-exact", "saved-whole"):
            result["art_w"] = source.geom.art_h
        elif placement["fit"] == "marks":
            bounds = source.burn_bbox()
            result["art_w"] = bounds[3] - bounds[1]
    return result


@dataclass(frozen=True)
class Layer:
    path: str
    digest: str
    name: str

    @classmethod
    def checked(cls, path):
        path = Path(path).resolve()
        if path.is_dir():
            path /= "job.json"
        folder = job_package.import_job(path) if path.suffix.lower() == ".lpsjob" else path
        if folder.name.lower() != "job.json":
            raise ValueError("Select a Studio .lpsjob or job.json.")
        _, _, job, _, _, _, provenance = picture_jobs.read(folder)
        if provenance.get("jig_reference"):
            raise ValueError("Assign the original layer job. This copy has already been placed in a jig.")
        if job.piece.get("shape") != "circle":
            raise ValueError("Choose a job with a round tin in Size.")
        return cls(str(path), jobs.sha256(path), job.name)

    def read(self):
        path = Path(self.path)
        if jobs.sha256(path) != self.digest:
            raise ValueError(f"{self.name} changed on disk. Remove and add the intended version.")
        return picture_jobs.read(job_package.import_job(path) if path.suffix.lower() == ".lpsjob" else path)

    def verify_files(self):
        path = Path(self.path)
        if jobs.sha256(path) != self.digest:
            raise ValueError(f"{self.name} changed. Assign the revised layer and check the pocket again.")
        if path.suffix.lower() == ".lpsjob":
            return  # The verified picture and passes are all in the hashed archive.
        doc = json.loads(path.read_text(encoding="utf-8"))
        image = doc.get("editable_picture", {})
        if not image.get("sha256"):
            self.read()
            return
        for record in (image, *doc["passes"]):
            if jobs.sha256(picture_jobs.contained(path.parent, record["file"])) != record["sha256"]:
                raise ValueError(f"A saved file in {self.name} changed. Check the original job.")


@dataclass
class Project:
    layout: tinjig.Layout
    layers: dict[int, list[Layer]] = field(default_factory=dict)

    def save(self, path):
        jobs.write_json(path, dict(version=1, layout=self.layout.to_dict(),
                                   layers={str(i): [vars(item) for item in layers]
                                           for i, layers in self.layers.items()}))

    @classmethod
    def read(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if set(data) != {"version", "layout", "layers"} or data["version"] != 1:
            raise ValueError("Unsupported tin jig file.")
        layout = tinjig.Layout.from_dict(data["layout"])
        layers = {}
        for key, items in data["layers"].items():
            i = int(key)
            if str(i) != key or not 0 <= i < len(layout.slots):
                raise ValueError("A layer refers to a missing pocket.")
            layers[i] = [Layer(**v) for v in items]
        return cls(layout, layers)

    def check(self, index, read=Layer.read):
        layers = self.layers.get(index, [])
        if not layers:
            raise ValueError("Assign a checked Studio job to this pocket first.")
        checked = []
        for item in layers:
            raw, _, source, _, look, placement, provenance = read(item)
            piece = tinjig.tin_piece(self.layout, index, source.piece)
            rotation = self.layout.rotation(index)
            positioned = rotated_placement(source, placement, rotation)
            image = imaging.orient(raw, rotation, False)
            job = planner.build_job(image, source.material, planner.Placement(piece, **positioned), look,
                                    name=f"Pocket {index + 1} - {source.name}", legacy_round_margins=True)
            expected = (source.geom.rows, source.geom.cols) if rotation % 2 else (source.geom.cols, source.geom.rows)
            if (job.geom.cols, job.geom.rows) != expected:
                raise ValueError("Turning this image changes its raster size. Review its rotated size in Studio first.")
            if not rotation and (len(job.passes) != len(source.passes) or any(
                    not np.array_equal(a.cells, b.cells) for a, b in zip(job.passes, source.passes))):
                raise ValueError("Placement changed the verified burn map. Check the source size and pocket.")
            planner.compile_job(job)
            report = verify.verify_job(job)
            if not report["ok"] or not report["locations"]:
                raise ValueError(f"Pocket {index + 1}: {verify.summary_text(report)}")
            if checked:
                differences = picture_jobs.registration_conflicts(checked[0][0], job)
                if differences:
                    raise ValueError("Layers do not register. " + " ".join(differences))
            checked.append((job, report, provenance))
        return checked

    def placement_key(self, index):
        slot = self.layout.slots[index]
        values = [self.layout.zero, self.layout.centre(index), self.layout.rotation(index),
                  slot.enabled, slot.done, [vars(item) for item in self.layers.get(index, [])]]
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def prepare(self, path, index, layer_number, *, run_list=None):
        if self.layout.slots[index].done:
            raise ValueError("This pocket is marked complete.")
        if self.read(path).placement_key(index) != self.placement_key(index):
            raise ValueError("Save the jig before preparing this pocket.")
        originals = {item: item.read() for item in self.layers[index]}
        job, report, provenance = self.check(index, originals.__getitem__)[layer_number]
        x, y, u, v = report["travel"]
        tw, th = tinjig.CONTROLLER_TRAVEL
        if max(0,u)-min(0,x) > tw or max(0,v)-min(0,y) > th:
            raise ValueError("This pocket exceeds controller travel from jig zero. Adjust Layout.")
        layer = self.layers[index][layer_number]
        raw, _, source, _, look, placement, _ = originals[layer]
        rotation = self.layout.rotation(index)
        image = imaging.orient(raw, rotation, False)
        layout = self.layout
        datum = [layout.zero, layout.rows, layout.cols, layout.pitch_x, layout.pitch_y, layout.stagger_x]
        ref = dict(file=str(Path(path).resolve()), pocket=index, key=self.placement_key(index), datum=datum,
                   commands=command_digest(job))
        if run_list is not None:
            ref.update(run_list=run_list, layer_digest=layer.digest)
        return jobs.save_job(job, report, picture=image, extra=dict(
            placement=rotated_placement(source, placement, rotation), look=look,
            keep_proportions=provenance["keep_proportions"],
            image_perimeter_border_mm=provenance["image_perimeter_border_mm"],
            pair_check_required=bool(provenance.get("pair_check_required") and len(self.layers[index]) < 2),
            source_provenance=dict(original_job=layer.path, original_sha256=layer.digest),
            jig_reference=ref))

    def neighbouring_pockets(self, index, diameter):
        """Occupied-space warning assumes other enabled pockets carry the same outside diameter."""
        here = self.layout.centre(index)
        return [i + 1 for i in self.layout.enabled() if i != index
                and math.dist(here, self.layout.centre(i)) < diameter - 1e-7]


def validate_placement(ref, job, window=None, resume_folder=None):
    path, index = Path(ref["file"]), ref["pocket"]
    project = Project.read(path)
    if (window is not None and window.winfo_exists() and window.file == path and
            window.project.placement_key(index) != ref["key"]):
        raise ValueError("This pocket has changed in the jig editor. Save and reopen the selected layer in Check.")
    if project.placement_key(index) != ref["key"]:
        raise ValueError("The saved pocket changed. Open its current layer from Tin jig.")
    if "run_list" in ref:
        from .jig_runlist import check_row
        check_row(ref, project, resume_folder)
    for layer in project.layers[index]:
        layer.verify_files()
    if command_digest(job) != ref["commands"]:
        raise ValueError("The checked commands differ from the saved pocket. Update the source layer in Tin jig.")
