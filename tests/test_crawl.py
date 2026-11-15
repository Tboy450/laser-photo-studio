"""Crawl passes: lines at an average speed below the controller's floor (tiny steps, each followed by a pause)."""
import threading
import time
import unittest

import numpy as np

from lps import jobs, ladder, planner, presets, recovery, verify
from lps.fakegrbl import FakeWire
from tests.test_runner import RunnerBase

LINES = [dict(x0=-10.0, x1=-8.0, y=-5.0, power=100, v_avg=12, step=0.05),
         dict(x0=-10.0, x1=-8.0, y=-5.1, power=100, v_avg=12, step=0.1),
         dict(x0=-10.0, x1=-9.0, y=-7.0, power=100, v_avg=6, step=0.05)]


def crawl_job(lines=LINES, raster=True):
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
        cells[n // 2:n // 2 + 3, n // 2:n // 2 + 20] = 1000
        passes.append(planner.PassPlan("R", "raster", "", "rows", cells, list(range(n)), 24))
    passes.append(planner.crawl_pass(geom, allowed, lines))
    return planner.compile_job(planner.JobPlan("crawl-test", mat, geom, piece, passes, None, None, allowed))


def problems(job, cmds):
    return verify.verify_pass(job, job.passes[-1], cmds)["problems"]


class CrawlPlan(unittest.TestCase):
    def test_timing(self):
        self.assertEqual(planner.crawl_timing(0.05, 12)[:2], (30, 0.15))
        self.assertEqual(planner.crawl_timing(0.1, 12)[:2], (30, 0.3))
        self.assertEqual(planner.crawl_timing(0.05, 6)[:2], (30, 0.4))
        self.assertEqual(planner.crawl_timing(0.02, 12, min_feed=24)[:2], (24, 0.05))
        with self.assertRaises(ValueError):           # 50 ms pause steps can't do it with moves at 30 or more
            planner.crawl_timing(0.02, 12)

    def test_commands_and_verify(self):
        job = crawl_job()
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"], rep)
        c = job.passes[-1].commands
        ln = job.passes[-1].lines[0]                                      # snapped to the dot grid
        self.assertLessEqual(abs(ln["x0"] + 10.0), 0.0501)
        self.assertLessEqual(abs(ln["y"] + 5.0), 0.0501)
        x0, y = f"{ln['x0']:.3f}", f"{ln['y']:.3f}"
        self.assertEqual(c[:5], ["M5 S0", f"G1 X{x0} Y{y} F3000 S0", "M3 S1000",
                                 f"G1 X{ln['x0'] + 0.05:.3f} Y{y} F30 S1000", "G4 P0.15"])
        self.assertEqual(c[-1], "M5 S0")
        self.assertAlmostEqual(job.passes[-1].est_s, 2 / 12 * 60 * 2 + 1 / 6 * 60, delta=8)
        self.assertIn("crawl line", verify.summary_text(rep))

    def test_verifier_rejects(self):
        job = crawl_job(raster=False)
        c = list(job.passes[-1].commands)
        k = c.index("M3 S1000")
        self.assertTrue(problems(job, c[:k + 1] + c[k + 3:]))                      # a step skipped
        self.assertTrue(problems(job, c[:k + 2] + c[k + 3:]))                      # a step without its pause
        self.assertTrue(problems(job, c[:k + 2] + ["G4 P0.3"] + c[k + 3:]))        # wrong pause
        self.assertTrue(problems(job, c[:k + 2] + ["G4 P0.15", "G4 P0.15"] + c[k + 3:]))   # extra pause
        back = c[:k + 3] + [c[k + 1]] + c[k + 3:]                                   # a step back to the left
        self.assertTrue(problems(job, back))
        self.assertTrue(problems(job, c[:k] + [c[k], c[k - 1]] + c[k + 1:]))       # travel with the laser on
        y0 = c[k + 1].split()[2]
        off = [x.replace(y0, "Y-6.000") if i == k + 1 else x for i, x in enumerate(c)]
        self.assertTrue(problems(job, off))                                         # off the line
        m5 = c.index("M5 S0", k)
        self.assertTrue(problems(job, c[:m5 - 2] + c[m5:]))                        # line not finished
        self.assertTrue(problems(job, c[:-1]))                                      # ends laser on
        raster = crawl_job().passes[0]
        bad = list(raster.commands)
        bad.insert(1, "M3 S1000")
        self.assertTrue(verify.verify_pass(crawl_job(), raster, bad)["problems"])  # raster still refuses M3

    def test_resume_points(self):
        body = crawl_job(raster=False).passes[0].commands
        k = body.index("M3 S1000")
        self.assertEqual(recovery.pass_kind(body), "crawl")
        self.assertEqual(recovery.crawl_resume(body, k + 4), k + 5)                 # after step 2's pause
        self.assertEqual(recovery.crawl_resume(body, k + 3), k + 3)                 # step 2 in progress: redo it
        lead = recovery.lead_in(body, k + 5, (-9.9, -5.0))
        self.assertEqual(lead, ["M5 S0", "G1 X-9.900 Y-5.000 F3000 S0", "M3 S1000"])   # re-armed after the move
        m5 = body.index("M5 S0", k)
        self.assertEqual(recovery.lead_in(body, m5 + 1, (0, 0))[-1], "G1 X0.000 Y0.000 F3000 S0")


class CrawlRuns(RunnerBase):
    def save(self, job):
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"], rep)
        folder = jobs.save_job(job, rep, folder=self.root / f"crawl-{time.monotonic_ns()}")
        jobs.write_json(folder / "run.json", dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0],
                                                  pause_between=False, park=[0.0, 0.0]))
        return folder

    def _resume(self, folder, c):
        st = jobs.read_json(folder / "state.json")
        spec = dict(st["resume"])
        spec.update(pause_between=False, park=[0.0, 0.0], completed=st["completed"])
        jobs.write_json(folder / "run.json", spec)
        return self.run_job(folder, FakeWire(c))

    def burned(self, c, s=1000):
        return sorted((round(a, 3), round(b, 3), round(y, 3)) for a, y, b, _, sp, _, mode, _ in c.burns
                      if mode == "M3" and sp == s)

    def test_complete_and_pause_finishes_the_line(self):
        job = crawl_job(raster=False)
        want = [(round(ln["x0"] + k * ln["step"], 3), round(ln["x0"] + (k + 1) * ln["step"], 3), ln["y"])
                for ln in job.passes[0].lines for k in range(ln["steps"])]
        folder = self.save(job)
        c = self.ctrl()
        c.speedup = 40.0
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            if len(c.burns) > 3:
                jobs.send_control(folder, "pause")                    # mid line 1
                break
            time.sleep(0.01)
        t.join(60)
        self.assertEqual(out.get("r"), "stopped")
        first = self.burned(c)
        self.assertEqual(first, sorted(want[:job.passes[0].lines[0]["steps"]]))   # line 1 finished, then stopped
        c.speedup = 3000.0
        self.assertEqual(self._resume(folder, c), "complete")
        self.assertEqual(self.burned(c), sorted(want))                 # every step exactly once
        self.assertEqual(len(c.pulses), len(want))                    # one pause, laser on, per step
        self.assertEqual(c.modal["spindle"], "M5")

    def test_estop_turns_off_at_once(self):
        job = crawl_job(raster=False)
        folder = self.save(job)
        c = self.ctrl()
        c.speedup = 20.0
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        deadline = time.time() + 20
        while time.time() < deadline:
            if len(c.burns) > 3:
                jobs.send_control(folder, "estop")
                break
            time.sleep(0.01)
        t.join(30)
        self.assertIn(out.get("r"), ("stopped", "fault"))
        self.assertEqual(c.modal["spindle"], "M5")
        n = len(c.burns)
        self.assertLess(n, 15)                                        # stopped within a few steps, not the line
        st = jobs.read_json(folder / "state.json")
        self.assertEqual(st["resume"]["lead"][-1], "M3 S1000")         # resume re-arms after the laser-off move


if __name__ == "__main__":
    unittest.main()
