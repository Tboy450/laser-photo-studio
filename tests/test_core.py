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

    def test_start_point_on_a_picked_spot(self):
        corner = small_job("anodized-dots", 40.0, 30.0)
        spot = small_job("anodized-dots", 40.0, 30.0, origin="spot", spot=[12.5, 8.0])
        self.assertEqual(planner.piece_rect(spot.piece), (-12.5, -8.0, 27.5, 22.0))
        self.assertAlmostEqual(spot.geom.x0, corner.geom.x0 - 12.5, places=6)   # same place on the piece,
        self.assertAlmostEqual(spot.geom.yt, corner.geom.yt - 8.0, places=6)    # measured from the spot
        for a, b in zip(corner.passes, spot.passes):
            np.testing.assert_array_equal(a.cells, b.cells)
        self.assertTrue(verify.verify_job(spot)["ok"])
        self.assertIn("12.5 mm from the piece's left edge", jobs.origin_text(spot.piece))

    def test_toy_car_windows_are_no_burn_zones(self):
        black = Image.new("L", (400, 140), 0)
        mat = next(m for m in presets.BUILTIN if m.key == "anodized-dots").copy(negative=False)
        for body in presets.CAR_BODIES:
            v = presets.car_values(body)
            pc = presets.car_piece(v)
            self.assertEqual(len(pc["keepouts"]), 2 if presets.CAR_BODIES[body]["rear"] else 1, body)
            job = planner.compile_job(planner.build_job(black, mat, Placement(pc, fit="fill")))
            g = job.geom
            rr, cc = np.nonzero(sum(p.cells for p in job.passes))
            xs, ys = g.x0 + (cc + 0.5) * g.pitch - g.piece_rect[0], g.yt - (rr + 0.5) * g.pitch - g.piece_rect[1]
            for k in pc["keepouts"]:    # nothing burns on the glass
                inside = (xs > k["x"]) & (xs < k["x"] + k["w"]) & (ys > k["y"]) & (ys < k["y"] + k["h"])
                self.assertFalse(inside.any(), (body, k))
            self.assertTrue(verify.verify_job(job)["ok"], body)
        # The Mustang: windshield 25.9 mm back from the nose; start point on its front edge, on the centerline.
        v = presets.car_values("mustang")
        self.assertEqual(presets.car_piece(v)["spot"], [round(86.36 - 25.9, 2), 15.24])
        left = presets.car_piece(dict(v, front="left"))
        self.assertEqual(left["spot"], [25.9, 15.24])
        right_ws, left_ws = presets.car_piece(v)["keepouts"][0], left["keepouts"][0]
        self.assertAlmostEqual(right_ws["x"] + right_ws["w"], 86.36 - left_ws["x"], places=2)   # mirrored
        self.assertEqual(presets.car_piece(dict(v, start="nose"))["spot"], [86.36, 15.24])

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
            for p, meta in zip(job.passes, doc["passes"]):
                self.assertEqual(jobs.read_body(folder / meta["file"]), p.commands)
                self.assertEqual(jobs.sha256(folder / meta["file"]), meta["sha256"])
            text = jobs.lasergrbl_path(folder).read_text()
            self.assertTrue(jobs.lasergrbl_path(folder).name.endswith(" - all passes.nc"))
            self.assertIn("Look: pine", text)
            self.assertIn("M5 S0", text.splitlines()[-1])
            self.assertNotIn("$H", text)
            from lps import gcodeinfo
            info = gcodeinfo.analyse(jobs.lasergrbl_path(folder))
            self.assertEqual(info["kind"], "fill")
            self.assertAlmostEqual(info["row_pitch"], job.geom.pitch, places=3)


