"""Offline USB position evidence and exact-setup restoration regressions."""
import copy
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from lps import jobs, machine, position_memory
from lps.fakegrbl import FakeController, FakeWire
from lps.worker import MachineWorker
from tests import test_placement_ui as placement_ui
from tests import test_runner as runner_tests


def status(x, y, state="Idle", wco=(12., 7., 0.), feed=0):
    return machine.parse_status(
        f"<{state}|WPos:{x},{y},0|WCO:{wco[0]},{wco[1]},{wco[2]}|FS:{feed},0>")


class PositionJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.settings_patch = patch.object(jobs, "SETTINGS_FILE", self.folder / "settings.json")
        self.settings_patch.start()
        self.no_hardware = patch.object(machine.SerialWire, "open", side_effect=AssertionError("No real serial"))
        self.no_hardware.start()
        self.path = position_memory.memory_path("COM4")
        self.mem = position_memory.PositionMemory(self.path)

    def tearDown(self):
        self.no_hardware.stop()
        self.settings_patch.stop()
        self.tmp.cleanup()

    def test_idle_inspection_jog_records_physical_endpoint_and_survives_reopen(self):
        c = FakeController(speedup=3000)
        c.take_output()
        worker = MachineWorker(queue.Queue(), demo=False, context={"picture_file": "lid.png", "dx": -1.5})
        worker.g = machine.Grbl(FakeWire(c), observer=worker.memory.protocol)
        worker.g.open(settle=0)
        worker._task("origin", machine.set_origin_here, (), {})
        worker._task("jog", machine.jog, (-88.9, 0., 3000), {})
        worker.memory.disconnect()
        saved = jobs.read_json(self.path)
        self.assertFalse(saved["in_flight"])
        self.assertAlmostEqual(saved["last_idle"]["wpos"][0], -88.9, places=3)
        self.assertAlmostEqual(c.phys[0], -88.9, places=3)
        self.assertEqual(saved["context"]["dx"], -1.5)
        fresh = position_memory.PositionMemory(self.path)
        fresh.protocol("status", status(0, 0))  # not aligned yet: must not erase prior evidence
        self.assertEqual(jobs.read_json(self.path), saved)
        self.assertFalse(fresh.enabled)
        self.assertEqual(c.burns, [])
        worker.g.close()

    def test_mid_move_endpoint_is_not_promoted_to_completed_position(self):
        self.mem.arm(status(0, 0), {"job_folder": "lid-job", "check_mode": "burn"})
        self.mem.begin("perimeter")
        # Durable before sending motion; a crash here still means motion may have started.
        self.assertTrue(jobs.read_json(self.path)["in_flight"])
        self.mem.protocol("attempt", "G1 X30.000 Y8.000 F500 S20")
        self.mem.protocol("sent", "G1 X30.000 Y8.000 F500 S20")
        self.mem.protocol("status", status(11.2, 8, "Run", feed=500))
        self.mem.settled(status(11.2, 8, "Run", feed=500))
        self.mem.protocol("attempt", "G1 X31.000 Y8.000 F500 S20")
        self.mem.protocol("sent", "M5 S0")  # cleanup must not erase the uncertain motion
        self.mem.disconnect()
        saved = jobs.read_json(self.path)
        self.assertTrue(saved["in_flight"])
        self.assertEqual(saved["last_idle"]["wpos"][:2], [0, 0])
        self.assertEqual(saved["last_reported"]["wpos"][:2], [11.2, 8])
        self.assertIn("X30.000", saved["last_sent_motion"])
        self.assertIn("X31.000", saved["attempted_motion"])
        self.assertEqual(saved["context"]["check_mode"], "burn")

    def test_reset_keeps_pre_reset_coordinates_and_clears_protocol_offset_cache(self):
        self.mem.arm(status(-20, -7), {"job_folder": "old-job"})
        self.mem.begin("perimeter")
        g = machine.Grbl(FakeWire(FakeController()), observer=self.mem.protocol)
        g._line("<Run|MPos:8,10,0|WCO:12,7,0|FS:500,20>")
        g._line("Grbl 1.1h ['$' for help]")
        self.assertIsNone(g.wco)
        self.assertIsNone(g.status)
        g._line("<Idle|MPos:0,0,0|FS:0,0>")
        self.assertIsNone(g.status.wpos)
        saved = jobs.read_json(self.path)
        self.assertTrue(saved["reset"])
        self.assertEqual(saved["last_reported"]["wpos"][:2], [-4, 3])
        self.assertFalse(self.mem.enabled)

    def test_rearming_archives_previous_interrupted_path(self):
        self.mem.arm(status(0, 0), {"job_folder": "first"})
        self.mem.begin("perimeter")
        self.mem.data["path_progress"] = {"sent_moves": 35, "total": 100, "phase": "tracing"}
        self.mem.disconnect()
        self.mem.arm(status(-10, 3), {"job_folder": "second"})
        histories = list((self.path.parent / "history").glob("*.json"))
        self.assertEqual(len(histories), 1)
        old = jobs.read_json(histories[0])
        self.assertEqual(old["context"]["job_folder"], "first")
        self.assertEqual(old["path_progress"]["sent_moves"], 35)

    def test_partial_serial_write_is_failure_not_success(self):
        wire = machine.SerialWire()
        wire.ser = Mock()
        wire.ser.write.return_value = 3
        with self.assertRaises(machine.LinkError):
            wire.write(b"G1 X9 Y9 S0\n")

    def test_reset_idle_position_restoration_never_jogs_or_burns(self):
        c = FakeController(speedup=3000)
        c.take_output()
        g = machine.Grbl(FakeWire(c))
        g.open(settle=0)
        machine.set_origin_here(g, 0, 0)
        machine.jog(g, -88.9, 0, 3000)
        old_physical = c.phys[:]
        c.reboot()
        g.close()
        restored = machine.Grbl(FakeWire(c))
        restored.open(settle=0)
        restored.reset_seen = False  # connection checks already recorded the banner
        observed = restored.query_status()
        start = len(c.received)
        worker = MachineWorker(queue.Queue(), demo=False)
        st = worker.restore_position(restored, (-88.9, 0), observed, {"job_folder": "lid"})
        self.assertAlmostEqual(st.wpos[0], -88.9, places=3)
        self.assertEqual(c.phys, old_physical)
        self.assertEqual(c.burns, [])
        commands = c.received[start:]
        self.assertFalse(any(x.startswith(("$J", "G1 X", "G0", "$H", "M3", "M4")) for x in commands))
        machine.jog_to_work(restored, 0, 0, 3000)
        self.assertAlmostEqual(c.phys[0], 0, places=3)
        self.assertAlmostEqual(c.phys[1], 0, places=3)
        self.assertFalse(c.burns)
        restored.close()

    def test_jog_before_restoring_reference_invalidates_old_idle_checkpoint(self):
        self.mem.arm(status(-88.9, 0), {"job_folder": "lid"})
        self.mem.disconnect()
        c = FakeController(speedup=3000)
        c.take_output()
        worker = MachineWorker(queue.Queue(), demo=False)
        worker.g = machine.Grbl(FakeWire(c), observer=worker.memory.protocol)
        worker.g.open(settle=0)
        worker._task("jog", machine.jog, (5, 0, 3000), {})
        saved = jobs.read_json(self.path)
        self.assertTrue(saved.get("coordinate_uncertain"))
        self.assertTrue(saved["in_flight"])
        self.assertEqual(saved["last_idle"]["wpos"][:2], [-88.9, 0])
        self.assertFalse(worker.memory.enabled)
        worker.g.close()

    def test_worker_closes_port_even_if_final_position_save_fails(self):
        events = queue.Queue()
        worker = MachineWorker(events, demo=True)
        worker.quit.set()  # connect to fake controller then immediately execute cleanup
        with patch.object(worker.memory, "disconnect", side_effect=OSError("disk full")):
            worker.run()
        self.assertFalse(worker.g.wire.opened)
        seen = []
        while not events.empty():
            seen.append(events.get()[0])
        self.assertIn("disconnected", seen)


