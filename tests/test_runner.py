"""End-to-end runs against the simulated controller (no hardware)."""
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

from lps import jobs, machine, planner, presets, verify
from lps.fakegrbl import FakeController, FakeWire, coverage
from lps.runner import Runner
from tests.test_core import small_job

SPEED = 3000.0


def expected_counts(job):
    exp = np.zeros((job.geom.rows, job.geom.cols))
    for p in job.passes:
        exp += p.cells > 0
    return exp


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self._lock = jobs.LOCK_FILE
        jobs.LOCK_FILE = self.root / "sender.lock"

    def tearDown(self):
        jobs.LOCK_FILE = self._lock
        self.td.cleanup()

    def make(self, key="pine-layers", **spec):
        job = small_job(key, 24.0, 16.0)
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"])
        folder = jobs.save_job(job, rep, folder=self.root / f"job-{key}-{time.monotonic_ns()}")
        run = dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0], pause_between=False,
                   park=[0.0, 0.0])
        run.update(spec)
        jobs.write_json(folder / "run.json", run)
        return job, folder

    def ctrl(self, **kw):
        c = FakeController(speedup=SPEED, **kw)
        c.take_output()  # power-on banner happened long before we connect
        return c

    def run_job(self, folder, wire):
        return Runner(folder, wire=wire, settle=0.0).run()

    def assert_clean(self, c):
        self.assertFalse(c.overflow, "RX buffer overflowed")
        self.assertEqual(c.forbidden, [])
        self.assertFalse(any(l.startswith(("$H", "G0", "G28", "G92")) for l in c.received))
        self.assertTrue(all(b[6] == "M4" for b in c.burns))


class FullRuns(RunnerBase):
    def test_complete_job_burns_every_cell_exactly_once(self):
        job, folder = self.make()
        c = self.ctrl()
        self.assertEqual(self.run_job(folder, FakeWire(c)), "complete")
        st = jobs.read_json(folder / "state.json")
        self.assertEqual(st["phase"], "complete")
        cov = coverage(c, job.geom)
        np.testing.assert_allclose(cov, expected_counts(job), atol=1e-6)
        self.assert_clean(c)
        self.assertAlmostEqual(c.phys[0], 0.0, places=3)   # parked at the origin
        self.assertEqual(c.modal["spindle"], "M5")

    def test_photo_pause_between_layers(self):
        job, folder = self.make(pause_between=True)
        c = self.ctrl()
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        waits = 0
        deadline = time.time() + 60
        while t.is_alive() and time.time() < deadline:
            st = jobs.read_json(folder / "state.json", {}) or {}
            if st.get("phase") == "waiting_photo" and st.get("photo_wait_since"):
                self.assertFalse(st["laser_on"])
                jobs.send_control(folder, "continue")
                waits += 1
                time.sleep(0.4)
            time.sleep(0.05)
        t.join(5)
        self.assertEqual(result.get("r"), "complete")
        self.assertEqual(waits, len(job.passes) - 1)
        np.testing.assert_allclose(coverage(c, job.geom), expected_counts(job), atol=1e-6)

    def test_refuses_when_head_not_at_origin(self):
        job, folder = self.make()
        c = self.ctrl()
        c.phys = [5.0, 5.0]
        self.assertEqual(self.run_job(folder, FakeWire(c)), "fault")
        self.assertIn("Nothing was sent", jobs.read_json(folder / "state.json")["message"])
        self.assertEqual(c.burns, [])

    def test_refuses_changed_settings(self):
        job, folder = self.make()
        c = self.ctrl(settings={30: 255})
        self.assertEqual(self.run_job(folder, FakeWire(c)), "fault")
        self.assertEqual(c.burns, [])

    def test_refuses_controller_that_rebooted_on_connect(self):
        job, folder = self.make()
        c = FakeController(speedup=SPEED)   # banner still pending = it just restarted
        self.assertEqual(self.run_job(folder, FakeWire(c)), "fault")
        self.assertEqual(c.burns, [])

    def test_refuses_edited_pass_file(self):
        job, folder = self.make()
        f = folder / jobs.read_json(folder / "job.json")["passes"][0]["file"]
        f.write_text(f.read_text().replace("S250", "S900"))
        c = self.ctrl()
        self.assertEqual(self.run_job(folder, FakeWire(c)), "fault")
        self.assertEqual(c.received, [])


