"""Portable editable Studio jobs. Only the descriptor, source and checked passes travel."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from . import jobs, picture_jobs


MAX_BYTES = 256 * 1024 * 1024
PASS_NAME = re.compile(r"passes/[0-9]{2,3} [A-Za-z0-9 ._-]+\.nc\Z")


def _members(doc):
    if doc.get("app") != "Laser Photo Studio":
        raise ValueError("The package does not contain a Studio job.")
    source = (doc.get("editable_picture") or {}).get("file", "picture.png")
    if source != "picture.png":
        raise ValueError("Portable jobs need a standard picture.png source.")
    passes = [item.get("file", "") for item in doc.get("passes", [])]
    if not passes or len(passes) > 128 or len(passes) != len(set(passes)) or not all(
        isinstance(name, str) and PASS_NAME.fullmatch(name) for name in passes
    ):
        raise ValueError("The package has invalid or unsupported pass paths.")
    return ["job.json", source, *passes]


def export_job(folder: Path, destination: Path) -> None:
    folder, destination = Path(folder), Path(destination)
    picture_jobs.read(folder)
    members = _members(json.loads((folder / "job.json").read_text(encoding="utf-8")))
    if sum((folder / member).stat().st_size for member in members) > MAX_BYTES:
        raise ValueError("The editable package is larger than 256 MB.")
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as handle:
        temp = Path(handle.name)
    try:
        with ZipFile(temp, "w", compression=ZIP_DEFLATED) as zip_file:
            for member in members:
                zip_file.write(folder / member, member)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def import_job(package: Path) -> Path:
    package = Path(package)
    if package.stat().st_size > MAX_BYTES:
        raise ValueError("The editable package is larger than 256 MB.")
    collected = jobs.SETTINGS_FILE.parent / "Imported Jobs"
    with ZipFile(package) as zip_file:
        entries = zip_file.infolist()
        if len(entries) > 130 or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("The editable package exceeds Studio's file limits.")
        names = [item.filename for item in entries]
        if len(names) != len(set(names)) or "job.json" not in names:
            raise ValueError("The package has duplicate files or no job.json.")
        if zip_file.getinfo("job.json").file_size > 4 * 1024 * 1024:
            raise ValueError("The job descriptor is larger than 4 MB.")
        doc = json.loads(zip_file.read("job.json"))
        if not isinstance(doc, dict):
            raise ValueError("The job descriptor must be a Studio job object.")
        members = _members(doc)
        if set(names) != set(members):
            raise ValueError("The package must contain only the source picture and its listed passes.")
        collected.mkdir(parents=True, exist_ok=True)
        # Validate in a staging folder before publishing the import. Native reopening
        # checks sizes, source hash, pass hashes and exact compiled command bodies.
        with tempfile.TemporaryDirectory(dir=collected, prefix=".import-") as staging:
            candidate = Path(staging) / "job"
            for name in members:
                target = candidate / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(name) as archive, target.open("xb") as file:
                    shutil.copyfileobj(archive, file)
            picture_jobs.read(candidate)
            destination = collected / jobs.sha256(package)
            try:
                candidate.rename(destination)
            except FileExistsError:
                # Reuse only an identical checked package, never a modified folder.
                if any(not (destination / name).is_file() or
                       jobs.sha256(candidate / name) != jobs.sha256(destination / name) for name in members):
                    raise ValueError("A previously imported copy changed. Move it aside before importing again.")
    return destination / "job.json"
