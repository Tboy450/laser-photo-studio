# Small-tin non-burning travel reassessment (2026-11-21)

**Status: DRAFT engineering review — no code changes to machine control, no saved preset changes and no physical tests.**

## Request
The operator reports that 6000 mm/min non-burning travel was too aggressive at small tin-lid scale. The upcoming experimental silver/soot test is 100% power, 450 mm/min burn feed, 0.15 mm raster pitch, one pass. Blank travel is distinct from burn feed and from row rewind. Copper presets are not in scope.

Recommendation to *test*, not a deployed value: **1800 mm/min for laser-off blank movement**, with 2–3 mm transition allowance and no acceleration on short gaps. Consider 2400 mm/min only after a smooth dry run. Do not silently change engrave feed or existing material presets.

## Confirmed code behavior on main
- lps/planner.py: ACCEL=500 mm/s² is assumed, MAX_FEED=6000 mm/min; raster_commands is serpentine. Blank S0 spans within a row stay at burn feed. Laser-off move to start of next row uses material.row_feed.
- lps/presets.py: default row_feed=600 mm/min, hop_feed=3000 mm/min, runup=4 mm. None is an adjustable within-row blank feed.
- lps/app.py: exposes burn feed and run-up, but not distinct Blank Travel Speed and Rewind Speed UI controls on main.
- lps/jobs.py: final return-to-origin uses F3000 S0; it is not per-row rewind.
- lps/verify.py: strict allowed feed whitelist. A new S0 speed requires verifier changes and no missed/doubled burn cells.
- Existing open PR #2 (https://github.com/Tboy450/laser-photo-studio/pull/2) reportedly implements row-return controls; open PR #7 (https://github.com/Tboy450/laser-photo-studio/pull/7) already documents the independent blank-travel request. Reconcile before implementing.

## Transition distance check (not physical measurements)
Assuming starting burn speed 450 mm/min = 7.5 mm/s and acceleration 500 mm/s², d = (v² − v0²) / (2a).

| Laser-off feed | Approx. acceleration distance from 450 |
|---|---:|
| 1800 mm/min | 0.84 mm |
| 2400 mm/min | 1.54 mm |
| 6000 mm/min | 9.94 mm |

Therefore 2–3 mm approach buffer is plausible for the 1800 candidate under code assumptions, not for 6000; check actual hardware $120/$121 and $110/$111 rather than trusting source constants. Distance does not guarantee effective braking.

## Proposed work (NOT implemented here)
1. Keep **Blank Travel Speed** and **Rewind Speed** separate and clearly labeled, only expose rewind when left-to-right mode is supported; preserve the other material defaults.
2. Enable faster **S0** moves for sufficiently long **within-row** gaps only; initial candidate threshold **8 mm**, reserve **2–3 mm** at each end and keep short blanks at burn feed. If actual available acceleration/braking distance is insufficient, slow down or stay at burn feed rather than force acceleration.
3. Retain M4/M5 and laser-off S0 transitions, zero, bounds, all intended engraving cells exactly once; do not generate G0/homing/unintended laser motion.
4. FakeGRBL/verifier cases: gaps 0.15, 2, 4, 6, 8 and 20 mm; left-to-right vs serpentine; ensure S>0 only at burn feed, no neighboring unintended burn, no new envelope excursions, preserved file compatibility.
5. Simulate, then do a physical **laser-off** trace with the operator before using scrap coated metal. Measure elapsed time, vibrations, registration and after-wipe finish. No production setting is validated yet.

## Private companion and handoff
- Full 58-line review and test plan is stored in restricted Drive: https://drive.google.com/file/d/11FzQ28_6OqDmr_1Ip47eIrZyw38KR72x/view
- Private session manager: https://github.com/Tboy450/session-handoff-hub/pull/12
- No client art or photos are committed in this public repo.
