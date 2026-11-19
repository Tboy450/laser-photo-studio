"""Fast blank gaps keep a slow zone each side and only speed up a long enough middle (user request + PR 7 spec)."""
import unittest

import numpy as np

from lps import planner, presets, verify
from tests.test_blank_gaps import BlankGaps


class GapMoves(unittest.TestCase):
    def test_short_gaps_stay_at_engraving_speed(self):
        for length in (1, 3, 5, 5.9):
            self.assertEqual(planner.blank_gap_moves(0, length, 140, 6000), [(length, 140)])

    def test_slow_zone_each_side_and_braking_cap(self):
        moves = planner.blank_gap_moves(0, 8, 140, 6000)
        self.assertEqual([m[0] for m in moves], [2.0, 6.0, 8])
        self.assertEqual((moves[0][1], moves[2][1]), (140, 140))     # 2 mm at engraving speed both sides
        vb, v = 140 / 60, moves[1][1] / 60
        self.assertLessEqual(v * v, vb * vb + planner.ACCEL * 4 + 1e-9)   # reachable and brakeable in 4 mm
        self.assertEqual(moves[1][1], 2686)                           # PR 7's figure for a 2 mm zone (~2690)
        self.assertEqual(planner.blank_gap_moves(0, 30, 140, 6000)[1][1], 6000)
        self.assertEqual(planner.blank_gap_moves(30, 0, 140, 6000)[0][0], 28.0)   # right-to-left mirrors it

    def test_settings_change_the_zones(self):
        self.assertEqual(planner.blank_gap_moves(0, 10, 140, 6000, guard=4, min_fast=2)[0][0], 4)
        self.assertEqual(planner.blank_gap_moves(0, 10, 140, 6000, guard=2, min_fast=7), [(10, 140)])
        m = presets.BUILTIN[0]
        self.assertEqual((m.fast_blank_gaps, m.blank_guard_mm, m.blank_min_fast_mm), (False, 2.0, 2.0))
        with self.assertRaises(ValueError):
            m.copy(blank_guard_mm=-1)


class GapJobs(BlankGaps):
    def test_compiled_job_has_slow_zone_before_every_mark(self):
        _, job, _ = self.build(True)
        self.assertTrue(verify.verify_job(job)['ok'])
        cmds = job.passes[0].commands
        for i, c in enumerate(cmds):
            if ' F3000 ' in c and c.endswith(' S0') and cmds[i - 1] != 'M5 S0' and cmds[i + 1] != 'M4 S0':
                after = cmds[i + 1]
                self.assertTrue(after.endswith(' S0') and ' F140 ' in after, after)
                self.assertGreaterEqual(abs(float(after.split()[1][1:]) - float(c.split()[1][1:])), 2 - 1e-3)

    def test_verifier_rejects_unguarded_or_too_fast_gaps(self):
        _, job, _ = self.build(True)
        cmds = job.passes[0].commands
        k = next(i for i, c in enumerate(cmds) if c.endswith(' S0') and ' F3000 ' in c and cmds[i + 1].endswith(' S0')
                 and ' F140 ' in cmds[i + 1] and cmds[i - 1] != 'M5 S0')
        good = list(cmds)
        no_zone = good[:k] + [good[k + 1].replace(' F140 ', ' F3000 ')] + good[k + 2:]   # fast right up to the mark
        self.assertFalse(verify.verify_pass(job, job.passes[0], no_zone)['ok'])
        m = job.material.copy(row_feed=6000)
        cmds4 = ['G1 X0.000 Y1.000 F140 S800', 'G1 X2.000 Y1.000 F140 S0', 'G1 X6.000 Y1.000 F6000 S0',
                 'G1 X8.000 Y1.000 F140 S0']
        self.assertIn("can't be reached and braked", verify._fast_gap_problem(m, cmds4, 2, 2.0, 6.0, 140, 6000))
        self.assertIsNone(verify._fast_gap_problem(m, cmds4, 2, 2.0, 6.0, 140, 2686))
        job.material = job.material.copy(fast_blank_gaps=False)  # fast moves without the setting: refused
        self.assertFalse(verify.verify_pass(job, job.passes[0], good)['ok'])


if __name__ == '__main__':
    unittest.main()