class FillOrOutline(unittest.TestCase):
    """The Hot Wheels stripes came out as outlines because LaserGRBL's Vectorize traces edges."""

    def analyse(self, moves):
        from lps import gcodeinfo
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "t.nc"
            f.write_text("G21 G90\nM4 S0\n" + "\n".join(moves) + "\nM5 S0\n")
            return gcodeinfo.analyse(f)

    @staticmethod
    def path(points, s=600):
        (x0, y0), rest = points[0], points[1:]
        return [f"G0 X{x0:.3f} Y{y0:.3f}"] + [f"G1 X{x:.3f} Y{y:.3f} S{s}" for x, y in rest] + ["G1 S0"]

    def test_vectorized_stripes_and_circle_are_outlines(self):
        moves = []
        for i in range(3):    # three long stripes, traced round their edges
            y = 5 + 4 * i
            moves += self.path([(0, y), (80, y), (80, y + 2), (0, y + 2), (0, y)])
        moves += self.path([(100 + 10 * math.cos(a), 10 + 10 * math.sin(a))
                            for a in np.linspace(0, 2 * math.pi, 73)])
        info = self.analyse(moves)
        self.assertEqual(info["kind"], "outline")
        from lps import gcodeinfo
        text, warn = gcodeinfo.describe_fill(info)
        self.assertTrue(warn)
        self.assertIn("OUTLINES ONLY", text)

    def test_rows_fill_in_any_direction(self):
        rows = []
        for i in range(60):   # line-to-line rows, 0.1 mm apart
            y = i * 0.1
            rows += [f"G0 X0 Y{y:.3f}", f"G1 X20 S500", "G1 S0"]
        info = self.analyse(rows)
        self.assertEqual((info["kind"], info["row_pitch"]), ("fill", 0.1))
        diag = []
        for i in range(60):   # LaserGRBL's diagonal direction
            o = i * 0.1
            diag += self.path([(o, 0), (o + 10, 10)])
        self.assertEqual(self.analyse(diag)["kind"], "fill")

    def test_hatch_with_border_is_mixed(self):
        moves = []
        for i in range(41):   # 20 mm hatch rows, 0.1 mm apart, plus a round border traced 5 times
            moves += self.path([(0, i * 0.1), (20, i * 0.1)])
        moves += self.path([(10 + 8 * math.cos(a), 2 + 8 * math.sin(a)) for a in np.linspace(0, 10 * math.pi, 361)])
        info = self.analyse(moves)
        self.assertEqual(info["kind"], "mixed")
        self.assertLess(info["fill_share"], 0.85)


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

    def test_anodized_shows_goku_card_and_hot_wheels_lessons(self):
        from lps import samples
        card = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
        items, note = samples.for_material(card)
        titles = [s.title for s in items]
        self.assertIn("Goku 'Kamehameha' card", titles)
        lessons = [s for s in items if s.kind == "lesson"]
        self.assertGreaterEqual(len(lessons), 3)
        self.assertTrue(all(s.title.startswith("What went wrong") for s in lessons))
        self.assertIn("Hot Wheels", note)

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
    def test_lasergrbl_recipes_and_energy(self):
        card = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
        r = presets.lasergrbl_recipe(card)
        self.assertIn("1bit BW Dithering", r)
        self.assertIn("Floyd-Steinberg", r)
        self.assertIn("S-MAX 500 (= 50%)", r)
        self.assertIn("Quality 10 lines/mm", r)
        self.assertIn("invert", r)          # Negative is on for anodized photos
        pine = next(m for m in presets.BUILTIN if m.key == "pine-layers")
        self.assertIn("layer files", presets.lasergrbl_recipe(pine))
        slower = card.copy(feed=1800)
        self.assertAlmostEqual(presets.energy(slower) / presets.energy(card), 2500 / 1800)
        from lps import helptext
        titles = [t for t, _ in helptext.topics(card)]
        self.assertIn("Too light or too dark?", titles)
        self.assertIn("Backgrounds & stickers", titles)
        self.assertTrue(all(body.strip() for _, body in helptext.topics(card)))
        for _, body in helptext.topics(card):   # every Guide picture exists
            for line in body.splitlines():
                if line.strip().startswith("[image:"):
                    self.assertTrue((jobs.APP_DIR / line.strip()[7:-1]).exists(), line)
        import re
        for f in (jobs.APP_DIR / "lps").glob("*.py"):    # every 'open the Guide at...' link names a real topic
            for name in re.findall(r'open_help\("([^"]+)"\)', f.read_text(encoding="utf-8")):
                self.assertIn(name, titles, f.name)

    def test_every_theme_is_complete_and_readable(self):
        from lps.ui_common import THEMES

        def lum(h):
            r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

        def contrast(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)

        self.assertEqual(len({frozenset(t) for t in THEMES.values()}), 1)     # every theme has every role
        for key, t in THEMES.items():
            need = 7.0 if key not in ("light", "dragonfly") else 4.5          # WCAG AAA for the contrast pairs
            self.assertGreaterEqual(contrast(t["ink"], t["bg"]), need, key)
            self.assertGreaterEqual(contrast(t["ink"], t["field"]), need, key)
            self.assertGreaterEqual(contrast(t["header_ink"], t["header"]), need, key)
            self.assertGreaterEqual(contrast(t["select_ink"], t["select"]), 4.5, key)
            for role in ("muted", "ok", "warn", "bad", "blue"):              # WCAG AA for coloured text
                self.assertGreaterEqual(contrast(t[role], t["bg"]), 4.5, (key, role))
            for role in ("ok", "bad"):                                        # status text on its own badge
                self.assertGreaterEqual(contrast(t[role], t[role + "_bg"]), 4.5, (key, role))
            self.assertGreaterEqual(contrast(t["grid"], t["canvas"]), 3.0, key)
            if key not in ("light", "dragonfly"):     # a contrast pair's grid is its text colour, with a backing line
                self.assertEqual(t["grid"], t["ink"], key)
                self.assertGreaterEqual(contrast(t["grid"], t["grid_back"]), 7.0, key)
            self.assertGreaterEqual(contrast(t["art"], t["canvas"]), 3.0, key)    # markers on the preview
            self.assertGreaterEqual(contrast(t["head"], t["canvas"]), 3.0, key)

    def test_grid_spacing_follows_the_zoom(self):
        from lps.preview import grid_step
        self.assertEqual(grid_step(3.5), 20)      # a 7 x 6 in plank fills the preview: coarse squares
        self.assertEqual(grid_step(8.6), 5)       # a toy car: finer
        self.assertEqual(grid_step(80.0), 0.5)    # tiny piece
        self.assertEqual(grid_step(0.1), 100)     # never fails on a huge piece

    def test_settings_show_other_units(self):
        from lps.app import adv_hint
        self.assertEqual(adv_hint("power", "60"), "= S600")
        self.assertEqual(adv_hint("pitch", "0.1"), "= 254 lines/in")
        self.assertEqual(adv_hint("feed", "2540"), "= 100 in/min")
        self.assertEqual(adv_hint("pitch", "abc"), "")

    def test_edge_burn_spots_a_burning_background(self):
        from lps import simulate
        logo = Image.new("L", (300, 200), 255)
        ImageDraw.Draw(logo).rectangle((60, 60, 240, 140), fill=0)
        wood = next(m for m in presets.BUILTIN if m.key == "pine-layers")
        card = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
        pl = Placement(piece(40.0, 30.0))
        self.assertLess(simulate.edge_burn(planner.build_job(logo, wood, pl)), 0.1)      # white bg, no Negative
        self.assertGreater(simulate.edge_burn(planner.build_job(logo, card, pl)), 0.9)   # Negative burns the white
        self.assertLess(simulate.edge_burn(planner.build_job(logo, card.copy(negative=False), pl)), 0.1)


if __name__ == "__main__":
    unittest.main()
