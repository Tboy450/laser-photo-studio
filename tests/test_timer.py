"""Print timer: per-pass ms timings (timing.json), a timestamped status trace, and the live on-screen clock."""
import csv
import unittest

from lps import jobs
from lps.app_laser import clock, timer_text
from lps.fakegrbl import FakeWire
from tests.test_dwell import lid_job
from tests.test_runner import RunnerBase


class TimerText(unittest.TestCase):
    def test_clock(self):
        self.assertEqual(clock(128.4367, ms=True), "2:08.437")
        self.assertEqual(clock(128.4367), "2:08.4")
        self.assertEqual(clock(3725.5), "1:02:05.5")

    def test_live_then_final(self):
        t = dict(job_t0=1000.0, job_end=None, pass_t0=1010.0, pass_end=None, pass_index=1)
        self.assertEqual(timer_text(t, 1070.25), "Print timer 1:10.2   pass 2: 1:00.2")
        t.update(job_end=1200.1234, pass_end=1138.4367,
                 last_pass=dict(title="x", real_s=128.437, est_s=480.0, ratio=0.2676))
        self.assertEqual(timer_text(t, 5000.0), "Print timer 3:20.123   pass 2: 2:08.437   "
                                                "last pass 128.437 s moving (planned 480.0 s, x0.268)")
        self.assertEqual(timer_text(None, 1.0), "")


class TimerRuns(RunnerBase):
    def run_saved(self, job, speedup):
        from lps import verify
        rep = verify.verify_job(job)
        folder = jobs.save_job(job, rep, folder=self.root / "timed")
        jobs.write_json(folder / "run.json", dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0],
                                                  pause_between=False, park=[0.0, 0.0]))
        c = self.ctrl()
        c.speedup = speedup
        self.assertEqual(self.run_job(folder, FakeWire(c)), "complete")
        return folder

    def test_timing_file_trace_and_log(self):
        job = lid_job()
        folder = self.run_saved(job, 60.0)
        tm = jobs.read_json(folder / "timing.json")["passes"]
        self.assertEqual([p["title"] for p in tm], [p.title for p in job.passes])
        for p in tm:
            self.assertEqual(p["ended"], "complete")
            start = p["first_motion_ms"] if p["first_motion_ms"] is not None else p["sent_ms"]   # sped-up fake
            self.assertLessEqual(p["sent_ms"], start)
            self.assertLess(start, p["idle_ms"])
            # real_s is rounded to milliseconds; include its half-unit rounding
            # boundary plus floating-point epsilon (places=3 can reject exactly .0005).
            self.assertAlmostEqual(p["real_s"], (p["idle_ms"] - start) / 1000, delta=.000500001)
            self.assertTrue(p["start_basis"])
        with open(folder / "status-trace.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertGreater(len(rows), 5)
        t = [float(r["t_ms"]) for r in rows]
        self.assertEqual(t, sorted(t))
        self.assertTrue({"state", "wx", "wy", "feed_mm_min", "laser_s", "ov"} <= set(rows[0]))
        log = (folder / "log.txt").read_text(encoding="utf-8")
        self.assertIn("[running] raster (1 of 2) running.", log)       # read_timing.py still works
        self.assertIn("[timing] raster:", log)
        st = jobs.read_json(folder / "state.json")
        self.assertTrue(st["timer"]["job_end"] >= st["timer"]["job_t0"])

    def test_real_time_matches_plan_at_real_speed(self):
        job = lid_job([dict(x=0.0, y=-10.0, seconds=1.5, power=80)], raster=False)
        folder = self.run_saved(job, 1.0)
        p = jobs.read_json(folder / "timing.json")["passes"][0]
        self.assertGreaterEqual(p["real_s"], 1.5)                         # the burn alone is 1.5 s
        self.assertLess(abs(p["real_over_planned"] - 1.0), 0.35)          # within status-poll resolution


if __name__ == "__main__":
    unittest.main()
