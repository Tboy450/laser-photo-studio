"""End-to-end runs against the simulated controller (no hardware)."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from lps import jobs, machine, planner, presets, recovery, verify
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
    def test_attempt_controls_survive_burst_and_emergency_has_priority(self):
        _, folder = self.make()
        original = jobs.read_json(folder / 'run.json')
        with patch.object(jobs.subprocess, 'Popen'):
            jobs.launch_runner(folder, original)
        run = Runner(folder, wire=FakeWire(self.ctrl()))
        # Windows wall time may return the same value for every click in a burst.
        with patch.object(jobs.time, 'time_ns', return_value=1):
            for command in ('pause', 'continue', 'estop', 'resume'):
                jobs.send_control(folder, command)
        self.assertEqual(run.check_control(), 'estop')
        self.assertTrue(run.estop_req)
        self.assertEqual([jobs.take_control(run.control_queue) for _ in range(3)], ['pause', 'continue', 'resume'])
        jobs.send_control(folder, 'pause')
        with patch.object(jobs.subprocess, 'Popen'):
            jobs.launch_runner(folder, original)
        new = Runner(folder, wire=FakeWire(self.ctrl()))
        self.assertIsNone(new.check_control())

    def test_photo_wait_idle_does_not_spend_the_next_commands_ack_timeout(self):
        _, folder = self.make(pause_between=True)
        runner = Runner(folder)
        runner.g = machine.Grbl(SimpleNamespace(write=lambda _data: None))
        runner.state["phase"] = "waiting_photo"
        runner.g.last_ack_at = 10
        with patch("lps.runner.time.monotonic", return_value=40):
            runner.last_status_at = 40
            runner.watch()
            runner.state["phase"] = "running"
            runner.g.send("M5 S0")
            runner.watch()
        with patch("lps.runner.time.monotonic", return_value=56):
            runner.last_status_at = 56
            with self.assertRaisesRegex(machine.ControllerError, "No acknowledgement"):
                runner.watch()

    def test_resume_keeps_saved_position_in_stream_before_first_write(self):
        job, folder = self.make(start_index=8)
        resume = Runner(folder)
        resume._progress()
        self.assertEqual(resume.state["sent"], 8)
        self.assertEqual(resume.state["pass_total"], len(job.passes[0].commands))
        self.assertGreater(resume.state["progress"], 0.0)
        self.assertEqual(resume.state["completed"], [])

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

    def test_job_from_a_picked_start_point(self):
        job = small_job("anodized-dots", 24.0, 16.0, origin="spot", spot=[10.0, 6.0])
        rep = verify.verify_job(job)
        self.assertTrue(rep["ok"])
        folder = jobs.save_job(job, rep, folder=self.root / "job-spot")
        jobs.write_json(folder / "run.json", dict(start_pass=0, start_index=0, lead=[], expected_start=[0.0, 0.0],
                                                  pause_between=False, park=[0.0, 0.0]))
        c = self.ctrl()
        self.assertEqual(self.run_job(folder, FakeWire(c)), "complete")
        np.testing.assert_allclose(coverage(c, job.geom), expected_counts(job), atol=1e-6)
        self.assert_clean(c)
        self.assertAlmostEqual(c.phys[0], 0.0, places=3)   # parked back on the picked spot

    def test_picture_moves_with_the_head(self):
        c = self.ctrl()
        g = machine.Grbl(FakeWire(c))
        g.open(settle=0.0)
        machine.set_origin_here(g, 4.0, 3.0)                  # 'the dot is here': nothing moves
        self.assertEqual(c.phys[:2], [0.0, 0.0])
        st = machine.jog_keep_position(g, 2.5, -1.0, 3000)    # head moves, keeps its X/Y
        self.assertAlmostEqual(st.wpos[0], 4.0, places=2)
        self.assertAlmostEqual(st.wpos[1], 3.0, places=2)
        self.assertAlmostEqual(c.phys[0], 2.5, places=3)
        self.assertAlmostEqual(c.phys[1], -1.0, places=3)
        g.close()
        self.assert_clean(c)

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
    def test_held_position_near_end_finishes_stroke_in_both_directions(self):
        for start, end, held in ((0, 1, .981), (1, 0, .019)):
            body = ["M5 S0", f"G1 X{start:.3f} Y0.000 F600 S0", "M4 S0",
                    f"G1 X{end:.3f} Y0.000 F2500 S500", "M5 S0"]
            point = [held, 0.]
            self.assertEqual(recovery.locate(body, point), (3, body[3]))
            self.assertEqual(recovery.locate(body, [end, 0]), (4, None))
            lead = recovery.resume_spec(body, 0, 3, point, partial=body[3])["lead"]
            self.assertEqual(recovery.held_resume_lead(lead, point, [*point, 0]),
                             ["M5 S0", "M4 S0", body[3]])
            self.assertEqual(recovery.held_resume_lead(lead, point, [held + .001, 0]), lead)
            self.assertEqual(recovery.held_resume_lead(lead, point, None), lead)

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
