"""Shaped pieces keep artwork and stock geometry separate."""
import unittest

import numpy as np
from PIL import Image

from lps import planner, presets, verify

CROSS = [[20, 0], [40, 0], [40, 60], [60, 60], [60, 80], [40, 80], [40, 100], [20, 100], [20, 80], [0, 80],
         [0, 60], [20, 60]]


def piece():
    return dict(name="test cross", shape="rect", w=60.0, h=100.0, origin="center", margins=(0, 0, 0, 0), corner=0.0,
                keepouts=[], outline=CROSS)


def job():
    mat = presets.BUILTIN[0].copy(style="threshold", pitch=0.5, negative=False, interlace=1, passes=1,
                                  thin_pass=False, scan_direction="forward")
    return planner.compile_job(planner.build_job(Image.new("L", (120, 200), 0), mat,
                                                 planner.Placement(piece(), fit="exact")))


class OutlinePiece(unittest.TestCase):
    def test_marks_stay_inside_the_outline(self):
        j = job()
        self.assertTrue(verify.verify_job(j)["ok"])
        g = j.geom
        burned = j.passes[0].cells > 0
        xs = g.x0 + (np.arange(g.cols) + 0.5) * g.x_pitch
        ys = g.yt - (np.arange(g.rows) + 0.5) * g.y_pitch
        X, Y = np.meshgrid(xs, ys)
        lx, ly = X - g.piece_rect[0], Y - g.piece_rect[1]
        inside = ((lx >= 20) & (lx <= 40)) | ((ly >= 60) & (ly <= 80))
        self.assertFalse((burned & ~inside).any())          # a solid black picture burns only the cross
        self.assertTrue(burned[inside & (np.abs(lx - 30) < 9) & (np.abs(ly - 50) < 40)].all())

    def test_stock_perimeter_is_the_cross_and_labels_say_so(self):
        j = job()
        path = planner.outline_path(j.piece, j.geom.piece_rect[:2])
        self.assertEqual(len(path), len(CROSS) + 1)
        self.assertEqual(path[0], path[-1])
        self.assertEqual(path[0], (20 - 30.0, 0 - 50.0))       # centre origin: piece-local -> work mm
        self.assertIn("own outline", presets.piece_choice_label(j.piece))
        self.assertIn("traces that outline", presets.piece_explanation(j.piece))


if __name__ == "__main__":
    unittest.main()
