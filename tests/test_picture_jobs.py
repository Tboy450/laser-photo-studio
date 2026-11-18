"""Native picture jobs retain editable source and settings; no physical serial access."""
import copy
import tempfile
import time
import tkinter as tk
import unittest
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from lps import imaging, jobs, machine, picture_jobs, planner, presets, simulate, verify
from lps.app import App


class PictureJobUI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)
        self.patches=[patch.object(jobs,'SETTINGS_FILE',self.path/'settings.json'),
                      patch.object(jobs,'LOCK_FILE',self.path/'sender.lock'),
                      patch.object(jobs,'JOBS_DIR',self.path/'jobs'),
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

