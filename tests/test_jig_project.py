import tempfile
import unittest
import time
import tkinter as tk
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from lps import jig_project, jobs, picture_jobs, planner, presets, tinjig, verify
from lps.app import App


class JigProjectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.project = jig_project.Project(tinjig.preset("6 (3 x 2)", pitch_x=54, pitch_y=54))
        self.piece = presets.PIECES["tin51face"]
        self.mat = presets.BUILTIN[0].copy(style="threshold", look="tin", negative=False, pitch=.15,
                                           scan_direction="forward")

    def source(self, name, pitch=.15):
        image = Image.new("L", (40, 20), 255)
        ImageDraw.Draw(image).rectangle((2, 1, 34, 12), fill=0)
        position = dict(fit="whole", art_w=12., dx=1.5, dy=-.6)
        job = planner.compile_job(planner.build_job(image, self.mat.copy(pitch=pitch),
                                  planner.Placement(self.piece, **position), name=name))
        folder = jobs.save_job(job,verify.verify_job(job),picture=image,extra=dict(placement=position),
                               folder=self.root/name)
        return jig_project.Layer.checked(folder)

    def test_pocket_moves_keep_burn_map_recipe_other_pockets_and_shared_zero(self):
        item=self.source("one")
        self.project.layers={0:[item], 4:[item]}
        self.project.layout.nudge([4], .6, -.3)
        before=self.project.check(0)[0][0]
        placed=self.project.check(4)[0][0]
        np.testing.assert_array_equal(before.passes[0].cells,placed.passes[0].cells)
        self.assertEqual(placed.material,before.material)
        self.assertAlmostEqual(placed.geom.x0-before.geom.x0,54.6)
        self.assertAlmostEqual(placed.geom.yt-before.geom.yt,-54.3)
        path=self.root/'layout.lpsjig'
        self.project.save(path)
        other=jig_project.Project.read(path)
        self.assertEqual(other.layout,self.project.layout)
        self.assertEqual(other.check(4)[0][0].passes[0].commands,placed.passes[0].commands)
        Path(item.path).write_text("{}")
        with self.assertRaisesRegex(ValueError,"changed on disk"):
            other.check(4)

    def test_turned_artwork_preserves_dimensions_scan_direction_and_layers(self):
        self.project.layers[4]=[self.source("one"),self.source("two")]
        original=self.project.check(4)[0][0]
        self.project.layout.slots[4].rot=1
        a,b=[p[0] for p in self.project.check(4)]
        self.assertEqual((a.geom.cols,a.geom.rows),(original.geom.rows,original.geom.cols))
        self.assertEqual(a.material.scan_direction,"forward")
        self.assertFalse(picture_jobs.registration_conflicts(a,b))
        self.project.layers[4][1]=self.source("wrong-pitch",.10)
        with self.assertRaisesRegex(ValueError,"do not register"):
            self.project.check(4)

    def test_stagger_and_rejected_multi_nudge_do_not_move_neighbours(self):
        lay=self.project.layout
        lay.stagger_x=6
        self.assertEqual(lay.centre(3),(6.,-54.))
        lay.slots[1].done=True
        with self.assertRaises(ValueError):
            lay.nudge([0,1],.5,2)
        self.assertEqual(lay.centre(0),(0.,0.))
        self.assertEqual(self.project.neighbouring_pockets(0,55),[2,4])

    def test_flush_three_by_three_full_face_keeps_source_grid_at_fractional_centres(self):
        project=jig_project.Project(tinjig.flush_layout())
        image=Image.new("L",(340,340),0)
        placement=dict(fit="whole",art_w=51.,dx=0.,dy=0.)
        job=planner.compile_job(planner.build_job(image,self.mat,planner.Placement(self.piece,**placement)))
        folder=jobs.save_job(job,verify.verify_job(job),picture=image,extra=dict(placement=placement),folder=self.root/"disk")
        layer=jig_project.Layer.checked(folder)
        original=layer.read()
        for i in project.layout.enabled():
            project.layers[i]=[layer]
            placed,report,_=project.check(i,lambda _:original)[0]
            dx,dy=project.layout.centre(i)
            self.assertAlmostEqual(placed.geom.x0,job.geom.x0+dx,places=8)
            self.assertAlmostEqual(placed.geom.yt,job.geom.yt+dy,places=8)
            self.assertTrue(report["ok"])
            np.testing.assert_array_equal(placed.passes[0].cells,job.passes[0].cells)
        path=self.root/"flush.lpsjig"
        project.save(path)
        with patch.object(jobs,"JOBS_DIR",self.root/"placed"):
            folder=project.prepare(path,1,0)
        self.assertEqual(picture_jobs.read(folder)[2].geom,project.check(1)[0][0].geom)

    def test_selected_layer_reopens_and_stale_pocket_cannot_launch(self):
        p=self.project
        p.layers[4]=[self.source("first"),self.source("second")]
        saved=self.root/"carton.lpsjig"
        p.save(saved)
        with patch.object(jobs,"JOBS_DIR",self.root/"placed"):
            folder=p.prepare(saved,4,1)
        _,_,job,report,_,_,meta=picture_jobs.read(folder)
        ref=meta["jig_reference"]
        self.assertTrue(report["ok"])
        self.assertEqual(job.name,"Pocket 5 - second")
        self.assertEqual(job.geom,p.check(4)[1][0].geom)
        p.layout.nudge([2],.5,0)
        p.save(saved)
        jig_project.validate_placement(ref, job)
        p.layout.nudge([4],.5,0)
        window=SimpleNamespace(winfo_exists=lambda:True,file=saved,project=p)
        with self.assertRaisesRegex(ValueError,"jig editor"):
            jig_project.validate_placement(ref,job,window)
        with self.assertRaisesRegex(ValueError,"Save the jig"):
            p.prepare(saved,4,1)
        p.save(saved)
        with self.assertRaisesRegex(ValueError,"saved pocket changed"):
            jig_project.validate_placement(ref,job)
        app=SimpleNamespace(_closing=False,root=None,_jig_placement_ok=lambda ref,j:False)
        from lps.app_laser import LaserMixin
        with patch.object(jobs,"launch_runner",side_effect=AssertionError("stale job launched")):
            LaserMixin.launch(app,folder,{})

    def test_normal_jig_window_select_check_save_and_reopen(self):
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        app = SimpleNamespace(root=root)
        App.open_tin_jig(app)
        window = app._jig_window
        self.addCleanup(window.destroy)
        layer = self.source("mask")
        window.select(4)
        window.add_path(layer.path)
        with patch("tkinter.messagebox.askyesno",return_value=True):
            window.fill_empty()
        self.assertEqual((window.project.layout.cols,window.project.layout.rows),(3,3))
        self.assertEqual(window.project.layout.pitch_x,52.3875)
        self.assertEqual(window.project.layout.centre(8),(104.775,-104.775))
        self.assertEqual(len(window.project.layers),9)
        window.check(whole=True)
        deadline = time.monotonic()+12
        while window.check_stop and time.monotonic()<deadline:
            root.update()
            time.sleep(.01)
        self.assertIn("9 assigned pocket(s) checked",window.status.get())
        self.assertEqual(window.checked[0][0].material.scan_direction,"forward")
        self.assertEqual(window.map_mode.get(),"Travel")
        for mode in ("Image circle","Burn map"):
            window.map_mode.set(mode)
            window.display()
        file=self.root/"carton.lpsjig"
        with patch("tkinter.filedialog.asksaveasfilename",return_value=str(file)):
            self.assertTrue(window.save())
        with patch("tkinter.filedialog.askopenfilename",return_value=str(file)):
            window.open()
        self.assertEqual(window.index,0)
        self.assertFalse(window.checked)
        self.assertEqual(window.project.layers[4],[layer])

    def test_run_list_through_check_and_saved_runner_history(self):
        from lps.jig_runlist import RunList
        from lps.fakegrbl import FakeController, FakeWire
        from lps.runner import Runner
        project = jig_project.Project(tinjig.flush_layout())
        pair = [self.source("first"), self.source("second")]
        project.layers = {i: pair.copy() for i in project.layout.enabled()}
        path = self.root / "nine.lpsjig"
        project.save(path)
        root = tk.Tk()
        root.withdraw()
        try:
            app = App(root, SimpleNamespace(demo=True, picture=None, perimeter=None))
            app.open_tin_jig()
            jig = app._jig_window
            jig.file, jig.project = path, project
            with patch.object(jobs, "JOBS_DIR", self.root / "prepared"), patch.object(jobs, "LOCK_FILE", self.root / "lock"):
                jig.open_run_list()
                win = jig._run_list
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    win.new()
                batch = win.batch
                self.assertEqual(len(batch.entries), 18)
                self.assertEqual(win.rows.set("1", "state"), "Waiting for earlier layer")
                win.prepare(True)
                self.assertEqual(app.nb.index("current"), 3)
                folder = app.save_current_job(quiet=True)
                ref = jobs.read_json(folder/"job.json")["jig_reference"]
                self.assertEqual(ref["run_list"]["row"], 0)
                self.assertEqual(batch.records(), {})  # Preparing alone never completes a layer.
                spec = dict(start_pass=0, start_index=0, lead=[], expected_start=[0., 0.],
                            pause_between=False, park=[0., 0.])
                jobs.write_json(folder/"run.json", dict(spec, demo=True))
                jobs.write_json(folder/"state.json", dict(phase="complete", demo=True))
                self.assertEqual(batch.records(), {})
                jobs.write_json(folder/"run.json", dict(spec, demo=False))
                jobs.write_json(folder/"state.json", dict(phase="dropout", demo=False))
                win.refresh()
                self.assertIn("dropout", win.rows.set("0", "state"))
                self.assertEqual(win.rows.set("1", "state"), "Review pocket run")
                with self.assertRaisesRegex(ValueError, "dropout"):
                    jig_project.validate_placement(ref,app.job)
                jig_project.validate_placement(ref, app.job, resume_folder=folder)
                c = FakeController(speedup=5000)
                c.take_output()
                self.assertEqual(Runner(folder,wire=FakeWire(c),settle=0).run(), "complete")
                jig.open_run_list()
                win = jig._run_list
                self.assertEqual(win.batch.batch, batch.batch)
                self.assertEqual(win.rows.set("0","state"), "Finished")
                self.assertEqual(win.rows.set("1","state"), "Ready")
                with self.assertRaisesRegex(ValueError, "Finished"):
                    jig_project.validate_placement(ref, app.job, resume_folder=folder)
                win.prepare(True)
                self.assertEqual(app.source_provenance["jig_reference"]["run_list"]["row"], 1)
                project.layout.nudge([0], .3, 0)
                project.save(path)
                self.assertEqual(batch.status(1,project,batch.records()), "Placement changed after printing")
                self.assertEqual(batch.status(2,project,batch.records()), "Ready")
                fresh = RunList.create(path)
                self.assertFalse(fresh.records())
                self.assertEqual(fresh.status(0,project,{}), "Ready")
        finally:
            for event in root.tk.call("after","info"):
                root.tk.call("after","cancel",event)
            root.destroy()

    def test_normal_checker_and_simulated_sender_use_only_selected_pocket(self):
        from lps.fakegrbl import FakeController, FakeWire, coverage
        from lps.runner import Runner
        project = self.project
        project.layers[0] = project.layers[4] = [self.source("test art")]
        path = self.root / "tray.lpsjig"
        project.save(path)
        root = tk.Tk()
        root.withdraw()
        try:
            app = App(root,SimpleNamespace(demo=True, picture=None, perimeter=None))
            app.open_tin_jig()
            win = app._jig_window
            win.project, win.file = project, path
            win.select(4)
            win.checked = project.check(4)
            with patch.object(jobs,"JOBS_DIR",self.root/"prepared"), patch.object(jobs,"LOCK_FILE",self.root/"sender.lock"):
                win.open_selected()
                self.assertEqual(app.nb.index("current"),3)
                self.assertIn("Pocket 5",app.job.name)
                self.assertFalse(app.connected)
                folder = Path(app.source_provenance["folder"])
                jobs.write_json(folder/"run.json",dict(start_pass=0,start_index=0,lead=[],expected_start=[0.,0.],
                                                        pause_between=False,park=[0.,0.]))
                controller = FakeController(speedup=5000)
                controller.take_output()
                self.assertEqual(Runner(folder, wire=FakeWire(controller), settle=0).run(),"complete")
                np.testing.assert_allclose(coverage(controller,app.job.geom),app.job.passes[0].cells>0,atol=1e-5)
                self.assertEqual(tuple(controller.phys[:2]),(0.,0.))
                self.assertEqual(controller.modal["spindle"],"M5")
                app.connected=True
                app.origin_set=True
                app.last_status=SimpleNamespace(idle_off=True, wpos=(0,0,0))
                with patch.object(app, "status_stale", return_value=False), patch.object(app,"refresh_laser_page"):
                    self.assertTrue(app.open_saved_job(folder))
                    self.assertTrue(app.origin_set)
                    app.last_status.wpos = (54,-54,0)
                    self.assertTrue(app.open_saved_job(folder))
                    self.assertFalse(app.origin_set)
                app.connected=False
        finally:
            for event in root.tk.call("after","info"):
                root.tk.call("after","cancel",event)
            root.destroy()
