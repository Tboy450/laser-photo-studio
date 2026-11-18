"""Reconstruct an editable picture job, validating it before changing app state."""
from __future__ import annotations

import copy
from dataclasses import fields
from pathlib import Path

from . import imaging, jobs, planner, presets, verify

LOOK_KEYS = ('brightness', 'contrast', 'gamma', 'sharpen', 'autolevel', 'negative', 'black_point', 'white_point')


def contained(folder, name):
    path = (folder / name).resolve()
    if not path.is_relative_to(folder.resolve()):
        raise ValueError('Saved file path leaves the job folder.')
    return path


def read(folder):
    folder = Path(folder)
    if folder.is_file():
        folder = folder.parent
    doc = jobs.read_json(folder / 'job.json')
    if not doc or doc.get('app') != 'Laser Photo Studio':
        raise ValueError('Choose a Studio job.json, or open the original picture.')
    if doc.get('grid') or not doc.get('passes') or any(
            p.get('kind', 'rows') not in ('rows', 'features') for p in doc['passes']):
        raise ValueError('This is not a regeneratable picture job. Open its original picture or use G-code check mode.')
    unknown = set(doc['material']) - {f.name for f in fields(presets.Material)}
    if unknown or set(doc.get('look', {})) - set(LOOK_KEYS):
        raise ValueError('Unsupported saved settings; no values were silently discarded: ' + ', '.join(sorted(unknown or set(doc['look'])-set(LOOK_KEYS))))
    mat = presets.Material.from_dict(doc['material'])
    if mat.badge not in presets.BADGES:
        raise ValueError('Unknown material category; no preset was substituted.')
    look = {k: doc.get('look', {}).get(k, getattr(mat, k)) for k in LOOK_KEYS}
    placement = doc.get('placement')
    if not placement or set(placement) - {'fit', 'art_w', 'dx', 'dy'}:
        raise ValueError('Editable placement metadata is missing or unsupported; open the original picture and set its size.')
    # picture.png is saved before tone/dither processing, with orientation already applied.
    image_info = doc.get('editable_picture') or {'file': 'picture.png'}
    picture = contained(folder, image_info['file'])
    if not picture.exists():
        raise ValueError('No editable source picture in this job. Open the original picture; sliders cannot edit G-code alone.')
    if image_info.get('sha256') and jobs.sha256(picture) != image_info['sha256']:
        raise ValueError('The saved editable picture changed; restore the original saved copy.')
    raw = imaging.load_picture(picture)
    job = planner.build_job(raw, mat, planner.Placement(copy.deepcopy(doc['piece']), **placement),
                            look=look, name=doc['name'])
    planner.compile_job(job)
    report = verify.verify_job(job)
    if not report['ok'] or len(job.passes) != len(doc['passes']):
        raise ValueError('Saved picture/settings do not reconstruct a verified job.')
    for saved, rebuilt in zip(doc['passes'], job.passes):
        path = contained(folder, saved['file'])
        if jobs.sha256(path) != saved['sha256']:
            raise ValueError('A saved pass changed after verification: ' + saved['file'])
        if jobs.read_body(path) != rebuilt.commands:
            raise ValueError('The source/settings do not reproduce the saved commands. This may be a baked image or unsupported job; open the original picture to edit.')
    # Neither job metadata nor imported template controls machine connection settings.
    defaults = sorted({f.name for f in fields(presets.Material)} - set(doc['material']))
    provenance = dict(folder=str(folder.resolve()), source=doc.get('source_provenance') or
                      dict(original_picture=doc.get('picture_file'), saved_picture_sha256=jobs.sha256(picture)),
                      defaults_used=defaults, reference=doc.get('based_on_job'),
                      saved_source_transform=doc.get('saved_source_transform'),
                      original_material=copy.deepcopy(doc['material']),
                      keep_proportions=bool(doc.get('keep_proportions', False)))
    return raw, picture, job, report, look, placement, provenance
