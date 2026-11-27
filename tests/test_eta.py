"""No hardware: planned-time countdown, pause accounting and saved-job resume budgets."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lps import eta, jobs, planner, verify
from lps.runner import Runner
from tests.test_dwell import lid_job


class StableETA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        job = lid_job()
        jobs.save_job(job, verify.verify_job(job), folder=self.folder)
        jobs.write_json(self.folder/'run.json', dict(start_pass=0, start_index=0, completed=[]))
        self.runner = Runner(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def test_components_match_planner_and_keep_return_separate(self):
        body=['M5 S0','G1 X-5 Y0 F6000 S0','M4 S0','G1 X0 Y0 F3500 S0',
              'G1 X30 Y0 F3500 S500','M5 S0','G1 X-5 Y1 F6000 S0','M3 S500','G4 P2.5','M5 S0']
        parts=eta.components(body)
        self.assertAlmostEqual(sum(parts.values()),planner.estimate_seconds(body))
        self.assertGreater(parts['laser_off_s'],0)
        self.assertGreater(parts['engraving_s'],0)
        self.assertEqual(parts['dwell_s'],2.5)
        self.assertAlmostEqual(sum(eta.components(body, 6).values()),
                               sum(parts.values())-sum(eta.components(body[:6]).values()))

    def test_no_hours_jump_on_stop_or_different_command_densities(self):
        r=self.runner
        r.job['passes']=[dict(est_s=7200.)]
        r.eta_components=dict(engraving_s=3200.,laser_off_s=3900.,dwell_s=0.,overhead_s=100.)
        r.pi=0;r.active_s=3600.
        r.state.update(completed=[],phase='running',sent=50,pass_total=100)
        # Old algorithm lost partial progress on leaving running/paused: 3600 -> 7200 seconds.
        r._progress();self.assertEqual(r.state['remaining_s'],3600)
        for phase,sent in [('stopping',50),('paused',10),('running',99),('dropout',99)]:
            r.state.update(phase=phase,sent=sent);r._progress()
            self.assertEqual(r.state['remaining_s'],3600)
        r.active_s=7300;r.state['phase']='running';r._progress()
        self.assertTrue(r.state['eta']['exceeded'])
        r.state['phase']='complete';r._progress()
        self.assertFalse(r.state['eta']['exceeded'])
        self.assertEqual(r.state['remaining_s'],0)

    def test_pauses_and_photo_wait_do_not_consume_countdown(self):
        r=self.runner
        r.t0_mono=100.;r.active_mark=100.;r.accounted_at=100.
        r.state['phase']='running'
        for now,paused,phase,active in [(110,False,'running',True),(120,True,'paused',True),
                                        (130,True,'waiting_photo',False),(140,False,'running',True)]:
            r.paused=paused;r.state['phase']=phase
            if not active:r.active_mark=None
            elif r.active_mark is None:r.active_mark=now-10
            with patch('lps.runner.time.monotonic',return_value=now):r.save(force=True)
        self.assertEqual(r.active_s,20.)
        self.assertEqual(r.paused_s,20.)
        self.assertEqual(r.state['wall_elapsed_s'],40.)

    def test_saved_resume_budget_excludes_previous_passes_and_skipped_commands(self):
        r=self.runner;bodies=r.load_passes()
        full=sum(r.eta_components.values())
        r.spec.update(start_pass=1,start_index=3)
        r.state['completed']=[0]
        r.load_passes()
        expected=sum(eta.components(bodies[1],3).values())
        self.assertAlmostEqual(sum(r.eta_components.values()),expected)
        self.assertLess(expected,full)
