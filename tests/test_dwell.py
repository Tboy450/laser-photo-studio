"""Burn-in-place ("dwell") passes: the laser on, standing still, only at chosen spots."""
import threading
import time
import unittest

import numpy as np

from lps import jobs, ladder, planner, presets, recovery, verify
from lps.fakegrbl import FakeController, FakeWire, coverage
from lps.runner import Runner
from tests.test_runner import RunnerBase

SPOTS = [dict(x=-5.25, y=-14.8, seconds=5, power=80), dict(x=1.75, y=-14.8, seconds=20, power=80),
         dict(x=5.25, y=-18.0, seconds=40, power=100)]


def lid_job(spots=SPOTS, cool=0.0, raster=True):
    base = next(m for m in presets.BUILTIN if m.key == "anodized-dots")
    mat = ladder.lid_material(base, "Reflective tin lid").copy(scan_direction="forward", row_feed=3000)
    piece = ladder.lid_piece()
    p = mat.pitch
    n = int(round(2 * (25.4 - piece["margins"][0]) / p))
    geom = planner.layout((n, n), planner.Placement(piece, art_w=n * p, fit="whole"), p)
    geom.cols, geom.rows = n, n
    allowed = planner.allowed_cells(geom, piece)
    passes = []
    if raster:
        cells = np.zeros((n, n), np.int16)
        cells[n // 2 - 5:n // 2 + 5, n // 2 - 5:n // 2 + 5] = 800
        passes.append(planner.PassPlan("R", "raster", "", "rows", cells, list(range(n)), 2200))
    passes.append(planner.dwell_pass(geom, allowed, spots, cool_s=cool))
    job = planner.JobPlan("dwell-test", mat, geom, piece, passes, None, None, allowed)
    return planner.compile_job(job)


def problems(job, cmds):
    return verify.verify_pass(job, job.passes[-1], cmds)["problems"]


class DwellPlan(unittest.TestCase):
    def test_commands_verify_and_estimate(self):
        job = lid_job(cool=3.0)
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"], rep)
        d = job.passes[-1]
        self.assertEqual(d.commands[:5], ["M5 S0", f"G1 X{d.spots[0]['x']:.3f} Y{d.spots[0]['y']:.3f} F3000 S0",
                                          "M3 S800", "G4 P5", "M5 S0"])
        self.assertEqual(d.commands[5], "G4 P3")                      # cool-down between spots, laser off
        self.assertEqual(d.commands[-1], "M5 S0")
        self.assertNotIn("G4 P3", d.commands[-3:])                     # no cool-down after the last spot
        self.assertGreaterEqual(d.est_s, 5 + 20 + 40 + 2 * 3)
        bx0, by0, bx1, by1 = job.burn_bbox()
        self.assertLessEqual(by0, -18.0)                               # the perimeter check covers the spots
        self.assertIn("burn-in-place", verify.summary_text(rep))
        moves = list(verify.trace_moves(job))                          # previews skip M3/G4 without error
        self.assertEqual(len(moves), 1 + sum(sum(1 for c in p.commands if c.startswith("G1 ")) for p in job.passes))
        for sp, want in zip(d.spots, SPOTS):                          # snapped to a dot centre, at most half a dot
            self.assertLessEqual(abs(sp["x"] - want["x"]), 0.0501)
            self.assertLessEqual(abs(sp["y"] - want["y"]), 0.0501)

    def test_spots_outside_or_too_long_are_refused(self):
        with self.assertRaises(ValueError):
            lid_job([dict(x=24.0, y=0.0, seconds=5, power=80)])        # off the lid's usable circle
        with self.assertRaises(ValueError):
            lid_job([dict(x=0.0, y=-10.0, seconds=61, power=80)])      # over the 60 s limit
        with self.assertRaises(ValueError):
            lid_job([dict(x=0.0, y=-10.0, seconds=5, power=120)])

    def test_verifier_rejects_unsafe_dwell_commands(self):
        job = lid_job(cool=2.0)
        c = list(job.passes[-1].commands)
        k = c.index("M3 S800")
        self.assertTrue(problems(job, c[:k + 1] + c[k + 2:]))           # M3 without its G4
        self.assertTrue(problems(job, c[:k + 2] + c[k + 3:]))           # no M5 after the burn: next move laser on
        self.assertTrue(problems(job, c[:k + 1] + ["G4 P61"] + c[k + 2:]))   # too long / not the planned time
        self.assertTrue(problems(job, c[:k] + ["M3 S900"] + c[k + 1:]))      # not the planned power
        moved = c[:k - 1] + [c[k - 1].replace(" S0", " S800")] + c[k:]
        self.assertTrue(problems(job, moved))                           # a move with the laser on
        self.assertTrue(problems(job, c[:k] + ["G4 P1"] + c[k:]))            # a wait not after M5 S0
        self.assertTrue(problems(job, c[:k + 3]))                       # spots missing
        self.assertTrue(problems(job, c + c[1:]))                       # spots burned twice
        self.assertTrue(problems(job, c[:-1]))                          # doesn't end laser off
        j = c.index("G4 P2")                                               # the cool-down after spot 1
        self.assertEqual(c[j + 1:j + 3][0], "M5 S0")
        self.assertTrue(problems(job, c[:j + 1] + c[j + 2:]))           # a move not straight after M5 S0
        self.assertTrue(problems(job, c[:k] + ["M5 S0"] + c[k:]))       # M3 not straight after its travel move
        for x, cmd in enumerate(c):                                     # every move: laser off just before it
            if cmd.startswith("G1 "):
                self.assertEqual(c[x - 1], "M5 S0")
                self.assertTrue(cmd.endswith(" S0"))
        raster = job.passes[0]
        bad = list(raster.commands)
        bad.insert(1, "M3 S800")
        self.assertTrue(verify.verify_pass(job, raster, bad)["problems"])   # raster passes still refuse M3

    def test_spots_are_never_stacked_in_one_place(self):
        with self.assertRaises(ValueError):                             # 0.5 mm apart: not its own burn
            lid_job([dict(x=0.0, y=-10.0, seconds=5, power=80), dict(x=0.5, y=-10.0, seconds=5, power=80)])
        job = lid_job([dict(x=0.0, y=-10.0, seconds=5, power=80), dict(x=3.0, y=-10.0, seconds=5, power=80)],
                      raster=False)
        d = job.passes[0]
        near = dict(d.spots[1], x=round(d.spots[0]["x"] + 0.3, 3))      # hand-edited plan: second spot 0.3 mm away
        cells = np.zeros_like(d.cells)
        for sp in (d.spots[0], near):
            cells[int(np.floor((job.geom.yt - sp["y"]) / job.geom.y_pitch)),
                  int(np.floor((sp["x"] - job.geom.x0) / job.geom.x_pitch))] = sp["s"]
        stacked = planner.PassPlan("D", "d", "", "dwell", cells, None, 3000, spots=[d.spots[0], near])
        job.passes = [stacked]
        planner.compile_job(job)
        self.assertTrue(any("closer than" in m for m in verify.verify_pass(job, stacked)["problems"]))

    def test_resume_never_repeats_a_spot(self):
        body = lid_job(raster=False).passes[0].commands
        k3 = body.index("M3 S800")
        idx, skipped = recovery.dwell_resume(body, k3, k3)              # stopped mid-spot 1
        self.assertEqual(body[idx - 1], "M5 S0")
        self.assertEqual(skipped, 1)
        self.assertEqual(body[idx], "M5 S0")                            # next: laser off, then travel to spot 2
        self.assertTrue(body[idx + 1].startswith("G1 "))
        self.assertEqual(recovery.dwell_resume(body, idx, idx - 1), (idx, None))   # between spots: unchanged


class DwellRuns(RunnerBase):
    def save(self, job, **spec):
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"], rep)
        folder = jobs.save_job(job, rep, folder=self.root / f"dwell-{time.monotonic_ns()}")
        run = dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0], pause_between=False,
                   park=[0.0, 0.0])
        run.update(spec)
        jobs.write_json(folder / "run.json", run)
        self.assertEqual(jobs.read_json(folder / "job.json")["passes"][-1]["kind"], "dwell")
        return folder

    def _resume(self, folder, c):
        st = jobs.read_json(folder / "state.json")
        spec = dict(st["resume"])
        spec.update(pause_between=False, park=[0.0, 0.0], completed=st["completed"])
        jobs.write_json(folder / "run.json", spec)
        return self.run_job(folder, FakeWire(c))

    def spots_burned(self, c):
        return [(round(x, 3), round(y, 3), s, round(t, 3)) for x, y, s, t in c.pulses]

    def test_runs_raster_then_spots(self):
        job = lid_job()
        folder = self.save(job)
        c = self.ctrl()
        self.assertEqual(self.run_job(folder, FakeWire(c)), "complete")
        np.testing.assert_allclose(coverage(c, job.geom), (job.passes[0].cells > 0).astype(float), atol=1e-6)
        want = [(sp["x"], sp["y"], sp["s"], float(sp["seconds"])) for sp in job.passes[-1].spots]
        self.assertEqual(self.spots_burned(c), want)
        self.assertTrue(all(b[6] == "M4" for b in c.burns))            # every moving burn is still M4
        self.assertEqual(c.modal["spindle"], "M5")

    def test_long_burn_is_not_a_stalled_controller(self):
        old = Runner.ACK_TIMEOUT
        Runner.ACK_TIMEOUT = 0.3
        try:
            job = lid_job([dict(x=0.0, y=-10.0, seconds=1.5, power=80), dict(x=2.0, y=-10.0, seconds=1.5, power=80)],
                          raster=False)
            folder = self.save(job)
            c = self.ctrl()
            c.speedup = 1.0
            self.assertEqual(self.run_job(folder, FakeWire(c)), "complete")
            self.assertEqual(len(c.pulses), 2)
        finally:
            Runner.ACK_TIMEOUT = old

    def _interrupt(self, request):
        spots = [dict(x=-4.0 + 2.0 * k, y=-10.0, seconds=1.0, power=80) for k in range(4)]
        job = lid_job(spots, raster=False)
        folder = self.save(job)
        c = self.ctrl()
        c.speedup = 1.0
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            if c.cur is not None and c.cur["kind"] == "dwell" and c.cur["t"] > 0.2 and len(c.pulses) == 1:
                jobs.send_control(folder, request)                     # mid-burn on spot 2
                break
            time.sleep(0.01)
        t.join(30)
        self.assertEqual(out.get("r"), "stopped")
        first = list(c.pulses)
        c.speedup = 3000.0
        self.assertEqual(self._resume(folder, c), "complete")
        return job, first, c.pulses[len(first):]

    def test_estop_mid_spot_skips_it_and_never_repeats(self):
        job, before, after = self._interrupt("estop")
        sp = job.passes[0].spots
        self.assertEqual(len(before), 2)
        self.assertLess(before[1][3], 1.0)                              # spot 2 cut short at once
        self.assertEqual([(round(x, 3), round(y, 3)) for x, y, *_ in after], [(s["x"], s["y"]) for s in sp[2:]])

    def test_pause_finishes_the_spot_then_stops(self):
        job, before, after = self._interrupt("pause")
        sp = job.passes[0].spots
        self.assertEqual(len(before), 2)
        self.assertAlmostEqual(before[1][3], 1.0, places=3)             # spot 2 burned in full, not held half-done
        positions = [(round(x, 3), round(y, 3)) for x, y, *_ in before + after]
        self.assertEqual(positions, [(s["x"], s["y"]) for s in sp])     # every spot exactly once


if __name__ == "__main__":
    unittest.main()
