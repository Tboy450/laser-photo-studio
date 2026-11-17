"""Existing sample records retain provenance; learning never changes a job or recipe."""
import json,runpy,tempfile,tkinter as tk,unittest
from pathlib import Path
from unittest.mock import patch, Mock
from PIL import Image
from lps import samples,presets,helptext
from lps.sample_view import EvidenceDialog

class SampleEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.p=patch.object(samples,'USER_DIR',self.root);self.p.start()
        self.folder=self.root/'mine';self.folder.mkdir()
        Image.new('RGB',(12,12),'white').save(self.folder/'photo.jpg')
        self.record=dict(file='photo.jpg',title='Old photo',kind='test',caption='Original notes',date='2026-11-01',source='original.png',future_field=4)
        (self.folder/'photos.json').write_text(json.dumps([self.record]))
    def tearDown(self):
        self.p.stop();self.tmp.cleanup()
    def test_legacy_photo_remains_unknown_until_recorded(self):
        s=samples.user_samples('mine')[0]
        self.assertEqual(samples.evidence_state(s),'Not recorded');self.assertEqual(s.source,'original.png')
    def test_edit_survives_reload_preserving_source_and_future_fields(self):
        s=samples.user_samples('mine')[0]
        values=dict(state='Operator report',substrate='reflective lid; alloy unknown',row_pitch='N/A: vector',mode='M4',commanded_feed='240',motion_evidence='not independently measured',surface='sanding unknown',result='operator links penetration to sequence; exact segment unknown')
        samples.update_user_evidence(s,values)
        row=json.loads((self.folder/'photos.json').read_text())[0]
        for k,v in self.record.items():self.assertEqual(row[k],v)
        self.assertEqual(samples.user_samples('mine')[0].evidence,values)
    def test_invalid_state_or_field_does_not_write(self):
        s=samples.user_samples('mine')[0];path=self.folder/'photos.json';before=path.read_bytes()
        for values in [dict(state='universally proven'),dict(power_pct=80),dict(private_sms='do not store')]:
            with self.assertRaises(ValueError):samples.update_user_evidence(s,values)
        self.assertEqual(path.read_bytes(),before)
    def test_failed_save_does_not_change_memory_or_original_record(self):
        s=samples.user_samples('mine')[0];path=self.folder/'photos.json';before=path.read_bytes()
        with patch('lps.jobs.write_json',side_effect=OSError('test disk failure')):
            with self.assertRaises(OSError):samples.update_user_evidence(s,dict(state='Prepared - not run'))
        self.assertEqual(s.evidence,{});self.assertEqual(path.read_bytes(),before)
    def test_builtin_evidence_and_generator_are_consistent(self):
        doc=samples.builtin_index();record=doc['samples']['red-hill-speed-floor']
        mod=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/make_samples.py'))
        self.assertEqual(record['evidence'],mod['SAMPLES']['red-hill-speed-floor']['evidence'])
        mat=next(m for m in presets.BUILTIN if m.key=='lid-halftone')
        items,note=samples.for_material(mat)
        s=next(s for s in items if s.path.name=='red-hill-speed-floor.jpg')
        self.assertEqual(samples.evidence_state(s),'Physical test')
        self.assertIn('not evidence for this halftone recipe',note)
        with self.assertRaises(ValueError):samples.update_user_evidence(s,dict(state='Repeated physical tests'))
    def test_guide_separates_latest_corrections_and_proposals(self):
        t=helptext.LEARNING
        for phrase in ['not independent motion','56 damaged book pages','F240','None of these has raster DPI','M3','not physically run','different proposed surface comparison','0.10 mm']:
            self.assertIn(phrase,t)
    def test_user_dialog_saves_and_builtin_dialog_is_readonly(self):
        root=tk.Tk();root.withdraw()
        try:
            callback=Mock()
            s=samples.user_samples('mine')[0];dialog=EvidenceDialog(root,s,on_saved=callback);dialog.withdraw()
            self.assertEqual(len(dialog.vars),sum(len(g) for g in samples.EVIDENCE_GROUPS.values()))
            dialog.vars['state'].set('Physical test');dialog.vars['row_pitch'].set('0.10');dialog.save()
            self.assertEqual(samples.user_samples('mine')[0].evidence['row_pitch'],'0.10')
            callback.assert_called_once()
            s.user=False;dialog=EvidenceDialog(root,s);dialog.withdraw()
            widgets=[]
            def walk(w):
                widgets.extend(w.winfo_children())
                for c in w.winfo_children():walk(c)
            walk(dialog)
            entries=[w for w in widgets if w.winfo_class()=='TEntry']
            self.assertTrue(entries);self.assertTrue(all(w.instate(['readonly']) for w in entries))
            self.assertFalse(any(w.winfo_class()=='TButton' and w.cget('text')=='Save test record' for w in widgets))
            dialog.destroy()
        finally:root.destroy()
