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
        self.assertEqual(moves[1][1], 2685)                           # PR 7's figure for a 2 mm zone (~2690)
        self.assertEqual(planner.blank_gap_moves(0, 30, 140, 6000)[1][1], 6000)
        self.assertEqual(planner.blank_gap_moves(30, 0, 140, 6000)[0][0], 28.0)   # right-to-left mirrors it

    def test_settings_change_the_zones(self):
        self.assertEqual(planner.blank_gap_moves(0, 10, 140, 6000, guard=4, min_fast=2)[0][0], 4)
        self.assertEqual(planner.blank_gap_moves(0, 10, 140, 6000, guard=2, min_fast=7), [(10, 140)])
        m = presets.BUILTIN[0]
        self.assertEqual((m.fast_blank_gaps, m.blank_feed, m.blank_guard_mm, m.blank_min_fast_mm), (False, 6000, 2.0, 2.0))
        with self.assertRaises(ValueError):
            m.copy(blank_feed=7000)
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
        m = job.material.copy(blank_feed=6000)
        cmds4 = ['G1 X0.000 Y1.000 F140 S800', 'G1 X2.000 Y1.000 F140 S0', 'G1 X6.000 Y1.000 F6000 S0',
                 'G1 X8.000 Y1.000 F140 S0']
        self.assertIn("can't be reached and braked", verify._fast_gap_problem(m, cmds4, 2, 2.0, 6.0, 140, 6000))
        self.assertIsNone(verify._fast_gap_problem(m, cmds4, 2, 2.0, 6.0, 140, 2686))
        job.material = job.material.copy(fast_blank_gaps=False)  # fast moves without the setting: refused
        self.assertFalse(verify.verify_pass(job, job.passes[0], good)['ok'])


class SeparateBlankSpeed(BlankGaps):
    def test_blank_speed_is_its_own_setting_not_the_rewind(self):
        _, a, _ = self.build(True, travel=3000)
        job = a
        m = job.material.copy(row_feed=3000, blank_feed=6000)
        job.material = m
        planner.compile_job(job)
        cmds = job.passes[0].commands
        mids = {int(c.split()[3][1:]) for c in cmds if c.startswith('G1') and c.endswith(' S0')
                and int(c.split()[3][1:]) > 140}
        self.assertGreater(max(mids), 3000)                         # gaps run past the rewind speed (braking-capped)...
        rewinds = [c for i, c in enumerate(cmds) if i + 1 < len(cmds) and cmds[i + 1] == 'M4 S0']
        self.assertTrue(all(' F3000 ' in c for c in rewinds))       # ...while row rewinds keep their own 3000
        self.assertTrue(verify.verify_job(job)['ok'])
        job.material = m.copy(blank_feed=4000)                    # a lower blank limit must refuse F6000 moves
        self.assertFalse(verify.verify_pass(job, job.passes[0], cmds)['ok'])



class PlannerPassesItsOwnCheck(unittest.TestCase):
    """Tristan's 2026-11-20 report: Check job failed with 'fast blank gap F3157 can't be reached and braked within
    2.598 mm'. Whatever the planner emits for a gap, its own verifier must accept; a short gap simply doesn't speed up."""

    def check(self, x0, x1, burn, fast, guard=2.0, min_fast=2.0):
        m = presets.BUILTIN[0].copy(fast_blank_gaps=True, blank_feed=fast, blank_guard_mm=guard, blank_min_fast_mm=min_fast)
        moves = planner.blank_gap_moves(x0, x1, burn, fast, guard, min_fast)
        cmds = [f"G1 X{planner.fmt(x0)} Y1.000 F{burn} S350"]
        cmds += [f"G1 X{planner.fmt(x)} Y1.000 F{f} S0" for x, f in moves]
        cmds.append(f"G1 X{planner.fmt(x1 + 0.15)} Y1.000 F{burn} S350")
        xs = [float(c.split()[1][1:]) for c in cmds]
        for k in range(1, len(cmds) - 1):
            f = int(cmds[k].split()[3][1:])
            if f > burn:
                self.assertIsNone(verify._fast_gap_problem(m, cmds, k, xs[k - 1], xs[k], burn, f), (x0, x1, burn, cmds))
        return moves

    def test_reported_cases(self):
        for mid in (2.148, 2.598, 2.298):
            for burn in (2250, 2400, 140, 3000):
                self.check(4.424, 4.424 + mid + 4.0, burn, 6000)

    def test_fuzz_gap_lengths_feeds_and_positions(self):
        rng = np.random.default_rng(20261120)
        for _ in range(3000):
            x0 = float(rng.uniform(-90, 90))
            length = float(rng.uniform(0.1, 40))
            burn = int(rng.choice([140, 1200, 2250, 3500, 4500]))
            fast = int(rng.choice([3000, 4500, 6000]))
            moves = self.check(x0, x0 + length, burn, fast, float(rng.choice([0.5, 1, 2, 3])), float(rng.choice([0, 2, 5])))
            if length < 4.0 + 2.0 and len(moves) == 1:
                self.assertEqual(moves, [(x0 + length, burn)])          # short gaps stay at the engraving feed

    def test_dotted_job_with_fast_gaps_passes_check(self):
        from PIL import Image
        rng = np.random.default_rng(7)
        im = Image.fromarray((rng.random((300, 260)) * 255).astype('uint8'))
        for feed in (2250, 140):
            mat = presets.BUILTIN[0].copy(style='floyd', pitch=0.15, feed=feed, scan_direction='forward', row_feed=6000,
                                          fast_blank_gaps=True, blank_feed=6000, interlace=1, passes=1, thin_pass=False)
            piece = dict(name='t', shape='rect', w=40.0, h=46.0, origin='center', margins=(0, 0, 0, 0), corner=0.0, keepouts=[])
            job = planner.compile_job(planner.build_job(im, mat, planner.Placement(piece, fit='exact')))
            self.assertTrue(verify.verify_job(job)['ok'], verify.verify_job(job)['passes'][0]['problems'][:3])


if __name__ == '__main__':
    unittest.main()
