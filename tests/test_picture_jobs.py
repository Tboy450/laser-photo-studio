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

from lps import jobs, machine, picture_jobs, planner, presets, verify
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
        self.look=dict(brightness=0,contrast=13,gamma=1.,sharpen=30,negative=True,autolevel=False)
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
        self.assertEqual(asdict(a.mat),asdict(self.job.material))
        self.assertEqual(a.tree.selection(),('m:imported-test',))
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

