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

## Addendum: opt-in ADAPTIVE BLANK TRAVEL mode (operator request, 2026-11-21)

**Important change from fixed-speed recommendation:** Acceleration and deceleration speeds, peak allowed blank feed and offset distances must be **computed per gap from geometry and machine motion limits**, not fixed globally because a job or lid is small. A small lid can contain both tiny and long blank gaps. Keep the first iteration laser-OFF only.

### UI contract

- [ ] **Adaptive Blank Travel (Experimental)** — a clearly labeled **checkbox**, **OFF by default**. Show it near the two separate manual controls **Blank Travel Speed** and **Rewind Speed**. The operator wants a checkbox *for testing*.
- OFF: preserve current G-code and settings behavior exactly, including current serpentine raster and speeds. Do not silently engage adaptive movement or overwrite any proven material preset.
- ON: show **Maximum blank travel speed** (proposed initial cap **1800 mm/min**, user-editable, not a guaranteed result), **acceleration input/verified machine value**, and **effective feed + calculated offsets per gap** in preview/job report. The 1800 number is a trial ceiling, not a universal speed.
- The option should be saved in the job's metadata with an `experimental` flag and the exact motion parameters used for generating the verified G-code. Clear mark **experimental / dry run required** before enabling physical production. Do not silently treat it as a machine setting.
- A separately named **Rewind Speed** remains independently configurable, only when truly one-way / left-to-right scanning is implemented. Do not conflate the return traverse with within-row blank motion or generic row/hop speeds.

### Motion-plan requirements

1. Detect each contiguous **laser-off S0 span**, including blank spans between marks and optionally end-of-row return as a **separate** planning category. The length of this particular free span, not just total image size, determines whether speeding up is worthwhile.
2. Set entry and exit baseline to the actual engraving feed (v_b), calculate controller-limited peak (v_p) with `v_p <= user_max`, `v_p <= machine_feed_limit` and adequate distance to accelerate and decelerate at **verified** axis acceleration. Conservative symmetric approximation for a gap of length (L): (2d=(v_p^2-v_b^2)/a), so (v_p <= sqrt(v_b^2 + aL)), before reserving additional buffers/uncertainty. In a practical controller, corner speed, lookahead, minimum segment lengths, axis-dependent accel, and stopping accuracy make this only an upper bound: **allow more margin or fall back to baseline**.
3. Start with **2–3 mm operator-preferred transition/buffer zones** as a **preferred minimum**, but dynamically enlarge or shorten peak to respect calculated braking distance, and **never accelerate** if blank gap is too short. An **8 mm** minimum useful blank gap is a provisional performance filter, not a proof of safe 1800 speed or an exact size threshold.
4. For unequal constraints at either end, compute separate acceleration and deceleration distances/feeds (not a symmetrical simplification in implementation), fit them inside the open gap and enforce that the terminal approach to any powered mark is back at engraving speed **before S>0**. If controller dynamics cannot be guaranteed, the correct safe behavior is **no speed-up**.
5. Never speed up a powered move, never emit a laser-on high-speed transition, and preserve every intended raster burn cell exactly once, safe travel envelope, machine origin and M4/M5 sequencing. No G0, homing or firmware changes. Deceleration needs actual G-code/GRBL planner tests; naive adjacent `F` commands do not by themselves guarantee instantaneous speed changes at programmed boundaries.
6. Keep an auditable comparison **adaptive OFF vs ON** for the same art, including commanded feed groups, minimum gap accelerated, calculated approach/exit offsets, preview of traversals, estimated travel-time benefit and count of skipped short gaps.

### Required tests before release

- Deterministic unit tests for 0.15 / 1 / 2 / 3 / 4 / 6 / 8 / 20 / 40 mm gaps, changing image/lid sizes and burn feeds (including the **450 mm/min** planned tin test), plus different axis acceleration constraints.
- With checkbox OFF, command output should be **byte-identical** to a baseline job (apart from non-functional manifest metadata). ON must never modify raster pixel placement, S>0 burn feed/power, or G-code origin.
- Confirm no S>0 moves at adaptive blank feed, no duplicate/missing burns, no new envelope violations; verify mid-row empty gaps, leading/trailing gaps, short fragments and direction changes.
- Exercise fake GRBL and a human-supervised **laser-off dry trace** before actual runs. Report **measured motion**, noise and overshoot separately from model-predicted distances; any acceleration mismatch must disable adaptive output safely.
- Reconcile existing **PR #2** row-return controls and **PR #7** earlier blank travel request so one UI switch cannot secretly change other return speed behavior.

**Implementation status:** request documented and committed to this draft documentation PR only; **checkbox and adaptive algorithm are not implemented yet**.
