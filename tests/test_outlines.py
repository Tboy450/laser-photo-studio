import threading
import unittest
from collections import Counter

import numpy as np

from lps import machine, outlines, planner
from lps.fakegrbl import FakeController, FakeWire


class LiteralOutlines(unittest.TestCase):
    def assert_edges_match(self,mask):
        expected=Counter()
        h,w=mask.shape
        for r,c in zip(*np.nonzero(mask)):
            if r==0 or not mask[r-1,c]: expected[((c,r),(c+1,r))]+=1
            if c==w-1 or not mask[r,c+1]: expected[((c+1,r),(c+1,r+1))]+=1
            if r==h-1 or not mask[r+1,c]: expected[((c+1,r+1),(c,r+1))]+=1
            if c==0 or not mask[r,c-1]: expected[((c,r+1),(c,r))]+=1
        got=Counter()
        area=0
        for path in outlines.cell_contours(mask):
            self.assertEqual(path[0],path[-1])
            for (ax,ay),(bx,by) in zip(path,path[1:]):
                self.assertTrue(ax==bx or ay==by)
                length=abs(bx-ax)+abs(by-ay)
                dx,dy=(bx-ax)//length,(by-ay)//length
                for k in range(length):
                    got[((ax+k*dx,ay+k*dy),(ax+(k+1)*dx,ay+(k+1)*dy))]+=1
                area+=ax*by-bx*ay
        self.assertEqual(got,expected)
        self.assertEqual(area/2,int(mask.sum()))

    def test_boundaries_match_cells_including_holes_and_diagonal_contacts(self):
        rng=np.random.default_rng(7)
        for _ in range(60):
            self.assert_edges_match(rng.random((12,15))>.45)
        donut=np.ones((10,10),bool); donut[2:7,3:8]=False
        self.assert_edges_match(donut)
        self.assertEqual(len(outlines.cell_contours(np.eye(2,dtype=bool))),2)

    def test_white_padding_and_window_do_not_become_rectangle(self):
        mask=np.zeros((10,14),bool)
        mask[2:8,3:11]=True
        mask[4:6,6:8]=False
        mask[0,0]=True
        g=planner.Geometry(.1,14,10,0,1,None,(0,0,1.4,1),(0,0,1.4,1))
        paths=outlines.physical_contours(mask,g)
        self.assertEqual(len(paths),3)  # main shape, window hole, disconnected island
        vertices=[p for path in paths for p in path]
        self.assertNotIn((1.4,0),vertices)
        self.assertIn((.6,.6),vertices)
        sticker = outlines.sticker_paths(paths)
        self.assertEqual(len(sticker), 2)
        self.assertNotIn((.6, .6), [point for path in sticker for point in path])

    def test_round_image_check_clips_to_usable_face(self):
        path = outlines.image_boundary((-4, -5, 4, 5), (-6, -6, 6, 6), 10)
        self.assertEqual(path[0], path[-1])
        self.assertAlmostEqual(max(x for x, _ in path), 4)
        self.assertTrue(all(x * x + y * y <= 25.000001 for x, y in path))


class TraceController(unittest.TestCase):
    def test_burn_trace_powers_only_planned_strokes_at_two_percent(self):
        c = FakeController(speedup=10000)
        c.take_output()
        g = machine.Grbl(FakeWire(c))
        g.open(settle=0)
        moves = [(1, 2, 2500, False), (3, 2, 800, True), (3, 4, 2000, False), (1, 4, 900, True)]
        try:
            machine.trace_outline(g, [], feed=1500, illuminate=False, moves=iter(moves),
                                  move_count=len(moves), live_trace=True)
            self.assertEqual([tuple(burn[:5]) for burn in c.burns],
                             [(1, 2, 3, 2, 20), (3, 4, 1, 4, 20)])
            self.assertTrue(all(burn[6] == "M4" for burn in c.burns))
            self.assertFalse(c.pulses or c.forbidden)
            self.assertEqual(g.query_status().wpos[:2], (0, 0))
            machine.require_off(g)
        finally:
            g.close()

    def test_dry_run_forces_zero_power_and_keeps_move_order(self):
        class RecordingWire(FakeWire):
            def write(self, data):
                sent.append(data)
                super().write(data)

        sent = []
        c = FakeController(speedup=10000)
        c.take_output()
        g = machine.Grbl(RecordingWire(c))
        g.open(settle=0)
        statuses = []
        try:
            moves = [(1, 2, 2500, False), (3, 2, 800, True), (3, 4, 2000, False), (1, 4, 900, True)]
            machine.trace_outline(g, [], feed=1500, illuminate=False, moves=iter(moves),
                                  move_count=len(moves), status=statuses.append)
            xy = [s.decode().strip() for s in sent if s.startswith(b"G1 X")]
            self.assertEqual(xy[1:-1], [
                "G1 X1.000 Y2.000 F1500 S0", "G1 X3.000 Y2.000 F800 S0",
                "G1 X3.000 Y4.000 F1500 S0", "G1 X1.000 Y4.000 F900 S0",
            ])
            self.assertFalse(c.burns or c.pulses)
            self.assertFalse(any(s.startswith((b"M3", b"M4")) for s in sent))
            self.assertEqual(statuses[-1].wpos[:2], (0, 0))
        finally:
            g.close()

    def test_only_actual_edges_are_powered_at_one_percent(self):
        c=FakeController(speedup=10000)
        c.take_output()
        g=machine.Grbl(FakeWire(c)); g.open(settle=0)
        paths=[[(1,1),(3,1),(3,2),(1,2),(1,1)],[(5,4),(6,4),(6,5),(5,5),(5,4)]]
        try:
            machine.trace_outline(g,paths,feed=1000)
            expected=[(a[0],a[1],b[0],b[1]) for path in paths for a,b in zip(path,path[1:])]
            self.assertEqual([tuple(round(v,3) for v in burn[:4]) for burn in c.burns],expected)
            self.assertTrue(all(b[4]==10 and b[6]=='M4' for b in c.burns))
            self.assertEqual(c.phys,[0,0])
            self.assertEqual(c.modal['spindle'],'M5')
            self.assertFalse(c.overflow or c.forbidden or c.pulses)
        finally:
            g.close()

    def test_cancel_does_not_count_as_completed_check(self):
        for closing, expected in ((False, (0, 0)), (True, (-2, 4))):
            with self.subTest(closing=closing):
                c = FakeController(speedup=10000)
                c.take_output()
                g = machine.Grbl(FakeWire(c))
                g.open(settle=0)
                cancelled, shutdown = threading.Event(), threading.Event()

                def stop(_step, _total, _name, kind):
                    if kind == "tracing":
                        if closing:
                            shutdown.set()
                        cancelled.set()

                try:
                    with self.assertRaises(machine.ControllerError):
                        machine.trace_outline(g, [[(-3, 4), (-2, 4), (-2, 5)]],
                                              cancel=cancelled, shutdown=shutdown, progress=stop)
                    self.assertEqual(g.query_status().wpos[:2], expected)
                    self.assertEqual(c.modal["spindle"], "M5")
                    if closing:
                        self.assertFalse(any(cmd.startswith("G1X0.000Y0.000") for cmd in c.received))
                finally:
                    g.close()
