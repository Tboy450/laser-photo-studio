"""Software tin jig: layouts, independent nudges, per-tin jobs, true traces, stale-job detection, fit report."""
import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from lps import ladder, presets, tinjig, verify

PIECE = ladder.lid_piece()


def art():
    im = Image.new("L", (457, 457), 255)
    ImageDraw.Draw(im).ellipse((60, 60, 397, 397), outline=0, width=40)
    return im


def mat():
    base = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
    return base.copy(style="threshold", look="tin", negative=False, power=1000, feed=140, pitch=0.15,
                     scan_direction="forward", row_feed=6000, runup=1.0)


class Layouts(unittest.TestCase):
    def test_seven_across_presets(self):
        lay = tinjig.preset("20 = 7 + 7 + 6 (last slot off)")
        self.assertEqual((lay.cols, lay.rows, len(lay.slots), len(lay.enabled())), (7, 3, 21, 20))
        self.assertFalse(lay.slots[20].enabled)
        self.assertEqual(lay.centre(0), (0.0, 0.0))                     # zero at tin 1's centre
        self.assertEqual(lay.centre(6), (304.8, 0.0))                   # seven across X at 50.8 mm
        self.assertEqual(lay.centre(7), (0.0, -50.8))                   # second row below
        for name, n in (("18 = 7 + 7 + 4", 18), ("16 = 7 + 7 + 2", 16), ("7 x 2 (14)", 14), ("24 (6 x 4)", 24)):
            self.assertEqual(len(tinjig.preset(name).enabled()), n)

    def test_nudges_survive_group_moves_and_save(self):
        lay = tinjig.preset("7 x 3 (21)")
        lay.nudge([3], 0.4, -0.2)
        lay.move_group(1.0, 2.0)
        self.assertEqual(lay.centre(3), (round(3 * 50.8 + 1.4, 3), 1.8))  # its own nudge kept
        self.assertEqual(lay.centre(4), (round(4 * 50.8 + 1.0, 3), 2.0))  # neighbours only moved with the group
        back = tinjig.Layout.from_dict(lay.to_dict())
        self.assertEqual([back.centre(i) for i in range(21)], [lay.centre(i) for i in range(21)])
        with self.assertRaises(ValueError):
            tinjig.Layout.from_dict(dict(lay.to_dict(), mystery=1))      # unknown settings are refused, not dropped

    def test_done_tins_are_protected(self):
        lay = tinjig.preset("6 (3 x 2)")
        lay.slots[0].done = True
        with self.assertRaises(ValueError):
            lay.nudge([0], 0.1, 0)
        with self.assertRaises(ValueError):
            lay.move_group(1, 0)
        lay.nudge([1], 0.1, 0)                                         # an un-burned tin can still be fixed
        self.assertEqual(lay.queue(), [1, 2, 3, 4, 5])                  # the rest of the queue continues

    def test_fit_report(self):
        lay = tinjig.preset("7 x 3 (21)")
        r = tinjig.fit_report(lay, 45.72, 2.0)
        self.assertAlmostEqual(r["width"], 304.8 + 45.72 + 4.0, places=1)
        self.assertTrue(r["fits_travel"])                               # within the controller's 420 x 400
        self.assertGreater(r["free_from_zero"]["right"], 300)           # zero at tin 1 needs room to the right
        big = tinjig.Layout(name="10 across", cols=8, rows=1, pitch_x=60)
        self.assertFalse(tinjig.fit_report(big, 45.72, 2.0)["fits_travel"])


class TinJobs(unittest.TestCase):
    def test_each_tin_is_its_own_checked_job_at_its_slot(self):
        lay = tinjig.preset("7 x 2 (14)")
        lay.nudge([8], 0.5, -0.3)
        m = mat()
        job = tinjig.slot_job(art(), m, lay, 8, PIECE, 45.72)
        self.assertTrue(verify.verify_job(job)["ok"])
        cx, cy = lay.centre(8)
        x0, y0, x1, y1 = job.burn_bbox()
        self.assertAlmostEqual((x0 + x1) / 2, cx, delta=0.2)
        self.assertAlmostEqual((y0 + y1) / 2, cy, delta=0.2)
        self.assertFalse(tinjig.is_stale(job, lay, m, 45.72))
        lay.nudge([8], 0.1, 0)
        self.assertTrue(tinjig.is_stale(job, lay, m, 45.72))           # a nudge makes the old G-code stale
        with self.assertRaises(ValueError):
            tinjig.slot_job(art(), m, tinjig.preset("20 = 7 + 7 + 6 (last slot off)"), 20, PIECE, 45.72)

    def test_round_tin_traces_a_circle_not_a_square(self):
        lay = tinjig.preset("6 (3 x 2)")
        path = tinjig.image_trace(lay, 4, PIECE)
        cx, cy = lay.centre(4)
        radii = [math.hypot(x - cx, y - cy) for x, y in path]
        self.assertAlmostEqual(min(radii), 45.72 / 2, places=2)
        self.assertAlmostEqual(max(radii), 45.72 / 2, places=2)
        sel = tinjig.traces(lay, PIECE, "image", indices=[0, 2])
        self.assertEqual(len(sel), 2)
        job = tinjig.slot_job(art(), mat(), lay, 4, PIECE, 45.72)
        box = tinjig.travel_trace(job)
        self.assertEqual(len(box), 5)                                   # the travel envelope is a box, by design


if __name__ == "__main__":
    unittest.main()
