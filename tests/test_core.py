import math
import os
import tempfile
import unittest
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from lps import imaging, jobs, planner, presets, verify
from lps.planner import Placement

PROJECT = Path(r"C:\Users\Heemi\Documents\Codex\2026-10-25\got")


def sample_picture(w=400, h=300):
    im = Image.new("L", (w, h), 255)
    a = np.tile(np.linspace(30, 250, w), (h, 1)).astype(np.uint8)
    im.paste(Image.fromarray(a), (0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((40, 40, 160, 160), fill=20)
    d.rectangle((200, 60, 360, 90), fill=0)
    d.text((210, 150), "NORTH POLE 2026", fill=0)
    d.line((20, 260, 380, 200), fill=0, width=2)
    return im


def piece(w=40.0, h=30.0, **kw):
    p = dict(presets.PIECES["custom"])
    p.update(w=w, h=h, margins=(2.0, 2.0, 2.0, 2.0), keepouts=[])
    p.update(kw)
    return p


def small_job(key="pine-layers", w=40.0, h=30.0, **pkw):
    mat = next(m for m in presets.BUILTIN if m.key == key)
    job = planner.build_job(sample_picture(), mat, Placement(piece(w, h, **pkw)), name=f"t-{key}")
    return planner.compile_job(job)


class Components(unittest.TestCase):
    def test_labels_match_flood_fill(self):
        rng = np.random.default_rng(3)
        for _ in range(25):
            m = rng.random((rng.integers(1, 30), rng.integers(1, 30))) < 0.5
            lab, n = imaging.label_components(m)
            seen = {}
            H, W = m.shape
            for r in range(H):
                for c in range(W):
                    if m[r, c]:
                        for rr, cc in ((r + 1, c), (r, c + 1)):
                            if rr < H and cc < W and m[rr, cc]:
                                self.assertEqual(lab[r, c], lab[rr, cc])
                        seen.setdefault(lab[r, c], 0)
            self.assertEqual(len(seen), n)
            self.assertTrue((lab[~m] == 0).all())


@unittest.skipUnless((PROJECT / "outputs/north-pole-mural/layout-B-levels.png").exists(), "project files absent")
class ProvenPlank(unittest.TestCase):
    def test_reproduces_north_pole_plan(self):
        pic = imaging.load_picture(PROJECT / "outputs/north-pole-mural/operator-design.webp")
        mat = next(m for m in presets.BUILTIN if m.key == "pine-layers")
        job = planner.build_job(pic, mat, Placement(dict(presets.PIECES["plank76"])))
        theirs = np.asarray(Image.open(PROJECT / "outputs/north-pole-mural/layout-B-levels.png"))
        mapped = np.select([theirs == 0, theirs == 2, theirs == 3, theirs == 4], [0, 1, 2, 3], 9)
        self.assertTrue((mapped == job.levels).all())
        self.assertEqual([p.key for p in job.passes], ["L1", "L1thin", "L2", "L3"])
        self.assertEqual(int((job.passes[2].cells > 0).sum()), 180922)   # logged L2 size


class Styles(unittest.TestCase):
    def test_every_preset_compiles_and_verifies(self):
        for mat in presets.BUILTIN:
            with self.subTest(mat.key):
                job = small_job(mat.key, 30.0, 22.0)
                rep = verify.verify_job(job)
                self.assertTrue(rep["ok"], rep["passes"][0]["problems"][:3])
                self.assertGreater(rep["cells"], 0)
                for p in job.passes:
                    self.assertEqual(p.commands[0], "M5 S0")
                    self.assertEqual(p.commands[-1], "M5 S0")
                    for c in p.commands:
                        self.assertFalse(c.startswith(("G0", "$", "M3", "G10", "G92")), c)
                    smax = max(int(c.split("S")[-1]) for c in p.commands if c.startswith("G1"))
                    self.assertLessEqual(smax, 1000)

    def test_negative_material_burns_light_parts(self):
        job = small_job("anodized-dots", 30.0, 22.0)
        cells = job.passes[0].cells > 0
        g = job.gray  # already inverted: low = burn
        self.assertGreater(cells[g < 60].mean(), cells[g > 200].mean())

    def test_verify_catches_tampering(self):
        job = small_job("anodized-dots", 30.0, 22.0)
        p = job.passes[0]
        k = next(i for i, c in enumerate(p.commands) if c.startswith("G1") and not c.endswith(" S0"))
        for bad in (p.commands[:k + 1] + [p.commands[k - 1].replace("S0", "S0"), p.commands[k]] + p.commands[k + 1:],
                    [c.replace("S500", "S900") for c in p.commands],
                    p.commands[:3] + ["G0 X0 Y0"] + p.commands[3:]):
            self.assertFalse(verify.verify_pass(job, p, bad)["ok"])


class Placement_(unittest.TestCase):
    def test_keepouts_and_corners(self):
        pc = piece(60.0, 60.0, corner=10.0, keepouts=[dict(kind="circle", x=30.0, y=30.0, r=6.0)])
        mat = next(m for m in presets.BUILTIN if m.key == "logo-wood")
        black = Image.new("L", (300, 300), 0)
        job = planner.compile_job(planner.build_job(black, mat, Placement(pc, fit="fill")))
        g = job.geom
        rr, cc = np.nonzero(job.passes[0].cells)
        xs, ys = g.x0 + (cc + 0.5) * g.pitch, g.yt - (rr + 0.5) * g.pitch
        self.assertTrue(((xs - 30) ** 2 + (ys - 30) ** 2 > 36).all())
        self.assertFalse(((xs < 3) & (ys < 3)).any())   # rounded corner left bare
        self.assertTrue(verify.verify_job(job)["ok"])

    def test_test_grid(self):
        mat = next(m for m in presets.BUILTIN if m.key == "basswood-dots")
        job = planner.compile_job(planner.build_test_grid(mat, Placement(piece(120.0, 70.0)), [40, 60, 80],
                                                          [3000, 4500, 6000]))
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"], rep["passes"][0]["problems"][:3])
        fs = {int(c.split()[3][1:]) for c in job.passes[0].commands if c.startswith("G1") and not c.endswith(" S0")}
        self.assertEqual(fs, {3000, 4500, 6000})
        self.assertTrue(job.passes[1].cells.any())

    def test_perimeter_points(self):
        pts = planner.perimeter_points((0, 0, 50, 20), spacing=20)
        self.assertEqual(pts[0][:2], (0, 0))
        self.assertIn((50, 20, "upper-right"), pts)
        self.assertGreater(len(pts), 4)


class SaveLoad(unittest.TestCase):
    def test_files_round_trip(self):
        job = small_job("pine-layers")
        rep = verify.verify_job(job)
        with tempfile.TemporaryDirectory() as td:
            folder = jobs.save_job(job, rep, folder=Path(td) / "job")
            doc = jobs.read_json(folder / "job.json")
            self.assertTrue(doc["verified"])
            self.assertNotIn("LaserGRBL", (folder / "README.txt").read_text(encoding="utf-8"))
            for p, meta in zip(job.passes, doc["passes"]):
                self.assertEqual(jobs.read_body(folder / meta["file"]), p.commands)
                self.assertEqual(jobs.sha256(folder / meta["file"]), meta["sha256"])
            text = jobs.lasergrbl_path(folder).read_text()
            self.assertTrue(jobs.lasergrbl_path(folder).name.endswith(" - all passes.nc"))
            self.assertIn("Look: pine", text)
            self.assertIn("M5 S0", text.splitlines()[-1])
            self.assertNotIn("$H", text)


class Samples(unittest.TestCase):
    def test_every_proven_preset_has_photos(self):
        from lps import samples
        for m in presets.BUILTIN:
            items, note = samples.for_material(m)
            if m.badge == "PROVEN":
                self.assertTrue(items, m.key)
                self.assertTrue(any(s.kind in ("result", "test") for s in items), m.key)
                self.assertTrue(note, m.key)
            for s in items:
                self.assertTrue(s.path.exists(), s.path)
                self.assertIn(s.kind, samples.KINDS)
                self.assertTrue(s.title and s.caption, s.path)
                self.assertEqual(samples.thumbnail(s.path, (128, 96)).size[0] <= 128, True)

    def test_saved_preset_keeps_photos_and_user_photos_round_trip(self):
        from lps import samples
        base = next(m for m in presets.BUILTIN if m.key == "pine-layers")
        mine = base.copy(key="my-test", name="My test", badge="MINE", based_on="pine-layers")
        with tempfile.TemporaryDirectory() as td:
            old = samples.USER_DIR
            samples.USER_DIR = Path(td) / "samples"
            try:
                items, note = samples.for_material(mine)
                self.assertEqual(len(items), len(samples.for_material(base)[0]))
                self.assertIn("saved from", note)
                pic = Path(td) / "grid.png"
                Image.new("RGB", (3000, 2000), (200, 150, 100)).save(pic)
                added = samples.add_user_photo("my-test", pic, "Cherry grid 45%", "test", "top row best")
                with Image.open(added.path) as im:
                    self.assertLessEqual(max(im.size), samples.MAX_SIDE)
                after, _ = samples.for_material(mine)
                self.assertEqual(len(after), len(items) + 1)
                self.assertTrue(after[-1].user)
                self.assertEqual(after[-1].title, "Cherry grid 45%")
                samples.remove_user_photo(after[-1])
                self.assertEqual(len(samples.for_material(mine)[0]), len(items))
                self.assertFalse(added.path.exists())
            finally:
                samples.USER_DIR = old


class Explanations(unittest.TestCase):
    def test_studio_native_guide_and_energy(self):
        card = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
        slower = card.copy(feed=1800)
        self.assertAlmostEqual(presets.energy(slower) / presets.energy(card), 2500 / 1800)
        from lps import helptext
        topics = helptext.topics(card)
        titles = [t for t, _ in topics]
        self.assertIn("Too light or too dark?", titles)
        self.assertIn("Negative & previews", titles)
        self.assertNotIn("Using LaserGRBL", titles)
        self.assertTrue(all(body.strip() for _, body in topics))


if __name__ == "__main__":
    unittest.main()
