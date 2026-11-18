import copy
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from lps import slate_tones
import test_picture_jobs as fixtures


class ToneOptions(unittest.TestCase):
    def test_comparisons_preserve_inputs_and_reduce_light_marks_for_both_polarities(self):
        picture=Image.fromarray(np.tile(np.arange(256,dtype=np.uint8),(150,1)))
        for negative in (True,False):
            look=dict(brightness=0,contrast=0,gamma=1,sharpen=0,autolevel=False,
                      negative=negative,black_point=0,white_point=255)
            original=copy.deepcopy(look);pixels=picture.tobytes()
            choices=slate_tones.options(look)
            means=[np.asarray(slate_tones.preview(picture,v)).mean() for _,v in choices]
            self.assertEqual(look,original);self.assertEqual(picture.tobytes(),pixels)
            self.assertGreater(means[0],means[1]);self.assertGreater(means[1],means[2])
            allowed={'black_point'} if negative else {'white_point'}
            for _,option in choices:
                self.assertLessEqual({k for k in look if look[k]!=option[k]},allowed)

    def test_no_invalid_or_duplicate_extreme_choices(self):
        self.assertEqual(len(slate_tones.options(dict(black_point=254,white_point=255,negative=True))),1)
        with self.assertRaises(ValueError):slate_tones.options(dict(black_point=255,white_point=0))


class SlateToneUI(unittest.TestCase):
    setUp = fixtures.PictureJobUI.setUp
    tearDown = fixtures.PictureJobUI.tearDown
    def test_apply_changes_only_visible_point_not_recipe_geometry_or_other_look(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder))
        before=copy.deepcopy(a.build_params());source=a.picture.tobytes()
        self.assertTrue(a.apply_slate_comparison(a.gen,24))
        after=a.build_params()
        self.assertEqual(before[0],after[0]);self.assertEqual(before[1],after[1])
        expected=dict(before[2],black_point=24);self.assertEqual(after[2],expected)
        self.assertEqual(source,a.picture.tobytes())
        self.assertFalse(a.apply_slate_comparison(a.gen-1,36))
        with patch('lps.app_place.jobs.active_runner',return_value='running'):
            self.assertFalse(a.apply_slate_comparison(a.gen,36))
        a.mat=a.mat.copy(look='pine')
        self.assertFalse(a.apply_slate_comparison(a.gen,36))

    def test_cancel_leaves_current_job_and_settings_untouched_and_helper_is_slate_only(self):
        a=self.a;self.assertTrue(a.open_saved_job(self.folder));self.root.update()
        before=copy.deepcopy(a.build_params());generation=a.gen;job=a.job
        self.assertEqual(a.slate_compare_btn.winfo_manager(),'pack')
        a.compare_slate_tones()
        windows=[w for w in self.root.winfo_children() if w.winfo_class()=='Toplevel']
        self.assertEqual(len(windows),1)
        self.assertFalse(windows[0].grab_current())
        windows[0].destroy()
        self.assertEqual(before,a.build_params());self.assertEqual(generation,a.gen);self.assertIs(job,a.job)
        a.select_material('pine-layers');a.sync_picture_edit_mode()
        self.assertEqual(a.slate_compare_btn.winfo_manager(),'')
