"""Placement workflow regression tests. Isolated settings, no real serial access."""
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

from lps import jobs, machine, presets, planner
from lps.app import App


class PlacementUI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.patches = [patch.object(jobs,'SETTINGS_FILE',self.folder/'settings.json'),
                        patch.object(jobs,'LOCK_FILE',self.folder/'sender.lock'),
                        patch.object(jobs,'JOBS_DIR',self.folder/'Jobs'),
                        patch("lps.app_laser.DEMO_STATE", self.folder / "demo-state.json"),
                        patch.object(machine.SerialWire,'open',side_effect=AssertionError('No real laser in UI tests'))]
        for p in self.patches:
            p.start()
        self.root=tk.Tk()
        self.root.withdraw()
        self.app=App(self.root,SimpleNamespace(demo=True,picture=None,perimeter=None))
        self.app.select_material('anodized-dots')
        pic=Image.new('L',(1120,1520),255)
        ImageDraw.Draw(pic).rectangle((200,200,900,1300),fill=0)
        self.picture=self.folder/'roof.png'
        pic.save(self.picture,dpi=(2032,2032))
        self.app.open_picture(self.picture)
        self.app.v_neg.set(False)
        self.app.changed(0)
        self.pump()

    def tearDown(self):
        for task in self.root.tk.call('after','info'):
            self.root.tk.call('after','cancel',task)
        self.root.destroy()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def pump(self):
        end=time.monotonic()+15
        while time.monotonic()<end:
            self.root.update()
            if self.app.job is not None and not self.app.layout_pending:
                return
            time.sleep(.01)
        self.fail('Preview did not finish rebuilding')

    def test_preview_rejects_click_outside_canvas_or_while_closing(self):
        a, pv = self.app, self.app.preview
        pv.T = (0, 0, 10, 0, 20)
        click = SimpleNamespace(x=0, y=0, x_root=100, y_root=100)
        with patch.object(a, "click_mode", return_value="goto"), \
                patch.object(a, "preview_clicked") as jog, \
                patch.object(pv.canvas, "winfo_containing", return_value=a.root) as target:
            pv._click(click)
            jog.assert_not_called()
            target.return_value = pv.canvas
            pv._click(click)
            jog.assert_called_once()
            a._closing = True
            pv._click(click)
            jog.assert_called_once()

    def test_scan_direction_rebuilds_same_art_without_changing_placement_or_power(self):
        a = self.app
        geom = a.job.geom
        cells = a.job.passes[0].cells.copy()
        values = (a.mat.power, a.mat.feed, a.mat.pitch, a.mat.style)
        a.scan_box.current(1)
        a._scan_pick()
        self.pump()
        self.assertEqual(a.mat.scan_direction, "forward")
        self.assertEqual(a.job.material.scan_direction, "forward")
        self.assertEqual(a.job.geom, geom)
        self.assertTrue((a.job.passes[0].cells == cells).all())
        self.assertEqual((a.mat.power, a.mat.feed, a.mat.pitch, a.mat.style), values)
        a.scan_box.current(0)
        a._scan_pick()
        self.pump()
        self.assertEqual(a.mat.scan_direction, "alternating")

    def test_return_speed_preserves_burn_and_saves_material_value(self):
        a = self.app
        a.scan_box.current(1)
        a._scan_pick()
        self.pump()
        planner.compile_job(a.job)
        before = [c for p in a.job.passes for c in p.commands]
        geom = a.job.geom
        cells = a.job.passes[0].cells.copy()
        settings = (a.mat.feed, a.mat.power, a.mat.pitch, a.mat.hop_feed)
        old = a.mat.row_feed
        for value in (4500, 5000, 6000):
            a.return_var.set(str(value))
            a._return_changed()
            self.pump()
            planner.compile_job(a.job)
            after = [c for p in a.job.passes for c in p.commands]
            expected = [c[:-len(f'F{old} S0')] + f'F{value} S0'
                        if c.startswith('G1 ') and c.endswith(f'F{old} S0') else c for c in before]
            self.assertEqual(after, expected)
            self.assertEqual(a.job.geom, geom)
            self.assertTrue((a.job.passes[0].cells == cells).all())
            self.assertEqual((a.mat.feed, a.mat.power, a.mat.pitch, a.mat.hop_feed), settings)
            from dataclasses import asdict
            self.assertEqual(presets.Material.from_dict(asdict(a.mat)).row_feed, value)
            self.assertIn(f'row return: {value} mm/min', '\n'.join(jobs.header(a.job, 'test')))
        for invalid in ('0', '6001', 'nan', 'inf', 'fast', '4500.5'):
            a.return_var.set(invalid)
            a._return_changed()
            self.assertEqual(a.mat.row_feed, 6000)
            self.assertEqual(a.return_var.get(), '6000')

    def test_window_close_waits_for_setup_disconnect_without_a_modal(self):
        a = self.app
        with patch.object(a, "disconnect") as disconnect, \
                patch.object(a.root, "after") as schedule, \
                patch.object(a.root, "destroy") as destroy, \
                patch("lps.app.messagebox.showinfo") as dialog:
            a.worker = object()
            a.on_close()
            a.on_close()
            disconnect.assert_called_once()
            schedule.assert_called_once_with(60, a._finish_close)
            destroy.assert_not_called()
            a.worker = None
            a._finish_close()
            destroy.assert_called_once()
            dialog.assert_not_called()

    def test_alignment_and_check_lifecycle_in_demo(self):
        a = self.app
        def until(predicate):
            end = time.monotonic() + 12
            while time.monotonic() < end:
                self.root.update()
                if predicate():
                    return
                time.sleep(.01)
            self.fail("Demo event did not arrive")

        a.goto(4)
        until(a.verified_layout)
        a.check_mode = "burn"
        a.preview.redraw()
        self.assertIsNotNone(a.preview._check_photo)
        a.connect()
        until(lambda: a.connected and a.last_status is not None)
        try:
            self.assertIsNone(a.head_position())
            with patch("lps.app_laser.messagebox.askokcancel", return_value=True), \
                    patch("lps.app_laser.messagebox.askyesno", return_value=True):
                a.set_origin()
                until(lambda: a.origin_set)
                initial = a.last_status
                initial_phys = tuple(a.worker.ctrl.phys)
                a.click_var.set("here")
                a.preview_clicked(2, 3, 2, 3)
                self.assertTrue(a.current_observation())
                self.assertTrue(machine.same_position(initial, a.last_status))
                a.apply_alignment()
                until(lambda: a.head_position() == (2, 3))
                self.assertEqual(tuple(a.worker.ctrl.phys), initial_phys)
                self.assertIsNone(a.observed_dot)

                positions = []
                a.event_hooks.append(lambda ev: positions.append(ev[1].wpos) if ev[0] == "status" else None)
                a.run_perimeter("travel")
                self.assertTrue(a.perim_running)
                until(lambda: not a.perim_running)
                self.assertGreater(len(set(positions)), 1)
                self.assertEqual(a.head_position(), (0, 0))
                self.assertFalse(a.worker.ctrl.burns)
                self.assertFalse(a.ready_items()[4][0])

                a.run_perimeter("sticker")
                self.assertTrue(a.perim_running)
                a.stop_perimeter()
                until(lambda: not a.perim_running)
                self.assertNotIn("sticker", a.completed_checks)
                a.run_perimeter("sticker")
                self.assertTrue(a.perim_running)
                until(lambda: not a.perim_running)
                self.assertTrue(a.ready_items()[4][0])

                a.run_perimeter("image")
                self.assertTrue(a.perim_running)
                a.disconnect()
                until(lambda: a.worker is None)
                self.assertFalse(a.perim_running)
                self.assertFalse(a.completed_checks)
                a.connect()
                until(lambda: a.connected and a.last_status is not None)
                self.assertFalse(a.origin_set)
        finally:
            a.disconnect(wait=True)

    def test_saved_size_box_origin_and_perimeter_stay_together(self):
        a=self.app
        self.assertTrue(a.exact_var.get())
        self.assertEqual(a.picture_box(),(0,0,14,19))
        self.assertIn('Lower-left X 0.000, Y 0.000',a.box_lbl.cget('text'))
        # White padding does not move the frame to the first dark pixel.
        self.assertNotEqual(a.job.burn_bbox(),a.picture_box())
        for w,h in ((14.29,19.05),(1.8,20.64)):
            a.pw_var.set(str(w)); a.ph_var.set(str(h)); a._piece_edited()
            self.assertTrue(a.layout_pending)
            self.assertTrue(all('disabled' in b.state() for b in a.check_buttons.values()))
            self.pump()
            self.assertAlmostEqual(a.job.geom.art_w,w)
            self.assertAlmostEqual(a.job.geom.art_h,h)
            pts=planner.perimeter_points(a.picture_box())
            self.assertEqual(pts[0][:2],(0,0))
            self.assertAlmostEqual(max(p[0] for p in pts),w)
            self.assertAlmostEqual(max(p[1] for p in pts),h)
        # A material template cannot replace an explicitly sized image.
        a.select_material('pine-layers')
        self.pump()
        self.assertEqual((a.piece['w'],a.piece['h']),(1.8,20.64))
        self.assertTrue(a.exact_var.get())
        a.pw_var.set('14.29')
        a._piece_edited('w')
        a.ph_var.set('19.05')
        a._piece_edited('h')
        self.pump()
        self.assertEqual(a.picture_box(),(0,0,14.29,19.05))
        self.assertAlmostEqual(a.job.geom.art_w,14.29)
        self.assertAlmostEqual(a.job.geom.art_h,19.05)

    def test_proportions_are_a_separate_visible_choice(self):
        a=self.app
        a.proportions_var.set(True)
        a.pw_var.set('7')
        a._piece_edited('w')
        self.pump()
        self.assertAlmostEqual(a.piece['h'],9.5)
        a.proportions_var.set(False)
        a.ph_var.set('19')
        a._piece_edited('h')
        self.pump()
        self.assertAlmostEqual(a.piece['w'],7)
        self.assertAlmostEqual(a.piece['h'],19)

    def test_prepared_import_does_not_reinvert_when_material_changes(self):
        path=self.folder/'roof-IMPORT.png'
        path.write_bytes(self.picture.read_bytes())
        a=self.app
        a.open_picture(path)
        self.pump()
        self.assertFalse(a.v_neg.get())
        a.select_material('anodized-dots')
        self.pump()
        self.assertFalse(a.v_neg.get())
        self.assertEqual(a.picture_box(),(0,0,14,19))

    def test_preview_drag_moves_and_resizes_window_without_machine_motion(self):
        a=self.app
        a.use_car(presets.car_values('sports'))
        self.pump()
        a.goto(2)
        a.zone_edit_var.set(True)
        a.select_keepout(0)
        z=dict(a.piece['keepouts'][0])
        pv=a.preview
        pv.T=(0,0,10,-30,30)
        def event(x,y):
            px0,py0,_,_=planner.piece_rect(a.job.piece)
            return SimpleNamespace(x=(px0+x+30)*10,y=(30-py0-y)*10)
        a.origin_set=True
        a.completed_checks["sticker"] = a.check_key()
        origin=planner.piece_rect(a.piece)[:2]
        with patch.object(machine,'move_off') as motion:
            pv._zone_press(event(z['x']+z['w']/2,z['y']+z['h']/2))
            pv._zone_motion(event(z['x']+z['w']/2+1,z['y']+z['h']/2+1))
            pv._zone_release(None)
            self.pump()
            moved=dict(a.piece['keepouts'][0])
            self.assertAlmostEqual(moved['x'],z['x']+1,places=2)
            self.assertFalse(a.completed_checks)
            self.assertEqual(origin,planner.piece_rect(a.piece)[:2])
            # Direct corner drag is the resize action, not a machine jog.
            pv.T=(0,0,10,-30,30)
            pv._zone_press(event(moved['x']+moved['w'],moved['y']+moved['h']))
            pv._zone_motion(event(moved['x']+moved['w']+1,moved['y']+moved['h']+.5))
            pv._zone_release(None)
            self.pump()
            self.assertAlmostEqual(a.piece['keepouts'][0]['w'],moved['w']+1,places=2)
            motion.assert_not_called()
        self.assertFalse(a.job.passes[0].cells[~a.job.allowed].any())


class SpeedValue(unittest.TestCase):
    def test_slow_speeds_allowed_and_changes_explained(self):
        from lps.app import speed_value
        self.assertEqual(speed_value(140.0), (140, ""))
        self.assertEqual(speed_value(50.0), (50, ""))
        v, note = speed_value(12.0)
        self.assertEqual(v, 12)
        self.assertIn("24 mm/min", note)                     # accepted, with the measured-floor caution
        self.assertEqual(speed_value(7000.0)[0], 6000)
        self.assertIn("6000", speed_value(7000.0)[1])
        self.assertEqual(speed_value(0.0)[0], 1)
        self.assertIn("changed", speed_value(12.4)[1])