class RunnerPersistence(runner_tests.RunnerBase):
    def test_finished_job_saves_zero_before_releasing_port(self):
        memory_path = self.root / "completed-position.json"
        context = {"job_name": "church", "piece": {"origin": "center"}, "dx": -.5, "dy": 1.0}
        _, folder = self.make("anodized-dots", position_memory_path=str(memory_path), setup_context=context)
        c = self.ctrl(report="MPos")
        c.phys, c.wco = [40., 60.], [40., 60.]
        wire = FakeWire(c)
        self.assertEqual(self.run_job(folder, wire), "complete")
        saved = jobs.read_json(memory_path)
        self.assertEqual(saved["context"], context)
        self.assertTrue(saved["disconnected"])
        self.assertFalse(saved["in_flight"])
        self.assertEqual(saved["last_idle"]["wpos"][:2], [0., 0.])
        self.assertEqual(saved["last_idle"]["mpos"][:2], [40., 60.])
        self.assertEqual(saved["last_idle"]["wco"][:2], [40., 60.])
        self.assertFalse(wire.opened)
        self.assertFalse(jobs.LOCK_FILE.exists())

    def test_second_runner_cannot_overwrite_active_sender_position_record(self):
        memory_path = self.root / "live-position.json"
        mem = position_memory.PositionMemory(memory_path)
        mem.arm(status(-9, 6), {"job_folder": "active-job"})
        mem.begin("engraving")
        expected = memory_path.read_bytes()
        _, folder = self.make(position_memory_path=str(memory_path))
        wire = FakeWire(self.ctrl())
        with patch.object(jobs, "active_runner", return_value={"pid": -12345, "job": "active-job"}):
            self.assertEqual(self.run_job(folder, wire), "fault")
        self.assertEqual(memory_path.read_bytes(), expected)
        self.assertFalse(wire.opened)
        self.assertFalse(wire.ctrl.received)

    def test_runner_closes_port_even_if_final_position_save_fails(self):
        _, folder = self.make("anodized-dots")
        wire = FakeWire(self.ctrl())
        runner = runner_tests.Runner(folder, wire=wire, settle=0)
        with patch.object(runner.memory, "disconnect", side_effect=OSError("disk full")):
            self.assertEqual(runner.run(), "complete")
        self.assertFalse(wire.opened)
        self.assertFalse(jobs.LOCK_FILE.exists())


