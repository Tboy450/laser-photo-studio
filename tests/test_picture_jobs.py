"""Native picture jobs retain editable source and settings; no physical serial access."""
import copy
import json
import tempfile
import time
import tkinter as tk
import unittest
from dataclasses import asdict
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import numpy as np
from PIL import Image, ImageDraw

from lps import imaging, job_package, jobs, machine, picture_jobs, planner, presets, run_history, sample_library, simulate, verify
from lps.app import App
from lps.dialogs import RecoveryDialog


class PictureJobUI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.patches=[patch.object(jobs,'SETTINGS_FILE',self.path/'settings.json'),
                      patch.object(jobs,'LOCK_FILE',self.path/'sender.lock'),
                      patch.object(jobs,'JOBS_DIR',self.path/'jobs'),
                      patch.object(jobs,'launch_runner',side_effect=AssertionError('No runner')),
                      patch.object(machine.SerialWire,'open',side_effect=AssertionError('No hardware'))]
        for p in self.patches:p.start()
        self.root=tk.Tk();self.root.withdraw()
        self.a=App(self.root,SimpleNamespace(demo=True,picture=None,perimeter=None))
        image=Image.fromarray(np.tile(np.arange(256,dtype=np.uint8),(210,1)))
        mat=next(m for m in presets.BUILTIN if m.key=='slate').copy(
            key='imported-test',name='Imported editable photo',pitch=.2,feed=3500,power=500,
            row_feed=6000,hop_feed=2400,scan_direction='forward',runup=2,interlace=2)
        piece=dict(name='Measured test piece',shape='rect',w=40.,h=36.,origin='spot',spot=[7,6],
                   margins=[1.,2.,3.,4.],corner=1.,keepouts=[dict(kind='rect',x=5,y=7,w=2,h=3)])
        self.look=dict(brightness=0,contrast=13,gamma=1.,sharpen=30,negative=True,autolevel=False,
                       black_point=0,white_point=255)
        self.place=dict(art_w=28.,fit='whole',dx=.5,dy=-.75)
        self.job=planner.build_job(image,mat,planner.Placement(piece,**self.place),look=self.look,name='editable-test')
        planner.compile_job(self.job)
        self.folder=jobs.save_job(self.job,verify.verify_job(self.job),picture=image,
            folder=self.path/'input',extra=dict(look=self.look,placement=self.place,keep_proportions=True))

    def tearDown(self):
        for task in self.root.tk.call('after','info'):self.root.tk.call('after','cancel',task)
        self.root.destroy()
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def pump(self):
        end=time.monotonic()+15
        while time.monotonic()<end:
            self.root.update()
            if self.a.job is not None and not self.a.layout_pending:return
            time.sleep(.01)
        self.fail('Layout did not finish')

    def compile(self):
        planner.compile_job(self.a.job)
        self.a.report=verify.verify_job(self.a.job);self.a.compiled_gen=self.a.gen
        self.assertTrue(self.a.report['ok'])

    def test_oversize_whole_picture_preserves_ratio_and_can_open_old_checked_grid(self):
        image = Image.new('L', (200, 100), 0)
        piece = dict(self.job.piece, w=48, h=48, margins=(0, 0, 0, 0), shape='rect', keepouts=[])
        mat = self.job.material.copy(pitch=.15, negative=False)
        place = dict(fit='whole', art_w=90, dx=0, dy=0)
        g = planner.layout(image.size, planner.Placement(piece, **place), mat.pitch)
        self.assertEqual((g.art_w, g.art_h), (48, 24))
        legacy = planner.Placement(piece, **dict(place, fit='saved-whole'))
        old = planner.compile_job(planner.build_job(image, mat, legacy))
        self.assertEqual(old.geom.art_h, 45)
        folder = jobs.save_job(old, verify.verify_job(old), picture=image, extra=dict(placement=place))
        self.assertTrue(self.a.open_saved_job(folder))
        self.assertEqual(self.a.job.passes[0].commands, old.passes[0].commands)
        self.assertEqual(self.a.fit_var.get(), 'saved-whole')
        self.a.fit_var.set('whole')
        self.a._fit_changed()
        self.pump()
        self.assertEqual(self.a.job.geom.art_h, 24)
        self.a.artw_var.set('22.5')
        self.a._artw_edited()
        self.a._fit_changed()
        self.assertEqual(self.a.art_w, 22.5)

    def test_whole_picture_material_and_piece_matrix(self):
        a = self.a
        for material in presets.BUILTIN:
            a.select_material(material.key)
            for pitch in (.15, .10):
                a._customised(pitch=pitch)
                for key in presets.PIECES:
                    a.set_piece(key, user=False)
                    a.fit_var.set("whole")
                    a.artw_var.set("500")
                    a._artw_edited()
                    recipe, placement, _ = a.build_params()
                    self.assertEqual((recipe.key, recipe.pitch), (material.key, pitch))
                    self.assertEqual(placement.piece, presets.PIECES[key])
                    for w, h in ((200, 100), (100, 200)):
                        with self.subTest(material=material.key, piece=key, pitch=pitch, image=(w, h)):
                            grid = planner.layout((w, h), placement, pitch)
                            x0, y0, x1, y1 = grid.usable_rect
                            scale = min(500 / w, (x1-x0) / w, (y1-y0) / h)
                            self.assertAlmostEqual(grid.art_w, w * scale, delta=pitch)
                            self.assertAlmostEqual(grid.art_h, h * scale, delta=pitch)
                            self.assertLessEqual(grid.art_w, x1-x0 + 1e-8)
                            self.assertLessEqual(grid.art_h, y1-y0 + 1e-8)

    def test_exact_toggle_across_material_and_stock_presets(self):
        a = self.a
        a.picture = Image.new("L", (80,40), 74)
        for material in presets.BUILTIN:
            a.select_material(material.key)
            for key, piece in presets.PIECES.items():
                with self.subTest(material=material.key, piece=key):
                    a.set_piece(key, user=False)
                    a.proportions_var.set(True)
                    a.artw_var.set("12")
                    a._artw_edited()
                    before = a.build_params()[1]
                    a.exact_btn.invoke()
                    recipe, during, look = a.build_params()
                    if piece.get("shape") == "circle" or piece.get("outline"):
                        self.assertEqual(during.piece, before.piece)
                        self.assertEqual(during.fit, "art-exact")
                    else:
                        self.assertEqual(during.fit, "exact")
                    job = planner.compile_job(planner.build_job(a.picture, recipe, during, look))
                    self.assertAlmostEqual(job.geom.art_w / job.geom.art_h, 2)
                    self.assertTrue(verify.verify_job(job)["ok"])
                    a.exact_btn.invoke()
                    self.assertEqual(a.build_params()[1], before)

    def test_round_exact_restores_previous_engraved_width_after_file_size(self):
        a = self.a
        a.set_piece("tin50")
        a.fit_var.set("marks")
        a._fit_changed()
        a.artw_var.set("39")
        a._artw_edited()
        a.dx, a.dy = .25, -.5
        before = a.build_params()[1]
        a.exact_btn.invoke()
        a._exact_toggled((20, 10))
        during = a.build_params()[1]
        self.assertEqual(during, planner.Placement(before.piece, fit="art-exact", art_w=20, dx=.25, dy=-.5))
        a.exact_btn.invoke()
        self.assertEqual(a.build_params()[1], before)

    def test_one_measured_rim_survives_exact_and_limits_the_burn_map(self):
        a = self.a
        a.set_piece("tin50")
        a.rim_var.set("1.45")
        a._piece_edited()
        self.assertEqual(a.piece["margins"], (1.45,) * 4)
        self.assertIn("47.9 mm", a.rim_note.cget("text"))
        a.exact_btn.invoke()
        material, placement, look = a.build_params()
        job = planner.build_job(Image.new("L", (80,80), 0), material, placement, look)
        self.assertEqual(job.geom.usable_rect, (-23.95,-23.95,23.95,23.95))
        self.assertFalse(job.allowed[0, 0])
        self.assertTrue(job.allowed[job.geom.rows//2, job.geom.cols//2])
        self.assertEqual(a.piece["shape"], "circle")
        a.rim_var.set("26")
        a._piece_edited()
        self.assertEqual(a.piece["margins"], (1.45,) * 4)
        asymmetric = copy.deepcopy(placement)
        asymmetric.piece["margins"] = (1, 2, 1, 1)
        with self.assertRaisesRegex(ValueError, "one unprinted rim"):
            planner.build_job(Image.new("L",(8,8)), material, asymmetric)
        tiny = Image.new("L", (16, 16), 60)
        old_place = planner.Placement(asymmetric.piece, art_w=6)
        old = planner.compile_job(planner.build_job(tiny, material, old_place, look, legacy_round_margins=True))
        folder = jobs.save_job(old, verify.verify_job(old), picture=tiny,
                               extra=dict(placement=dict(fit="whole", art_w=6, dx=0, dy=0), look=look))
        self.assertTrue(a.open_saved_job(folder))
        self.assertEqual(a.job.passes[0].commands, old.passes[0].commands)
        self.assertEqual(a.rim_var.get(), "")
        self.assertIn("Unequal saved margins", a.rim_note.cget("text"))

    def test_transparent_negative_and_legacy_saved_commands(self):
        source = self.path / "transparent.png"
        image = Image.new("RGBA", (40, 20), (121, 37, 46, 0))
        image.paste((255, 255, 255, 255), (10, 5, 30, 15))
        image.putpixel((20, 10), (0, 0, 0, 255))
        image.save(source)
        a = self.a
        self.assertTrue(a.open_picture(source))
        self.assertEqual(a.picture.mode, "LA")
        self.assertEqual(a.picture.getpixel((20,10)), (0, 255))
        placement = dict(fit="whole", art_w=6, dx=0, dy=0)
        piece = dict(self.job.piece, margins=(0,)*4, keepouts=[], corner=0)
        place = planner.Placement(piece, **placement)
        for material in presets.BUILTIN:
            for negative in (True, False):
                with self.subTest(material=material.key, negative=negative):
                    job = planner.build_job(a.picture, material.copy(pitch=.15), place,
                                            look={"negative": negative})
                    for p in job.passes:
                        self.assertFalse(p.cells[:5].any() or p.cells[15:].any())
                        self.assertFalse(p.cells[:, :10].any() or p.cells[:, 30:].any())
        mat = self.job.material.copy(style="floyd", pitch=.15)
        for legacy in (True, False):
            raw = imaging.load_picture(source, flatten_on_white=legacy)
            plan = planner.compile_job(planner.build_job(raw, mat, place, self.look))
            folder = jobs.save_job(plan, verify.verify_job(plan), picture=raw, folder=self.path / str(legacy),
                                   extra=dict(placement=placement, look=self.look))
            if legacy:
                image.save(folder / "picture.png")
                doc = jobs.read_json(folder/"job.json")
                doc["editable_picture"]["sha256"] = jobs.sha256(folder/"picture.png")
                jobs.write_json(folder/"job.json", doc)
            reopened, _, rebuilt, _, _, _, provenance = picture_jobs.read(folder)
            self.assertEqual(provenance["legacy_alpha"], legacy)
            self.assertEqual(reopened.mode, "L" if legacy else "LA")
            self.assertEqual(rebuilt.passes[0].commands, plan.passes[0].commands)
            self.assertEqual(bool(rebuilt.passes[0].cells[0].any()), legacy)

    def test_soft_alpha_rotated_crop_and_negative_grayscale(self):
        source = Image.new("LA", (40, 20), (255, 0))
        source.paste((255, 128), (10, 5, 30, 15))
        source.putpixel((20, 10), (255, 255))
        other = source.copy()
        other.paste((0, 0), (0, 0, 40, 5))
        for image in (source, other):
            grid = imaging.to_grid(image, 40, 20, negative=True)
            self.assertEqual((grid[0, 20], grid[8, 20], grid[10, 20]), (255, 127, 0))
        crop = (2, 6, 18, 35)
        def adjusted(image):
            return imaging.to_grid(imaging.orient(image, 1, True), 23, 42, crop,
                                   negative=True, brightness=14, contrast=19, sharpen=70)
        np.testing.assert_array_equal(adjusted(source), adjusted(other))

    def test_invalid_fields_restore_accepted_recipe_and_piece(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        old_piece = copy.deepcopy(a.piece)
        gen = a.gen
        a.pw_var.set('48')
        a.margin_vars[0].set('x')
        a._piece_edited()
        self.assertEqual(a.piece, old_piece)
        self.assertEqual(a.gen, gen)
        self.assertEqual(float(a.pw_var.get()), old_piece['w'])
        feed = a.mat.feed
        a.adv_vars['feed'][0].set('1900')
        a.adv_vars['pitch'][0].set('NaN')
        a._adv_changed()
        self.assertEqual(a.mat.feed, feed)
        self.assertEqual(float(a.adv_vars['feed'][0].get()), feed)
        self.assertEqual(a.gen, gen)
        a.adv_vars['feed'][0].set('1900')
        a._adv_changed()
        self.assertEqual(a.mat.feed, 1900)
        self.assertEqual(a.piece, old_piece)
        self.pump()

    def test_saves_in_same_second_keep_independent_histories(self):
        import datetime
        frozen = datetime.datetime(2026, 11, 23, 10, 11, 12)
        with patch.object(jobs.dt, 'datetime') as clock:
            clock.now.return_value = frozen
            first = jobs.save_job(self.job, {})
            jobs.write_json(first / 'state.json', {'phase': 'complete'})
            second = jobs.save_job(self.job, {})
        self.assertNotEqual(first, second)
        self.assertFalse((second / 'state.json').exists())
        self.assertEqual(jobs.read_json(first / 'state.json')['phase'], 'complete')

    def test_no_marks_explained_and_not_ready_to_start(self):
        a = self.a
        image = Image.new('L', (20, 20), 255)
        placement = planner.Placement(self.job.piece)
        mat = self.job.material.copy(style='threshold', negative=False)
        a.job = planner.compile_job(planner.build_job(image, mat, placement))
        a.report = verify.verify_job(a.job)
        a.compiled_gen = a.gen
        self.assertIn('Empty engraving', verify.summary_text(a.report))
        self.assertFalse(a.ready_items()[1][0])
        self.assertIn('no marks', a.ready_items()[1][2])

    def test_exact_toggle_restores_saved_placement_and_expires_old_checks(self):
        def walk(parent):
            for child in parent.winfo_children():
                yield child
                yield from walk(child)

        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        a.origin_set = True
        a.completed_checks["image"] = a.check_key()
        exact = next(w for w in walk(a.pages[2].inner) if isinstance(w, ttk.Checkbutton)
                     and w.cget("text") == "Use exact image size")
        exact.invoke()
        self.assertFalse(a.origin_set)
        self.assertFalse(a.completed_checks)
        self.assertAlmostEqual(a.piece["w"] / a.piece["h"], a.picture.width / a.picture.height)
        self.pump()
        self.compile()
        a.update_check_panel()
        summary = str(a.check_text.cget("text"))
        self.assertIn("Saved setup: Fit: Whole image", summary)
        self.assertIn("Current setup:\nFit: Exact size", summary)
        self.assertIn("Total travel (includes beam-off run-up and return)", summary)
        exact.invoke()
        self.pump()
        self.compile()
        placement = a.build_params()[1]
        self.assertEqual(placement, planner.Placement(self.job.piece, **self.place))
        self.assertTrue(a.proportions_var.get())
        self.assertFalse(a.origin_set)
        self.assertFalse(a.completed_checks)
        self.assertEqual([p.commands for p in a.job.passes], [p.commands for p in self.job.passes])

    def test_round_saved_job_keeps_outline_when_switching_picture_or_material(self):
        a = self.a
        piece = presets.lid_piece(52, 49.10)
        piece["margins"] = list(piece["margins"])
        art = Image.new("L", (456, 456), 255)
        art.paste(0, (96, 105, 360, 349))
        mat = self.job.material.copy(look="tin", pitch=0.15, piece="card-portrait",
                                     style="floyd", negative=False)
        placement = dict(fit="whole", art_w=49.0, dx=0.0, dy=0.0)
        plan = planner.compile_job(planner.build_job(art, mat, planner.Placement(piece, **placement)))
        folder = jobs.save_job(plan, verify.verify_job(plan), picture=art, folder=self.path / "tin",
                               extra=dict(placement=placement, keep_proportions=True))
        self.assertTrue(a.open_saved_job(folder))
        self.assertEqual(a.artw_var.get(), "49")
        self.assertIn("Actual grid: 49.05 x 49.05 mm", a.arth_lbl.cget("text"))
        self.assertIn("Custom round lid (52 mm outside diameter)", a.piece_var.get())
        self.assertEqual(a.piece["origin"], "center")
        self.assertFalse(a.exact_btn.instate(["disabled"]))
        a.exact_btn.invoke()
        self.pump()
        exact = a.build_params()[1]
        self.assertEqual(exact, planner.Placement(piece, **dict(placement, fit="art-exact")))
        self.assertAlmostEqual(a.job.geom.art_w, 49.0)
        a.exact_btn.invoke()
        self.pump()
        self.assertEqual(a.build_params()[1], planner.Placement(piece, **placement))

        replacement = self.path / "other-mask.png"
        art.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(replacement, dpi=(508, 508))
        a.completed_checks["image"] = a.check_key()
        self.assertTrue(a.open_picture(replacement, keep_layout=True))
        self.assertFalse(a.completed_checks)
        self.pump()
        self.assertTrue(a.file_has_size)
        self.assertFalse(a.saved_btn.instate(["disabled"]))
        self.assertEqual(a.build_params()[1], planner.Placement(piece, **placement))
        self.assertEqual(picture_jobs.registration_conflicts(plan, a.job), [])

        a.select_material("glass")
        self.pump()
        self.assertEqual(a.mat.piece, "square100")
        self.assertEqual(a.build_params()[1], planner.Placement(piece, **placement))
        a.materials.append(mat.copy(key="legacy-tin", name="Tin lid – rose-brass reference 80% at 140",
                                    power=800, feed=140, pitch=0.10, badge="MINE"))
        a._fill_tree()
        a.select_material("legacy-tin")
        self.pump()
        self.assertEqual(a.build_params()[1], planner.Placement(piece, **placement))
        self.assertEqual(a.artw_var.get(), "49")
        self.assertIn("Actual grid: 49.00 x 49.00 mm", a.arth_lbl.cget("text"))
        self.assertIn("Raster grids differ", picture_jobs.registration_conflicts(plan, a.job)[0])

        a.adv_vars["feed"][0].set("2000")
        a.adv_vars["pitch"][0].set("0.15")
        a._adv_changed()
        self.pump()
        self.compile()
        a.update_check_panel()
        self.assertIn("Effective settings (adjusted from preset)", a.m_settings.cget("text"))
        self.assertIn("speed 2000 mm/min", a.m_settings.cget("text"))
        review = a.check_text.cget("text")
        self.assertIn("Actual engraving grid: 49.05 x 49.05 mm", review)
        self.assertIn("Row spacing: 0.15 mm setting, 0.150 mm actual.", review)
        self.assertIn("Effective power and speed: 80% at 2000 mm/min.", review)

        # Simulate a fresh stock selection and confirm the older card recipe hints resolve to a round tin.
        a.piece_user_set = False
        a.select_material("legacy-tin")
        self.pump()
        self.assertEqual(a.piece_key, "tin50")
        self.assertEqual(a.mat.piece, "card-portrait")
        self.assertEqual(a.mat.pitch, 0.10)

        self.assertTrue(a.open_saved_job(folder))
        self.assertTrue(a.open_picture(replacement))
        self.pump()
        self.assertEqual(a.piece, piece)
        self.assertIsNone(a.art_w)
        self.assertFalse(a.exact_var.get())

        a.set_piece("tin50")
        a.artw_var.set("49")
        a._artw_edited()
        self.pump()
        self.assertEqual(a.piece["w"], 50.8)
        self.assertIn("Actual grid: 45.60 x 45.60 mm", a.arth_lbl.cget("text"))
        self.assertIn("limited by the usable face", a.arth_lbl.cget("text"))
        self.assertIn("Raster grids differ", picture_jobs.registration_conflicts(plan, a.job)[0])

    def test_direct_engraved_width_and_trace_follow_the_powered_shape(self):
        a = self.a
        path = self.path / "padded-ring.png"
        im = Image.new("L", (500, 500), 255)
        draw = ImageDraw.Draw(im)
        draw.ellipse((25, 32, 474, 467), outline=0, width=10)
        draw.rectangle((189, 196, 308, 321), fill=0)
        im.save(path)
        a.set_piece("tin50")
        a.piece.update(presets.lid_piece(52, 49.10))
        a.open_picture(path)
        a._customised(style="threshold", negative=False, pitch=0.15)
        self.pump()
        self.assertEqual(len(a.check_paths("image")), 1)
        self.assertNotEqual(a.check_paths("image"), a.check_paths("stock"))
        a.fit_var.set("marks")
        a._fit_changed()
        a.artw_var.set("48.60")
        a._artw_edited()
        self.assertEqual(a.check_paths("image"), [])
        self.pump()
        self.compile()
        a.update_check_panel()
        self.assertIn("Requested engraved width: 48.60 mm", a.check_text.cget("text"))
        self.assertEqual(a.piece["origin"], "center")
        self.assertEqual(a.piece["shape"], "circle")
        bounds = a.job.burn_bbox()
        self.assertAlmostEqual(bounds[2] - bounds[0], 48.60, places=2)
        trace = a.check_paths("image")
        self.assertAlmostEqual(max(x for x, y in trace[0]) - min(x for x, y in trace[0]), 48.60, places=2)
        pi = a.save_current_job(quiet=True)
        self.assertTrue(a.open_saved_job(pi))
        self.assertEqual(a.check_paths("image"), trace)
        a.turn(1)
        self.pump()
        self.assertEqual(a.artw_var.get(), "48.6")
        self.assertNotEqual(a.check_paths("image"), trace)
        a.nudge(1, 0)
        self.pump()
        self.assertEqual(a.dx, 1)
        self.assertNotEqual(a.check_paths("image"), trace)

        a.artw_var.set("55")
        a._artw_edited()
        self.pump()
        self.assertIn("usable face limits", a.job.sizing_note)
        previous = a.check_paths("image")
        a.v_neg.set(True)
        a.changed(0)
        self.pump()
        self.assertNotEqual(a.check_paths("image"), previous)

        cropped_source = self.path / "wide-art.png"
        im.crop((0, 140, 500, 390)).save(cropped_source)
        self.assertTrue(a.open_picture(cropped_source))
        a.v_neg.set(False)
        a.fit_var.set("whole")
        a._fit_changed()
        self.pump()
        previous = a.check_paths("image")
        a.fit_var.set("fill")
        a._fit_changed()
        self.pump()
        self.assertIsNotNone(a.job.geom.crop)
        self.assertNotEqual(a.check_paths("image"), previous)

        a.piece.update(origin="spot", spot=[24, 27])
        a.dx, a.dy = 0.35, -0.6
        a.sync_place_fields()
        a.exact_btn.invoke()
        self.pump()
        place = a.build_params()[1]
        self.assertEqual(place.piece["origin"], "spot")
        self.assertEqual(place.piece["spot"], [24, 27])
        self.assertEqual((place.dx, place.dy), (0.35, -0.6))
        self.assertAlmostEqual(a.job.geom.art_w / a.job.geom.art_h, 2)

    def test_trace_of_selected_pass_updates_overlay_and_never_approves_full_job(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        job = a.job
        first = job.passes[0]
        cells = np.zeros_like(first.cells)
        cells[2:5, 2:6] = 300
        first.cells = np.zeros_like(cells)
        first.cells[8:12, 12:15] = 500
        job.passes.append(planner.PassPlan("other", "Other", "", "rows", cells))
        a.preview.view.set("map")
        a.preview.set_job(job)
        self.assertEqual(len(a.check_paths("image")), 2)
        a.preview.show.set("Only Other")
        self.assertEqual(len(a.check_paths("image")), 1)
        self.assertEqual(a.check_paths("image"), job.trace_paths(frozenset({"other"})))
        a.origin_set = True
        a.completed_checks["image"] = a.check_key("image")
        self.assertFalse(a.ready_items()[4][0])
        a.preview.show.set("All passes")
        self.assertEqual(len(a.check_paths("image")), 2)
        a.completed_checks["image"] = a.check_key("image")
        self.assertTrue(a.ready_items()[4][0])

    def test_glass_appearance_controls_leave_verified_commands_and_polarity_unchanged(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        a.select_material("glass")
        a.v_neg.set(False)
        a.changed(0)
        self.pump()
        self.compile()
        job, pv = a.job, a.preview
        self.assertEqual(job.material.look, "glass")
        before = [jobs.pass_text(job, p, i, len(job.passes)) for i, p in enumerate(job.passes, 1)]
        mask = simulate.laser_input(job).tobytes()
        pv.view.set("map")
        pv.refresh()
        burn_map = pv._art_image().tobytes()
        self.assertFalse(pv.glass_bar.winfo_manager())
        pv.view.set("look")
        pv.refresh()
        legacy = pv._art_image().tobytes()
        self.assertEqual(pv.glass_bar.winfo_manager(), "pack")
        pv.glass_marks.set("Light")
        pv.glass_backing.set("Dark")
        pv.refresh()
        self.assertNotEqual(pv._art_image().tobytes(), legacy)
        pv.view.set("map")
        pv.refresh()
        self.assertEqual(pv._art_image().tobytes(), burn_map)
        self.assertIs(a.job, job)
        self.assertFalse(a.v_neg.get())
        self.assertEqual(simulate.laser_input(job).tobytes(), mask)
        self.assertEqual([jobs.pass_text(job, p, i, len(job.passes)) for i, p in enumerate(job.passes, 1)], before)

    def test_glass_pattern_comparison_preserves_the_current_job_and_white_surround(self):
        picture = Image.new("L", (150, 100), 255)
        picture.paste(117, (20, 18, 130, 82))
        glass = next(m for m in presets.BUILTIN if m.key == "glass").copy(pitch=0.15)
        piece = dict(name="Synthetic coupon", shape="rect", w=22.5, h=15, origin="lower-left")
        job = planner.compile_job(planner.build_job(picture, glass, planner.Placement(piece, fit="exact")))
        (ordered_label, ordered), (irregular_label, irregular) = simulate.glass_pattern_previews(job)
        self.assertIn("Halftone", ordered_label)
        self.assertIn("Stucki", irregular_label)
        self.assertEqual(ordered.tobytes(), simulate.laser_input(job).tobytes())
        self.assertEqual(ordered.size, irregular.size)
        self.assertNotEqual(ordered.tobytes(), irregular.tobytes())
        self.assertTrue(np.all(np.asarray(irregular)[job.gray == 255] == 255))
        self.assertEqual(job.material.style, "halftone")

    def test_sample_browser_and_separate_recent_folders_use_native_loaders(self):
        a = self.a
        source = self.path / "artwork"
        source.mkdir()
        picture = source / "sample.png"
        Image.new("L", (48, 36), 100).save(picture)
        catalog = self.path / "samples.json"
        entries = [
            ("photo", "Glass", "reference", "artwork/sample.png"),
            ("missing", "Wood", "job", "missing/job.json"),
            ("job", "Slate", "job", "input/job.json"),
            ("art", "Tin", "image", str(picture)),
        ]
        catalog.write_text(json.dumps({"schema_version": 1, "entries": [
            dict(id=key, title=key, material=material, kind=kind, path=path, project="Test", notes="Fixture")
            for key, material, kind, path in entries
        ]}), encoding="utf-8")
        button = next(w for w in a.pages[0].inner.winfo_children()
                      if isinstance(w, ttk.Button) and w.cget("text") == "Samples & Jobs...")
        button.invoke()
        lib = a._sample_library
        with patch("lps.sample_library.filedialog.askopenfilename", return_value=str(catalog)):
            lib.choose_catalog()
        self.assertEqual(jobs.load_settings()[sample_library.CATALOG_SETTING], str(catalog))
        self.assertEqual(len(lib.listing.get_children()), 4)

        def select(index):
            lib.listing.selection_set(f"item:{index}")
            lib.select()

        select(1)
        self.assertIn("Unavailable", lib.listing.item("item:1", "values"))
        self.assertTrue(lib.open_button.instate(["disabled"]))
        select(0)
        self.assertIn("photo viewer", lib.details.get("1.0", "end"))
        self.assertIn("Reference", lib.listing.item("item:0", "values"))
        with patch("lps.sample_library.os.startfile", create=True) as viewer:
            lib.open_button.invoke()
        viewer.assert_called_once_with(str(picture))
        self.assertIsNone(a.picture_path)
        select(3)
        self.assertIn("current material", lib.details.get("1.0", "end"))
        with patch.object(jobs, "active_runner", return_value={"pid": 1}), \
                patch("lps.sample_library.messagebox.showinfo") as info:
            lib.open_button.invoke()
        info.assert_called_once()
        self.assertIsNone(a.picture_path)
        lib.open_button.invoke()
        self.assertEqual(a.picture_path, picture)
        lib.material.set("Slate")
        lib.refresh()
        group, = lib.listing.get_children()
        self.assertEqual(lib.listing.item(group, "text"), "Slate / Test")
        select(2)
        help_text = lib.details.get("1.0", "end")
        for label in ("saved picture", "Image including padding", "Engraved marks", "Set engraved width",
                      "50% at 3500 mm/min", "0.2 mm"):
            self.assertIn(label, help_text)
        lib.open_button.invoke()
        self.assertFalse(lib.winfo_exists())
        self.assertEqual(a.job.passes[0].commands, self.job.passes[0].commands)
        self.assertFalse(a.origin_set)
        self.assertEqual(a._picker_folder("picture"), str(source))
        self.assertEqual(a._picker_folder("job"), str(self.folder))
        button.invoke()
        lib = a._sample_library
        lib.recent.set(True)
        lib.refresh()
        self.assertEqual(lib.listing.item("item:0", "text"), "job")

    def test_port_settings_denial_keeps_old_data_and_does_not_connect(self):
        a = self.a
        jobs.save_settings(a.settings)
        prior = jobs.SETTINGS_FILE.read_bytes()
        a.port_var.set("COM6")
        with patch.object(jobs.os, "replace", side_effect=PermissionError(5, "Fixture denied")), \
                patch("lps.app_laser.messagebox.showerror") as error, \
                patch("lps.app_laser.MachineWorker", side_effect=AssertionError("Must not try connecting")):
            a.connect()
        self.assertEqual(jobs.SETTINGS_FILE.read_bytes(), prior)
        self.assertFalse(list(jobs.SETTINGS_FILE.parent.glob("settings.json.*.tmp")))
        self.assertEqual(a.settings["port"], "COM4")
        self.assertIsNone(a.worker)
        self.assertIn(str(jobs.SETTINGS_FILE), error.call_args.args[1])
        self.assertIn("did not attempt a connection to COM6", error.call_args.args[1])

    def test_portable_job_opens_through_file_drop_without_connection_or_zero(self):
        a = self.a
        destination = self.path / "portable with spaces.lpsjob"
        (self.folder / "photos" / "exclude.txt").write_text("not part of an editable job")
        job_package.export_job(self.folder, destination)
        with ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()), {"job.json", "picture.png", "passes/01 Engrave.nc"})
        with patch.object(jobs, "active_runner", return_value={"pid": 1}):
            self.assertFalse(a.open_dropped_file(destination))
        self.assertFalse((self.path / "Imported Jobs").exists())
        self.assertTrue(a.open_dropped_file(destination))
        self.assertEqual(a.job.passes[0].commands, self.job.passes[0].commands)
        self.assertEqual(a.build_params()[1], planner.Placement(self.job.piece, **self.place))
        self.assertFalse(a.origin_set)
        self.assertFalse(a.connected)
        self.assertEqual(a._picker_folder("job"), str(self.path))
        self.assertEqual(job_package.import_job(destination).parent, a.picture_path.parent)
        with ZipFile(destination, "a") as archive:
            archive.writestr("../other-job.json", "{}")
        with self.assertRaisesRegex(ValueError, "only the source picture"):
            job_package.import_job(destination)
        self.assertFalse((self.path / "other-job.json").exists())

    def test_image_corner_zero_translates_work_coordinates_without_moving_the_picture(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        a.piece["corner"] = 0.0
        a.changed(0)
        self.pump()
        original = a.job.geom
        a.origin_set = True
        a.completed_checks["image"] = a.check_key()
        a.use_image_corner_zero()
        self.assertFalse(a.origin_set)
        self.assertFalse(a.completed_checks)
        self.pump()
        updated = a.job.geom
        self.assertAlmostEqual(updated.x0, 0.0, places=2)
        self.assertAlmostEqual(updated.y0, 0.0, places=2)
        self.assertAlmostEqual(original.x0 - original.piece_rect[0], updated.x0 - updated.piece_rect[0])
        self.assertAlmostEqual(original.y0 - original.piece_rect[1], updated.y0 - updated.piece_rect[1])
        self.assertEqual((original.art_w, original.art_h), (updated.art_w, updated.art_h))
        self.assertEqual(a.job.material.pitch, self.job.material.pitch)
        self.assertFalse(a.connected)

    def test_recovery_shows_why_resume_is_blocked_and_keeps_button_in_footer(self):
        a = self.a
        state = dict(resume=dict(start_pass=0, expected_start=[-6.25, 2.9]), phase="dropout")
        with patch("lps.dialogs._recovery_work_area", return_value=(0, 0, 560, 410)):
            win = RecoveryDialog(a, self.folder, state)
        self.root.update_idletasks()
        self.assertEqual(str(win.transient()), "")
        self.assertLessEqual(win.winfo_height(), 354)
        footer = win.go.master.master
        self.assertEqual(footer.pack_info()["side"], "bottom")
        self.assertLessEqual(footer.winfo_y() + footer.winfo_height(), win.winfo_height())
        self.assertTrue(win.go.instate(["disabled"]))
        self.assertIn("Connect", str(win.resume_reason.cget("text")))
        a.connected = True
        a.last_status = SimpleNamespace(wpos=(-6.25, 2.9), state="Idle", idle_off=True, at=time.monotonic())
        win.refresh()
        self.assertIn("confirm it", str(win.resume_reason.cget("text")))
        win.declared = True
        win.refresh()
        self.assertFalse(win.go.instate(["disabled"]))
        a.dot_on = True
        win.refresh()
        self.assertTrue(win.go.instate(["disabled"]))
        self.assertIn("dot off", str(win.resume_reason.cget("text")))
        a.dot_on = False
        a.last_status.at -= 3
        win.refresh()
        self.assertIn("fresh", str(win.resume_reason.cget("text")))
        win.close()
        a.connected = False

    def test_live_head_follows_reported_coordinates_and_beam_between_progress_updates(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        a.active_folder = a.saved[a.gen] = self.folder
        stamp = time.time()
        first = dict(phase="running", pid=42, wpos=[0, 1], position_at=stamp, status_at=stamp, laser_on=True)
        a.run_state = first

        next_frame = dict(first, wpos=[4, 6], laser_on=False)
        jobs.write_json(self.folder / "state.json", next_frame)
        with patch.object(a.preview, "draw_head") as draw:
            a._follow_run_head()
            draw.assert_called_once()
        self.assertEqual(a.head_position(), [4, 6])
        self.assertFalse(a.laser_is_on())
        self.assertEqual(a.laser_lbl.cget("text").strip(), "laser off")
        self.assertIs(a.run_state, first)

        jobs.write_json(self.folder / "state.json", dict(next_frame, pid=99, wpos=[99, 99], laser_on=True))
        a._follow_run_head()
        self.assertEqual(a.head_position(), [4, 6])
        with patch("lps.app_laser.time.time", return_value=stamp + 1.2):
            a._follow_run_head()
            self.assertTrue(a.status_stale())
            self.assertEqual(a.laser_lbl.cget("text").strip(), "Beam status unavailable")

    def test_saved_reflective_lid_uses_its_template_without_changing_art(self):
        piece = copy.deepcopy(presets.PIECES["tin50"])
        path = self.path / "tin"
        art = Image.new("L", (40, 40), 255)
        art.paste(0, (10, 10, 30, 30))
        placement = dict(fit="whole", art_w=45.60, dx=0., dy=0.)
        job = planner.build_job(art, self.job.material, planner.Placement(piece, **placement), name="tin")
        planner.compile_job(job)
        report = verify.verify_job(job)
        self.assertTrue(report["ok"])
        jobs.save_job(job, report, picture=art, folder=path, extra=dict(placement=placement))
        self.assertTrue(self.a.open_saved_job(path))
        self.assertEqual(self.a.piece_key, "tin50")
        self.assertEqual(self.a.piece_var.get(), piece["name"])
        self.assertEqual(self.a.art_w, 45.60)
        self.assertEqual(self.a.job.passes[0].commands, job.passes[0].commands)

    def test_native_export_retains_passes_and_the_toolpath_preview(self):
        a = self.a
        raw, _, _, _, _, _, _ = picture_jobs.read(self.folder)
        mat = self.job.material.copy(passes=2)
        job = planner.compile_job(planner.build_job(
            raw, mat, planner.Placement(self.job.piece, **self.place), look=self.look, name="two passes"))
        fixture = jobs.save_job(job, verify.verify_job(job), picture=raw, folder=self.path / "two",
                                extra=dict(look=self.look, placement=self.place))
        self.assertTrue(a.open_saved_job(fixture))
        a.preview.view.set("toolpath")
        a.preview.refresh()
        a.preview.redraw()
        self.assertIn("planned laser power", a.preview.legend.cget("text"))
        self.assertIn("All passes", a.preview.show_box.cget("values"))

        target = self.path / "portable.nc"
        with patch("lps.app_place.filedialog.asksaveasfilename", return_value=str(target)), \
                patch("lps.app_place.messagebox.showinfo"):
            a.export_gcode()
        folder = a.saved[a.gen]
        self.assertEqual(target.read_bytes(), jobs.lasergrbl_path(fixture).read_bytes())
        self.assertEqual(target.read_bytes(), jobs.lasergrbl_path(folder).read_bytes())
        exported = target.with_name("portable - one file per pass")
        passes = sorted(exported.glob("*.nc"))
        self.assertEqual(len(passes), 2)
        self.assertEqual([jobs.read_body(p) for p in passes], [p.commands for p in job.passes])
        self.assertEqual(len(list(folder.glob("3 TOOLPATH*.png"))), 1)
        self.assertEqual(picture_jobs.read(folder)[2].passes[0].commands, job.passes[0].commands)
        self.assertFalse(a.connected)

    def test_pair_blocks_mismatched_grids_and_shows_requested_usable_and_actual_widths(self):
        a = self.a
        mat = self.job.material.copy(pitch=0.15, style="floyd", negative=False, passes=1)
        look = {key: getattr(mat, key) for key in picture_jobs.LOOK_KEYS}
        look["sharpen"] = 0
        copper_piece = presets.lid_piece(safe=50.8, name="Exact size")
        silver_piece = presets.lid_piece()

        def save_pass(name, piece, width, box, feed):
            art = Image.new("L", (456, 456), 255)
            art.paste(0, box)
            place = dict(fit="whole", art_w=width, dx=0.0, dy=0.0)
            p = planner.Placement(piece, **place)
            plan = planner.compile_job(planner.build_job(art, mat.copy(feed=feed), p, look=look, name=name))
            report = verify.verify_job(plan)
            self.assertTrue(report["ok"])
            return jobs.save_job(plan, report, picture=art, folder=self.path / name,
                                 extra=dict(placement=place, look=look))

        copper = save_pass("Copper", copper_piece, 49.0, (75, 120, 190, 340), 50)
        silver = save_pass("Silver mismatch", silver_piece, 49.05, (230, 125, 330, 345), 2000)
        aligned = save_pass("Silver aligned", copper_piece, 49.05, (230, 125, 330, 345), 2000)
        self.assertTrue(a.open_saved_job(copper))
        self.assertIn("Requested artwork width: 49.00 mm", a.check_text.cget("text"))
        self.assertIn("Actual engraving grid: 49.05 x 49.05 mm", a.check_text.cget("text"))
        self.assertIn("Requested width rounded", a.check_text.cget("text"))
        self.assertIn("Marks:", a.check_text.cget("text"))
        self.assertEqual(a.pair_blocker(), "")

        def pair_with(folder):
            with patch("lps.app_place.filedialog.askopenfilename", return_value=str(folder / "job.json")):
                a.choose_pair()

        pair_with(silver)
        self.assertIn("49.05 x 49.05 mm (327 x 327) vs 45.60 x 45.60 mm (304 x 304)", a.pair_blocker())
        self.assertIn("Usable faces or margins differ", a.pair_blocker())
        self.assertTrue(a.btn_start.instate(["disabled"]))
        with patch.object(a, "ready_items", return_value=[(True, "", "")] * 6), \
                patch.object(a, "save_current_job") as save, \
                patch("lps.app_laser.messagebox.showinfo") as explanation:
            a.start_engraving()
            explanation.assert_called_once()
            self.assertIn("Raster grids differ", explanation.call_args.args[1])
            save.assert_not_called()
        self.assertTrue(a.open_saved_job(silver))
        self.assertEqual(a.piece_dimensions["w"][0].cget("text"), "Outside diameter")
        self.assertFalse(a.piece_dimensions["h"][1].winfo_manager())
        self.assertEqual(a.artw_var.get(), "49.05")
        self.assertIn("Actual grid: 45.60 x 45.60 mm", a.arth_lbl.cget("text"))
        before_edit = a.gen
        a._artw_edited()
        self.assertEqual(a.gen, before_edit)
        self.assertIn("Requested artwork width: 49.05 mm", a.check_text.cget("text"))
        self.assertIn("Usable face: 45.72 x 45.72 mm", a.check_text.cget("text"))
        self.assertIn("Width limited by the usable face", a.check_text.cget("text"))
        self.assertIn("Actual engraving grid: 45.60 x 45.60 mm", a.check_text.cget("text"))
        self.assertIsNone(a._pair)

        self.assertTrue(a.open_saved_job(copper))
        pair_with(aligned)
        self.assertEqual(a.pair_blocker(recheck=True), "")
        self.assertIn("Pair geometry matches", a.check_text.cget("text"))
        metadata = aligned / "job.json"
        metadata.write_text(metadata.read_text() + "\n")
        self.assertIn("Choose the paired job again", a.pair_blocker(recheck=True))
        a.clear_pair()
        self.assertEqual(a.pair_blocker(recheck=True), "")
        self.assertFalse(a.connected)

    def test_run_history_keeps_prepared_and_latest_physical_attempt_distinct(self):
        a = self.a
        jobs.JOBS_DIR.mkdir()
        folder = self.folder.rename(jobs.JOBS_DIR / "fixture")
        a.open_run_history()
        win = a._run_history
        self.assertTrue(win.save_button.instate(["disabled"]))
        self.assertIn("No run result", win.details.get("1.0", "end"))
        jobs.write_json(folder / "state.json", {"phase": "complete", "started": "2026-11-21T03:34:14",
                                               "timer": {"job_t0": 123.0}, "elapsed_s": 19.0})
        jobs.write_json(folder / "timing.json", {"passes": [{"title": "Engrave", "ended": "complete",
                                                             "real_s": 18.0, "start_basis": "first reported movement"}]})
        win.reload()
        self.assertFalse(win.save_button.instate(["disabled"]))
        self.assertIn("18.000 s", win.details.get("1.0", "end"))
        photo = folder / "picture.png"
        run_history.save_run_result(folder, "123.0", {"stock": "fixture wood", "before_photo": str(photo)})
        self.assertEqual(run_history.read_run(folder)[-1]["before_photo"], str(photo))
        jobs.write_json(folder / "state.json", {"phase": "complete", "timer": {"job_t0": 124.0}})
        self.assertEqual(run_history.read_run(folder)[-1], {})
        with self.assertRaisesRegex(ValueError, "changed"):
            run_history.save_run_result(folder, "123.0", {"finish": "wrong attempt"})
        self.assertEqual(jobs.read_json(folder / "results.json")["attempts"]["123.0"]["stock"], "fixture wood")

    def test_full_snapshot_survives_startup_events_and_edits_change_actual_output(self):
        a=self.a;a.port_var.set('COM6')
        self.assertTrue(a.open_saved_job(self.folder))
        self.root.update()  # includes queued startup tree selections
        expected=asdict(self.job.material)
        self.assertEqual(asdict(a.mat),expected)
        self.assertEqual(a.tree.selection(),('job:material',))
        self.assertFalse(any(m.key=='imported-test' for m in a.materials))
        self.assertEqual(a.source_provenance['original_material']['name'],self.job.material.name)
        self.assertEqual(a.piece,self.job.piece)
        self.assertEqual(a.build_params()[2],self.look)
        self.assertEqual(a.build_params()[1].__dict__,planner.Placement(self.job.piece,**self.place).__dict__)
        self.assertEqual(a.port_var.get(),'COM6')
        self.assertTrue(a.proportions_var.get())
        original=a.job.passes[0].commands.copy();gray=a.job.gray.copy()
        cells=a.job.passes[0].cells.copy()
        a.v_contrast.set(-35);a.v_sharpen.set(100);a.changed(0)
        self.assertIsNone(a.report);self.assertNotEqual(a.compiled_gen,a.gen)
        self.pump();self.compile()
        self.assertFalse(np.array_equal(a.job.gray,gray))
        self.assertFalse(np.array_equal(a.job.passes[0].cells,cells))
        self.assertNotEqual(a.job.passes[0].commands,original)
        inverted=a.job.gray.copy()
        a.v_neg.set(False);a.changed(0);self.pump();self.compile()
        self.assertTrue(np.allclose(a.job.gray,255.-inverted))  # Negative applied exactly once
        self.assertEqual(a.piece,self.job.piece)

    def test_browse_and_apply_preset_to_saved_picture_keep_photo_and_geometry(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        a.goto(1)
        self.root.update()
        original = a.build_params()
        old_commands = [p.commands.copy() for p in a.job.passes]
        a.completed_checks["image"] = a.check_key()
        gen = a.gen
        a.tree.selection_set("m:glass")
        self.root.update()
        self.assertEqual(a._pending_material, "glass")
        self.assertEqual(a.tree.selection(), ("m:glass",))
        self.assertEqual(a.gen, gen)
        self.assertIn("image", a.completed_checks)
        self.assertEqual(a.build_params(), original)
        self.assertEqual(old_commands, [p.commands for p in a.job.passes])
        self.assertIn("Speed: 3500 mm/min", a.material_diff.cget("text"))
        self.assertIn("Contrast: 13", a.material_diff.cget("text"))
        a._apply_material_choice(False)
        self.pump()
        self.compile()
        self.assertFalse(a.completed_checks)
        self.assertEqual(a.build_params()[1:], original[1:])
        self.assertEqual(a.mat.key, "glass")
        review = a.placement_review_text(a.job, a.report)
        self.assertIn("Reference job: input", review)
        self.assertIn("Print changes:", review)
        self.assertNotIn("Picture changes:", review)
        self.assertFalse(a.look_frames[1].winfo_manager())

        a.tree.selection_set("m:pine-layers")
        self.root.update()
        a.apply_full_preset.invoke()
        self.pump()
        self.compile()
        self.assertEqual(a.mat.key, "pine-layers")
        self.assertEqual(a.build_params()[1], original[1])
        self.assertFalse(a.v_neg.get())
        self.assertEqual(a.v_sharpen.get(), a.mat.sharpen)
        self.assertIn("Picture changes:", a.placement_review_text(a.job, a.report))
        self.assertTrue(a.look_frames[1].winfo_manager())

    def test_selected_recipe_can_change_exposure_without_resampling_a_registered_mask(self):
        a = self.a
        target = next(m for m in presets.BUILTIN if m.key == "slate").copy(pitch=.10, power=800, feed=140)
        a.materials = [target]
        current = target.copy(style="floyd", pitch=.15, power=500, feed=2400)
        stock = presets.PIECES["tin51face"]
        position = dict(fit="whole", art_w=51, dx=0, dy=0)
        picture = Image.new("L", (340, 340), 255)
        ImageDraw.Draw(picture).ellipse((30, 75, 288, 265), outline=0, width=4)
        original = planner.compile_job(planner.build_job(picture, current, planner.Placement(stock, **position)))
        folder = jobs.save_job(original, verify.verify_job(original), picture=picture,
                               extra=dict(placement=position))
        self.assertTrue(a.open_saved_job(folder))
        self.assertEqual(a.piece_key, "tin51face")
        a.goto(1)
        self.root.geometry("900x575+4200+50")
        self.root.deiconify()
        self.root.update()
        row = "m:" + target.key
        a.tree.see(row)
        self.root.update()
        x, y, w, h = a.tree.bbox(row)
        for event in ("<ButtonPress-1>", "<ButtonRelease-1>"):
            a.tree.event_generate(event, x=x+32, y=y+h//2)
        self.root.update()
        self.assertEqual(a.tree.selection(), (row,))
        self.assertIn("340 × 340 → 510 × 510", a.preset_impact.cget("text"))
        self.assertIn("2400 mm/min", a.active_recipe.cget("text"))
        self.assertLess(a.apply_exposure.winfo_rooty() + a.apply_exposure.winfo_height(),
                        self.root.winfo_rooty() + self.root.winfo_height())
        a.tree.focus_force()
        a.tree.event_generate("<Return>")
        self.root.update()
        self.assertEqual(self.root.focus_get(), a.apply_exposure)
        a.apply_exposure.event_generate("<KeyPress-space>")
        a.apply_exposure.event_generate("<KeyRelease-space>")
        self.root.update()
        self.pump()
        self.compile()
        self.assertEqual((a.mat.feed, a.mat.power, a.mat.pitch, a.mat.style), (140, 800, .15, "floyd"))
        self.assertEqual(a.build_params()[1], planner.Placement(a.piece, **position))
        self.assertFalse(picture_jobs.registration_conflicts(original, a.job))
        np.testing.assert_array_equal(original.passes[0].cells > 0, a.job.passes[0].cells > 0)
        a.tree.selection_set(row)
        self.root.update()
        a.require_pair.set(True)
        a.apply_full_preset.invoke()
        self.pump()
        self.compile()
        self.assertEqual(a.job.geom.cols, 510)
        self.assertIn("fresh comparison", a.pair_blocker())
        saved = a.save_current_job(quiet=True)
        self.assertTrue(a.open_saved_job(saved))
        self.assertIn("fresh comparison", a.pair_blocker())
        with patch("lps.app_place.filedialog.askopenfilename", return_value=str(folder/"job.json")):
            a.choose_pair()
        self.assertIn("Raster grids differ", a.pair_blocker())

    def test_repeat_reference_survives_replacement_and_identifies_intentional_speed_test(self):
        a = self.a
        self.assertTrue(a.open_saved_job(self.folder))
        replacement = self.path / "second-IMPORT.png"
        replacement.write_bytes((self.folder / "picture.png").read_bytes())
        self.assertTrue(a.open_picture(replacement, keep_layout=True))
        self.pump()
        self.compile()
        self.assertEqual([p.commands for p in a.job.passes], [p.commands for p in self.job.passes])
        self.assertTrue(a.v_neg.get())
        self.assertIn("Print settings match", a.placement_review_text(a.job, a.report))
        a._customised(feed=2800)
        self.pump()
        self.compile()
        review = a.placement_review_text(a.job, a.report)
        self.assertIn("Speed: 3500 mm/min → 2800 mm/min", review)
        self.assertNotIn("Picture changes:", review)
        self.assertEqual(self.look, a.build_params()[2])
        self.assertTrue(a.open_picture(replacement))
        self.assertEqual(a._repeat_reference[0], self.folder)
        self.assertFalse(a.v_neg.get())
        self.assertEqual(a.v_contrast.get(), a.mat.contrast)

    def test_save_reopen_rotated_image_and_live_values_without_double_processing(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        a.turn(1);a.flip();self.pump()
        a.v_contrast.set(7);a.v_neg.set(False);a.changed(0);self.pump();self.compile()
        expected=a.job.passes[0].commands.copy();gray=a.job.gray.copy()
        folder=a.save_current_job(quiet=True)
        saved=jobs.read_json(folder/'job.json')
        self.assertIn('sha256',saved['editable_picture'])
        self.assertEqual(saved['saved_source_transform']['rotate'],1)
        self.assertTrue(saved['saved_source_transform']['mirror'])
        self.assertTrue(a.open_saved_job(folder/'job.json'));self.root.update()
        self.assertEqual(a.job.passes[0].commands,expected)
        self.assertTrue(np.array_equal(a.job.gray,gray))
        self.assertFalse(a.v_neg.get())
        self.assertEqual(a.rotate,0)  # orientation is already in saved source pixels
        self.assertIsNotNone(a.source_provenance)

    def test_injected_source_less_job_reports_error_and_keeps_zero_guard(self):
        a=self.a;a.job=self.job;a.picture=a.picture_raw=None
        a.changed(0)
        self.root.update();self.root.update()
        self.assertFalse(a.layout_pending)
        self.assertIn('No editable picture',a.layout_error)
        self.assertIsNone(a.report)
        with patch.object(a,'need_connection') as connect:
            a.set_origin();connect.assert_not_called()
        self.assertTrue(a.open_saved_job(self.folder))
        self.assertIsNone(a.layout_error)
        self.assertFalse(a.layout_pending)
        with patch.object(a,'need_connection',return_value=False) as connect:
            a.set_origin();connect.assert_called_once()  # normal zero workflow, not bypass

    def test_bad_source_pass_and_unknown_schema_rejected_without_mutation(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder));before=a.job
        original=(self.folder/'picture.png').read_bytes()
        for what in ('source','pass','schema'):
            doc=jobs.read_json(self.folder/'job.json');saved=copy.deepcopy(doc)
            if what=='source':(self.folder/'picture.png').write_bytes(b'changed')
            elif what=='pass':
                f=self.folder/doc['passes'][0]['file'];content=f.read_bytes();f.write_bytes(content+b'\n;changed')
            else:
                doc['material']['unknown_setting']=99;jobs.write_json(self.folder/'job.json',doc)
            with patch('lps.app.messagebox.showerror') as error:
                self.assertFalse(a.open_saved_job(self.folder));error.assert_called_once()
            self.assertIs(a.job,before)
            (self.folder/'picture.png').write_bytes(original)
            if what=='pass':f.write_bytes(content)
            jobs.write_json(self.folder/'job.json',saved)

    def test_check_only_mode_explains_and_disables_picture_controls(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        a.perimeter_mode(self.folder/'passes'/jobs.pass_filename(1,self.job.passes[0]))
        self.assertIn('G-code check only',a.edit_mode_lbl.cget('text'))
        self.assertEqual(a.nb.tab(1,'state'),'disabled')
        self.assertTrue(a._locked_picture_widgets)
        self.assertTrue(all(w.instate(['disabled']) for w in a._locked_picture_widgets))
        self.assertTrue(a.open_saved_job(self.folder))
        self.assertEqual(a.nb.tab(1,'state'),'normal')
        self.assertFalse(a._locked_picture_widgets)

    def test_saved_material_preset_includes_effective_picture_adjustments(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        piece=copy.deepcopy(a.piece);a.port_var.set('COM4')
        a.v_contrast.set(17);a.v_sharpen.set(45);a.v_neg.set(False)
        with patch('lps.app.FormDialog',return_value=SimpleNamespace(result={'name':'Effective recipe'})), \
             patch.object(presets,'user_presets_path',return_value=self.path/'my-presets.json'):
            a.save_preset()
            saved=presets.load_materials()[-1]
        self.assertEqual((saved.contrast,saved.sharpen,saved.negative),(17,45,False))
        self.assertEqual(a.build_params()[2]['contrast'],17)
        self.assertEqual(a.piece,piece)
        self.assertEqual(a.port_var.get(),'COM4')

    def test_import_reuses_existing_recipe_without_editing_or_adding_presets(self):
        a=self.a
        stored=self.job.material.copy(key='my-existing-slate',name='Slate coaster - photo',badge='MINE',sharpen=30)
        a.materials.append(stored)
        before=copy.deepcopy(a.materials)
        self.assertTrue(a.open_saved_job(self.folder))
        self.root.update()
        self.assertEqual(a.materials,before)
        self.assertEqual(a.tree.selection(),('m:my-existing-slate',))
        self.assertFalse(a.tree.exists('m:imported-test'))
        self.assertFalse(a.tree.exists('job:material'))
        self.assertEqual(a.m_name.cget('text'),'Slate coaster - photo')
        self.assertEqual(a.build_params()[2],self.look)
        self.assertEqual(a.job.passes[0].commands,self.job.passes[0].commands)
        self.assertEqual(a.mat.row_feed,6000)
        self.assertEqual(a.mat.scan_direction,'forward')

    def test_size_labels_distinguish_measured_geometry_margins_and_rounding(self):
        self.assertEqual(presets.PIECES['coaster100']['corner'],0)
        self.assertEqual(presets.PIECES['square100']['corner'],0)
        self.assertEqual(presets.PIECES['coaster100']['w'],100.6)
        self.assertEqual(presets.PIECES['coaster100']['margins'],(5.8,)*4)
        self.assertIn('(slate)',presets.piece_choice_label(presets.PIECES['coaster100']))
        self.assertIn('3 mm margins',presets.piece_choice_label(presets.PIECES['square100']))
        piece=dict(name='Saved slate',shape='rect',w=100.6,h=100.6,origin='lower-left',
                   margins=[5.8]*4,corner=0,keepouts=[])
        self.a.piece=copy.deepcopy(piece);self.a.piece_key='custom';self.a.art_w=89
        self.a.sync_place_fields()
        self.assertEqual(self.a.piece_var.get(),'Square 100.6 x 100.6 mm (slate)')
        self.assertIn('corner radius 0 mm',self.a.piece_in_lbl.cget('text'))
        self.assertEqual(self.a.piece,piece)
        self.assertEqual(self.a.art_w,89)
        rounded=copy.deepcopy(presets.PIECES['coaster100']);rounded['corner']=8
        self.assertNotEqual(presets.piece_choice_label(rounded),presets.PIECES['coaster100']['name'])
        self.assertEqual(rounded['corner'],8)  # archived rounded jobs are never silently reshaped

    def test_piece_specific_controls_and_optional_slate_rounding(self):
        a=self.a
        a.select_material('slate');a.set_piece('coaster100')
        self.assertEqual(a.slate_rounding.winfo_manager(),'pack')
        self.assertEqual(a.car_options.winfo_manager(),'')
        self.assertFalse(a.rounding_var.get())
        self.assertEqual(a.piece['corner'],0)
        a.rounding_var.set(True);a._slate_rounding_toggled()
        self.assertGreater(a.piece['corner'],0)
        a.rounding_var.set(False);a._slate_rounding_toggled()
        self.assertEqual(a.piece['corner'],0)
        a.use_car(presets.car_values('mustang'))
        self.assertEqual(a.car_options.winfo_manager(),'pack')
        self.assertEqual(a.slate_rounding.winfo_manager(),'')
        a.set_piece('square100')
        self.assertEqual(a.car_options.winfo_manager(),'')
        self.assertEqual(a.slate_rounding.winfo_manager(),'')

    def test_same_key_job_override_can_return_to_the_stored_preset(self):
        a=self.a
        snapshot=presets.BUILTIN[0].copy(feed=217)
        with patch.object(a,'_show_material'):
            a._adopt_material_snapshot(snapshot)
        self.assertIsNotNone(a._job_material_snapshot)
        a.tree.selection_set('m:'+snapshot.key);a._tree_pick()
        self.assertIsNone(a._job_material_snapshot)
        self.assertEqual(a.mat.feed,presets.BUILTIN[0].feed)

    def test_preview_modes_match_marks_and_slate_polarity_without_changing_commands(self):
        a=self.a
        picture=Image.new('L',(20,20),0)
        picture.paste(255,(10,0,20,20))
        m=next(m for m in presets.BUILTIN if m.key=='slate').copy(style='threshold',pitch=.2,runup=0)
        pc=dict(name='Test',shape='rect',w=4.,h=4.,origin='lower-left',margins=[0]*4,corner=0,keepouts=[])
        job=planner.build_job(picture,m,planner.Placement(pc,art_w=4),look={'negative':True})
        a.job=job;a.preview.set_job(job);a.preview.view.set('map')
        firing=np.asarray(a.preview._art_image())
        self.assertEqual(firing.ndim,3)
        mask=job.passes[0].cells>0
        self.assertTrue(np.all(np.any(firing[mask]!=255,axis=1)))
        self.assertTrue(np.all(firing[~mask]==255))
        self.assertGreater(mask[:,10:].mean(),mask[:,:10].mean())  # source highlights fire on slate
        appearance=np.asarray(simulate.appearance(job)).mean(axis=2)
        self.assertGreater(appearance[:,12:].mean(),appearance[:,:8].mean())
        self.assertTrue(np.all(np.asarray(simulate.laser_input(job))[mask]==0))
        commands=planner.compile_job(job).passes[0].commands.copy()
        for view in ('look','map','pic','lgrbl'):
            a.preview.view.set(view);a.preview._art_image()
        self.assertEqual(job.passes[0].commands,commands)

    def test_auto_levels_changes_pixels_and_commands_without_moving_manual_sliders(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        a.picture=Image.fromarray(np.tile(np.linspace(80,180,256,dtype=np.uint8),(210,1)))
        a.v_auto.set(False);a.changed(0);self.pump();self.compile()
        before=a.job.passes[0].commands.copy()
        controls=(a.v_bright.get(),a.v_contrast.get(),a.v_gamma.get(),a.v_sharpen.get(),a.v_neg.get())
        a.v_auto.set(True);a.changed(0);self.pump();self.compile()
        self.assertNotEqual(a.job.passes[0].commands,before)
        self.assertEqual(controls,(a.v_bright.get(),a.v_contrast.get(),a.v_gamma.get(),a.v_sharpen.get(),a.v_neg.get()))

    def test_auto_action_writes_visible_levels_and_manual_edits_have_no_hidden_auto(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        a.picture=Image.fromarray(np.tile(np.linspace(80,180,256,dtype=np.uint8),(210,1)))
        a.auto_levels();self.pump();self.compile()
        self.assertFalse(a.v_auto.get())
        self.assertGreater(a.v_black.get(),0);self.assertLess(a.v_white.get(),255)
        self.assertEqual((a.v_bright.get(),a.v_contrast.get(),a.v_gamma.get()),(0,0,1))
        self.assertIn('Auto applied',a.look_mode.cget('text'))
        self.assertEqual((a.v_sharpen.get(),a.v_neg.get()),(30,True))
        a.v_contrast.set(15);a._manual_look_changed();self.pump();self.compile()
        self.assertIn('Manual:',a.look_mode.cget('text'))
        self.assertFalse(a.build_params()[2]['autolevel'])
        folder=a.save_current_job(quiet=True)
        gray=a.job.gray.copy()
        self.assertTrue(a.open_saved_job(folder));self.assertTrue(np.array_equal(gray,a.job.gray))

    def test_visible_level_points_reproduce_legacy_auto_exactly(self):
        rng=np.random.default_rng(42)
        for vals in (rng.integers(60,191,size=(67,91),dtype=np.uint8),np.full((10,10),128,dtype=np.uint8)):
            image=Image.fromarray(vals)
            lo,hi=imaging.auto_level_points(image)
            old=imaging.to_grid(image,91,67,autolevel=True,contrast=13,negative=True,sharpen=30)
            visible=imaging.to_grid(image,91,67,black_point=lo,white_point=hi,contrast=13,negative=True,sharpen=30)
            self.assertTrue(np.array_equal(old,visible))

    def test_slider_drag_notifies_only_once_on_release(self):
        from lps.ui_common import Slider
        callback=[];var=tk.DoubleVar()
        slider=Slider(self.root,'Test',var,0,100,command=callback.append)
        slider._start_drag()
        for value in (10,20,30):var.set(value);slider._moved()
        self.assertFalse(callback)
        slider._end_drag()
        self.assertEqual(callback,[30])

    def test_slider_accepts_exact_numeric_values_and_rejects_invalid_text(self):
        from lps.ui_common import Slider
        callback=[];var=tk.DoubleVar(value=0)
        slider=Slider(self.root,'Test',var,-100,100,command=callback.append)
        slider.edit_var.set('13');slider._commit_entry()
        self.assertEqual((var.get(),callback),(13,[13]))
        slider._commit_entry();self.assertEqual(callback,[13])
        slider.edit_var.set('nan');slider._commit_entry()
        self.assertEqual(var.get(),13)
        self.assertEqual(slider.edit_var.get(),'13')
