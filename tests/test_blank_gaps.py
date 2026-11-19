"""Fast blank travel must change only S0 feed, with legacy replay and editable saving intact."""
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from lps import jobs,picture_jobs,planner,presets,verify

class BlankGaps(unittest.TestCase):
    def build(self,fast=False,direction='forward',feed=140,travel=3000):
        im=Image.new('L',(240,160),255);d=ImageDraw.Draw(im)
        d.rectangle((10,10,25,150),fill=0);d.rectangle((210,10,225,150),fill=0)
        mat=presets.BUILTIN[0].copy(style='threshold',pitch=.1,feed=feed,power=800,
            interlace=1,passes=1,thin_pass=False,scan_direction=direction,row_feed=travel,
            runup=1,fast_blank_gaps=fast,blank_feed=travel)
        piece=dict(name='test',w=24.,h=16.,margin=0.,corner=0.,holes=[],origin='center')
        placement=planner.Placement(piece,art_w=24.)
        look=dict(brightness=0,contrast=0,gamma=1,sharpen=0,autolevel=False,negative=False,black_point=0,white_point=255)
        job=planner.compile_job(planner.build_job(im,mat,placement,look=look))
        return im,job,look

    def test_legacy_default_and_round_trip(self):
        old=asdict(presets.BUILTIN[0]);old.pop('fast_blank_gaps')
        self.assertFalse(presets.Material.from_dict(old).fast_blank_gaps)
        mat=presets.Material.from_dict(old).copy(fast_blank_gaps=True)
        self.assertEqual(presets.Material.from_dict(asdict(mat)),mat)
        with self.assertRaises(ValueError):mat.copy(fast_blank_gaps='false')

    def test_only_zero_power_feeds_change_in_both_directions(self):
        for direction in ('forward','alternating'):
            _,a,_=self.build(direction=direction);_,b,_=self.build(True,direction)
            self.assertTrue(verify.verify_job(b)['ok'])
            np.testing.assert_array_equal(a.passes[0].cells,b.passes[0].cells)
            pa=[c for c in a.passes[0].commands if not c.endswith(' S0')]
            pb=[c for c in b.passes[0].commands if not c.endswith(' S0')]
            self.assertEqual(pa,pb)                      # every mark and mode command identical
            fast=[c for c in b.passes[0].commands if c.endswith(' S0') and ' F3000 ' in c]
            self.assertGreater(len(fast),100)            # long gaps got a fast middle
            self.assertLess(b.est_s,a.est_s*.6)

    def test_short_gaps_and_runups_unchanged(self):
        cells=np.array([[800,0,0,800,0,800]],dtype=np.int16)
        g=planner.Geometry(.1,6,1,0,.1,None,(0,0,.6,.1),(0,0,.6,.1))
        a=planner.raster_commands(cells,None,g,140,3000,1)
        b=planner.raster_commands(cells,None,g,140,3000,1,fast_blank_gaps=True)
        self.assertEqual(a,b)

    def test_slower_return_never_slows_blank_gaps(self):
        _,a,_=self.build(feed=140,travel=60)
        _,b,_=self.build(True,feed=140,travel=60)
        self.assertEqual(a.passes[0].commands,b.passes[0].commands)

    def test_verifier_rejects_powered_travel_feed(self):
        _,job,_=self.build(True)
        cmds=job.passes[0].commands
        idx=next(i for i,c in enumerate(cmds) if c.endswith(' S800'))
        cmds[idx]=cmds[idx].replace(' F140 ',' F3000 ')
        report=verify.verify_job(job)
        self.assertFalse(report['ok'])
        self.assertIn('powered speed',str(report))

    def test_saved_source_rebuilds_exactly_with_fast_gaps(self):
        im,job,look=self.build(True)
        with tempfile.TemporaryDirectory() as td:
            folder=jobs.save_job(job,verify.verify_job(job),picture=im,folder=Path(td)/'job',
                extra=dict(look=look,placement=dict(fit='whole',art_w=24.,dx=0.,dy=0.)))
            rebuilt=picture_jobs.read(folder)[2]
            self.assertTrue(rebuilt.material.fast_blank_gaps)
            self.assertEqual(rebuilt.passes[0].commands,job.passes[0].commands)

if __name__=='__main__':unittest.main()