class SetupRestoreUI(unittest.TestCase):
    setUp = placement_ui.PlacementUI.setUp
    pump = placement_ui.PlacementUI.pump

    def tearDown(self):
        if self.app.worker:
            self.app.disconnect(wait=True)
        placement_ui.PlacementUI.tearDown(self)

    def until(self, predicate):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            self.root.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail("Demo UI did not reach expected state")

    def test_restore_button_keeps_inspection_park_and_original_job_zero(self):
        a = self.app
        a.connect()
        self.until(lambda: a.connected and a.last_status is not None)
        with patch("lps.app_laser.messagebox.askyesno", return_value=True), \
                patch("lps.app_laser.messagebox.askokcancel", return_value=True), \
                patch("lps.app_laser.messagebox.showinfo") as info, \
                patch("lps.app_laser.messagebox.showerror") as error:
            a.set_origin()
            self.until(lambda: a.origin_set and not a.worker.busy and a.worker.tasks.empty())
            a.jog(-88.9, 0)
            self.until(lambda: a.last_status and a.last_status.wpos and abs(a.last_status.wpos[0] + 88.9) < .01
                       and a.last_status.state == "Idle" and not a.worker.busy)
            geom = a.job.geom
            a.disconnect(wait=True)
            self.assertFalse(a.origin_set)
            a.connect()
            self.until(lambda: a.connected and a.last_status is not None and not a.worker.busy)
            before = list(a.worker.ctrl.phys)
            a.restore_saved_setup()
            self.until(lambda: a.origin_set and not a.layout_pending and not a.worker.busy)
            self.assertEqual(a.worker.ctrl.phys, before)
            self.assertAlmostEqual(a.last_status.wpos[0], -88.9, places=3)
            self.assertEqual(a.job.geom, geom)
            self.assertFalse(a.completed_checks)
            self.assertEqual(a.worker.ctrl.burns, [])
            info.assert_not_called()
            error.assert_not_called()

    def test_inspection_buttons_park_once_and_reconnect_to_original_zero(self):
        a = self.app
        a.connect()
        self.until(lambda: a.connected and a.last_status is not None)
        with patch("lps.app_laser.messagebox.askyesno", return_value=True), \
                patch("lps.app_laser.messagebox.askokcancel", return_value=True), \
                patch("lps.app_laser.messagebox.showinfo") as info, \
                patch("lps.app_laser.messagebox.showerror") as error:
            a.set_origin()
            self.until(lambda: a.origin_set and not a.worker.busy and a.worker.tasks.empty())
            geom = a.job.geom
            offset = tuple(a.worker.ctrl.wco)
            a.follow_var.set(True)  # inspection must ignore the placement-shifting arrow option
            a.btn_inspect.invoke()
            self.until(lambda: not a.inspection_request and not a.worker.busy and a.worker.tasks.empty()
                       and abs(a.last_status.wpos[0] + 88.9) < .01 and a.last_status.idle_off)
            a.btn_inspect.invoke()
            self.until(lambda: not a.inspection_request and not a.worker.busy and a.worker.tasks.empty())
            self.assertAlmostEqual(a.worker.ctrl.phys[0], -88.9, places=3)
            self.assertEqual(tuple(a.worker.ctrl.wco), offset)
            self.assertEqual(a.job.geom, geom)
            a.disconnect(wait=True)  # app Disconnect must preserve the same memory as unplugging
            self.assertFalse(a.connected)
            self.assertTrue(a.saved_position()["disconnected"])
            a.btn_return.invoke()  # reconnect, restore, return in this one requested action
            self.until(lambda: a.connected and a.origin_set and not a.layout_pending and not a.inspection_request
                       and not a.worker.busy and a.worker.tasks.empty() and a.last_status.idle_off
                       and abs(a.last_status.wpos[0]) < .01)
            self.assertAlmostEqual(a.worker.ctrl.phys[0], 0, places=3)
            self.assertAlmostEqual(a.worker.ctrl.phys[1], 0, places=3)
            self.assertEqual(tuple(a.worker.ctrl.wco), offset)
            self.assertEqual(a.job.geom, geom)
            self.assertFalse(a.worker.ctrl.burns)
            info.assert_not_called()
            error.assert_not_called()

    def test_inspection_cancellation_and_active_job_cannot_trigger_movement(self):
        a = self.app
        a.connect()
        self.until(lambda: a.connected and a.last_status is not None)
        a.worker.memory.arm(a.last_status, a.setup_context())
        with patch("lps.app_laser.messagebox.askyesno", return_value=False), \
                patch.object(a.worker, "submit") as send:
            a.inspection_move((-88.9, 0))
            self.assertIsNone(a.inspection_request)
            send.assert_not_called()
        with patch.object(jobs, "active_runner", return_value={"job": "printing"}), \
                patch.object(a.worker, "submit") as send:
            a.inspection_move((-88.9, 0))
            self.assertIsNone(a.inspection_request)
            send.assert_not_called()
        self.assertFalse(a.worker.ctrl.burns)

    def test_changing_piece_origin_does_not_bind_new_layout_to_old_zero(self):
        a = self.app
        a.piece["origin"] = "center"
        a.sync_place_fields()
        a.changed(0)
        self.pump()
        a.connect()
        self.until(lambda: a.connected and a.last_status is not None)
        with patch("lps.app_laser.messagebox.askyesno", return_value=True), \
                patch("lps.app_laser.messagebox.askokcancel", return_value=True):
            a.set_origin()
            self.until(lambda: a.origin_set and not a.worker.busy and a.worker.tasks.empty())
        before = a.saved_position()
        self.assertEqual(before["context"]["piece"]["origin"], "center")
        a.piece["origin"] = "lower-left"
        a.sync_place_fields()
        a.changed(0)
        self.pump()
        self.until(lambda: not a.worker.busy and a.worker.tasks.empty())
        self.assertFalse(a.origin_set)
        self.assertEqual(a.saved_position()["context"]["piece"]["origin"], "center")

    def test_resume_older_job_preserves_its_saved_context_not_current_picture(self):
        a = self.app
        folder = self.folder / "older-job"
        folder.mkdir()
        original = dict(a.setup_context(), job_folder=str(folder), dx=-2.5, dy=1.75)
        jobs.write_json(folder / "run.json", {"setup_context": original})
        a.dx, a.dy = 9, -7
        with patch.object(jobs, "active_runner", return_value=None), \
                patch.object(jobs, "launch_runner", return_value=123) as launch:
            a.launch(folder, {"start_pass": 0, "start_index": 17, "expected_start": [-2, 1]})
        saved = launch.call_args.args[1]["setup_context"]
        self.assertEqual(saved, jobs.read_json(folder / "run.json")["setup_context"])
        self.assertEqual(saved["dx"], -2.5)

    def test_restore_exact_layout_settings_and_masks_without_motion(self):
        a = self.app
        a.mat = a.mat.copy(power=570, feed=1700, scan_direction="forward")
        a.piece.update(w=45.72, h=45.72, origin="center", shape="circle",
                       margins=(0, 0, 0, 0), keepouts=[dict(kind="rect", x=5, y=6, w=3, h=4)])
        a.rotate, a.mirror = 1, True
        a.dx, a.dy = -.5, 1.25
        a.v_gamma.set(1.25)
        a.v_neg.set(True)
        a.fit_var.set("exact")
        a.sync_place_fields()
        ctx = copy.deepcopy(a.setup_context())
        a.mat = a.mat.copy(power=1000, feed=2500)
        a.piece.update(w=12, h=19, origin="lower-left", keepouts=[])
        a.dx, a.dy = 10, 20
        a.v_gamma.set(.6)
        a.v_neg.set(False)
        with patch.object(machine, "jog") as jog, patch.object(machine, "set_origin_here") as declare:
            a.load_setup_context(ctx)
            self.pump()
            jog.assert_not_called()
            declare.assert_not_called()
        got = a.setup_context()
        for key in ("picture_file", "rotate", "mirror", "material", "piece", "fit", "art_w", "dx", "dy", "look", "grid"):
            self.assertEqual(got[key], ctx[key], key)
        self.assertEqual(a.job.geom.art_w, 45.72)
        self.assertEqual(a.origin_var.get(), "center")
        self.assertFalse(a.completed_checks)

    def test_reset_during_trace_cannot_restore_old_idle_as_current_position(self):
        a = self.app
        a.connect()
        self.until(lambda: a.connected and a.last_status is not None)
        mem = a.worker.memory
        mem.arm(a.last_status, a.setup_context())
        mem.begin("perimeter")
        mem.protocol("status", status(-12, 8, "Run", wco=(0, 0, 0), feed=600))
        mem.protocol("reset", "Grbl 1.1h")
        a.connection_rebooted = True
        before = list(a.worker.ctrl.phys)
        with patch("lps.app_laser.messagebox.showinfo") as info, \
                patch("lps.app_laser.messagebox.askyesno") as confirm, \
                patch.object(a.worker, "submit") as send:
            a.restore_saved_setup()
        info.assert_called_once()
        confirm.assert_not_called()
        send.assert_not_called()
        self.assertEqual(a.worker.ctrl.phys, before)
        self.assertFalse(a.origin_set)
        self.assertTrue(jobs.read_json(mem.path)["in_flight"])

    def test_saved_layer_thresholds_restore_and_changed_source_is_rejected(self):
        a = self.app
        a.mat = a.mat.copy(style="layers", tone_cuts=(220, 150, 65))
        for var, val in zip(a.v_cut, a.mat.tone_cuts):
            var.set(val)
        ctx = copy.deepcopy(a.setup_context())
        for var, val in zip(a.v_cut, (200, 100, 25)):
            var.set(val)
        a.load_setup_context(ctx)
        self.pump()
        self.assertEqual(a.build_params()[0].tone_cuts, (220, 150, 65))
        self.picture.write_bytes(b"changed original")
        with self.assertRaisesRegex(ValueError, "source picture has changed"):
            a.load_setup_context(ctx)


if __name__ == "__main__":
    unittest.main()
