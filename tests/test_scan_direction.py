"""Offline direction comparison: same marks/power/size, different scan order only."""
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from lps import jobs, planner, presets, verify
from lps.fakegrbl import FakeController, FakeWire, coverage
from lps.runner import Runner
from tests.test_core import sample_picture, piece


def marked_directions(commands):
    x = y = 0.0
    directions = []
    for command in commands:
        if not command.startswith("G1 "):
            continue
        words = dict((w[0], float(w[1:])) for w in command.split()[1:])
        if words["S"] > 0:
            if words["Y"] != y:
                raise AssertionError("Powered return move")
            directions.append(np.sign(words["X"] - x))
        x, y = words["X"], words["Y"]
    return set(directions)


class ScanDirection(unittest.TestCase):
    def build(self, style, direction):
        mat = presets.BUILTIN[0].copy(style=style, scan_direction=direction)
        return planner.compile_job(planner.build_job(sample_picture(), mat,
            planner.Placement(piece(24, 18)), name="direction-offline-test"))

    def test_old_material_defaults_and_setting_round_trip(self):
        old = asdict(presets.BUILTIN[0])
        old.pop("scan_direction")
        self.assertEqual(presets.Material.from_dict(old).scan_direction, "alternating")
        forward = presets.Material.from_dict(old).copy(scan_direction="forward")
        self.assertEqual(presets.Material.from_dict(asdict(forward)), forward)
        with self.assertRaises(ValueError):
            forward.copy(scan_direction="unknown")

    def test_all_styles_preserve_cells_and_only_mark_forward(self):
        for style in presets.STYLES:
            with self.subTest(style=style):
                baseline = self.build(style, "alternating")
                forward = self.build(style, "forward")
                self.assertEqual(baseline.geom, forward.geom)
                self.assertEqual(len(baseline.passes), len(forward.passes))
                report = verify.verify_job(forward)
                self.assertTrue(report["ok"], report)
                for a, b in zip(baseline.passes, forward.passes):
                    np.testing.assert_array_equal(a.cells, b.cells)
                    self.assertEqual(a.feed, b.feed)
                    self.assertTrue(marked_directions(b.commands) <= {1})
                    self.assertEqual(b.commands[0], "M5 S0")
                    self.assertEqual(b.commands[-1], "M5 S0")
                self.assertIn(-1, set.union(*(marked_directions(p.commands) for p in baseline.passes)))

    def test_feature_rasters_use_forward_option(self):
        cells = np.array([[0, 300, 0, 0], [300, 300, 300, 0],
                          [0, 300, 0, 0], [0, 300, 0, 0]], dtype=np.int16)
        labels = np.where(cells, 1, 0)
        geom = planner.Geometry(.1, 4, 4, 0, .4, None, (0, 0, .4, .4), (0, 0, .4, .4))
        both = planner.feature_commands(cells, labels, geom, 300, 600, 1)
        one = planner.feature_commands(cells, labels, geom, 300, 600, 1, bidirectional=False)
        self.assertEqual(marked_directions(both), {-1, 1})
        self.assertEqual(marked_directions(one), {1})

    def test_saved_forward_job_runs_once_on_fake_controller(self):
        job = self.build("floyd", "forward")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(jobs, "LOCK_FILE", root / "sender.lock"), \
                    patch("lps.machine.SerialWire.open", side_effect=AssertionError("No real controller")):
                folder = jobs.save_job(job, verify.verify_job(job), folder=root / "job")
                saved = jobs.read_json(folder / "job.json")
                self.assertEqual(saved["material"]["scan_direction"], "forward")
                self.assertIn("left to right only", (folder / saved["passes"][0]["file"]).read_text())
                jobs.write_json(folder / "run.json", dict(start_pass=0, start_index=0, lead=[],
                    expected_start=[0., 0.], pause_between=False, park=[0., 0.]))
                controller = FakeController(speedup=3000)
                controller.take_output()
                self.assertEqual(Runner(folder, wire=FakeWire(controller), settle=0).run(), "complete")
                np.testing.assert_allclose(coverage(controller, job.geom), job.passes[0].cells > 0, atol=1e-6)
                self.assertFalse(controller.overflow)
                self.assertEqual(controller.forbidden, [])
                self.assertEqual(controller.modal["spindle"], "M5")
                np.testing.assert_allclose(controller.phys[:2], [0, 0], atol=.001)