class Recovery(RunnerBase):
    def _resume(self, folder, c, wire_state=None):
        st = jobs.read_json(folder / "state.json")
        spec = dict(st["resume"])
        spec.update(pause_between=False, park=[0.0, 0.0], completed=st["completed"])
        jobs.write_json(folder / "run.json", spec)
        return self.run_job(folder, FakeWire(c))

    def test_usb_dropout_reboot_and_resume(self):
        job, folder = self.make()
        c = self.ctrl()
        bed_from_work = (c.morg[0] + c.wco[0], c.morg[1] + c.wco[1])
        total = sum(len(p.commands) for p in job.passes)
        self.assertEqual(self.run_job(folder, FakeWire(c, fail_after_lines=int(total * 0.45))), "dropout")
        st = jobs.read_json(folder / "state.json")
        self.assertEqual(st["phase"], "dropout")
        stop = st["resume"]["expected_start"]
        c.run_until_idle()        # the controller finishes what it had received...
        c.reboot()                # ...then the replug reboots it: position now reads 0 wherever the head is
        # Recovery as the app does it: never home; declare the recorded stop point; resume after it.
        g = machine.Grbl(FakeWire(c))
        g.open(settle=0.0)
        machine.set_origin_here(g, stop[0], stop[1])
        g.close()
        self.assertEqual(self._resume(folder, c), "complete")
        np.testing.assert_allclose(coverage(c, job.geom, bed_from_work), expected_counts(job), atol=1e-6)
        self.assert_clean(c)

    def test_emergency_stop_mid_row_resumes_exactly(self):
        job, folder = self.make("anodized-dots")
        c = self.ctrl()
        c.speedup = 15.0
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        deadline = time.time() + 30
        while time.time() < deadline:
            st = jobs.read_json(folder / "state.json", {}) or {}
            if st.get("phase") == "running" and st.get("sent", 0) > len(job.passes[0].commands) * 0.1:
                jobs.send_control(folder, "estop")
                break
            time.sleep(0.01)
        t.join(60)
        self.assertEqual(out.get("r"), "stopped")
        st = jobs.read_json(folder / "state.json")
        self.assertTrue(st["resume"]["kept_position"])
        c.speedup = SPEED
        self.assertEqual(self._resume(folder, c), "complete")
        np.testing.assert_allclose(coverage(c, job.geom), expected_counts(job), atol=1e-6)

    def test_clean_stop_after_row_and_resume(self):
        job, folder = self.make()
        c = self.ctrl()
        c.speedup = 15.0
        out = {}
        t = threading.Thread(target=lambda: out.setdefault("r", self.run_job(folder, FakeWire(c))))
        t.start()
        deadline = time.time() + 30
        while time.time() < deadline:
            st = jobs.read_json(folder / "state.json", {}) or {}
            if st.get("phase") == "running" and st.get("sent", 0) > len(job.passes[0].commands) * 0.1:
                jobs.send_control(folder, "stop")
                break
            time.sleep(0.01)
        t.join(60)
        self.assertEqual(out.get("r"), "stopped")
        c.speedup = SPEED
        self.assertEqual(self._resume(folder, c), "complete")
        np.testing.assert_allclose(coverage(c, job.geom), expected_counts(job), atol=1e-6)


class Pointer(unittest.TestCase):
    def test_perimeter_check_only_uses_1_percent_bursts(self):
        c = FakeController(speedup=SPEED)
        c.take_output()
        g = machine.Grbl(FakeWire(c))
        g.open(settle=0.0)
        pts = planner.perimeter_points((2.0, 3.0, 30.0, 20.0))
        seen = []
        machine.perimeter_check(g, pts, pulses=2, progress=lambda i, n, name, what: seen.append((name, what)))
        self.assertEqual(len(c.pulses), 8)
        self.assertTrue(all(p[2] == 10 for p in c.pulses))
        corners = {(round(p[0], 3), round(p[1], 3)) for p in c.pulses}
        self.assertEqual(corners, {(2.0, 3.0), (30.0, 3.0), (30.0, 20.0), (2.0, 20.0)})
        self.assertEqual(c.burns, [])
        self.assertAlmostEqual(c.phys[0], 0.0, places=3)
        self.assertEqual(c.modal["spindle"], "M5")
        self.assertEqual(c.modal["S"], 0)
        # Each burst went out as ONE write that already contains its own OFF command.
        self.assertTrue(any(l == "M3S10" for l in c.received))

    def test_never_sends_homing_or_settings(self):
        c = FakeController(speedup=SPEED)
        g = machine.Grbl(FakeWire(c))
        for bad in ("$H", "$32=0", "G28", "G30 X0", "$RST=*"):
            with self.assertRaises(machine.ControllerError):
                g.send(bad)
        self.assertEqual(c.received, [])


if __name__ == "__main__":
    unittest.main()
