# Red Hill / Laser Photo Studio — overnight test log and scan-speed follow-up

**Test window:** November 17–18, 2026 (America/New_York).  
**Status:** User observations and development handoff, not a certified material recipe or machine-tested software release.  
**Equipment:** Tronxy Ultrabot U20 / 20 W diode laser, Laser Photo Studio, with LaserGRBL-compatible G-code workflow.  
**Associated work:** Red Hill Pine Salve Products matte-black round tin lids, Red Hill slate/coaster samples, six-tin carton jig, and a separate Chevrolet J8 wood artwork trial.

## Read this first: evidence and confidence

Use four explicit status labels throughout:
- **User-reported successful / promising:** the user personally observed a good result or described an in-progress run as looking good. This is not equivalent to independent measurement or software verification.
- **Observed unresolved:** directly noticed misbehavior or image/trace artifact; root cause not confirmed.
- **Proposed / pending:** a setting, mechanical design, or software optimization not yet tested on the machine.
- **Historical / may conflict:** earlier records that should not overwrite newer observations without a controlled comparison.

In particular, do not turn the stated preference for **0.15 mm raster spacing** into a machine-specific *minimum attainable resolution* or a universal material law. There are previous functional jobs at 0.10 mm. Preserve both profiles for comparative tests.

## 1. Confirmed user observations and recently selected settings

| Work / specimen | Settings / detail | Reported result | Classification |
|---|---|---|---|
| Red Hill slate image engraving | **4,500 mm/min**, **50% power**, **0.15 mm** raster pitch, one pass in the current discussion | User: “4500 at .15 is perfect”; 50% power separately reconfirmed | **User-reported successful** current slate run; do not overwrite historical 0.10 mm profiles |
| Other slate/coaster samples earlier in the overnight session | Three wiped-down samples were compared, with flash and no-flash photos | Later sample retained improved detail but unwanted fog/static/image-area marking remained on at least one test | **Observed unresolved**, not proof that all slate jobs share the problem |
| Matte-black round Red Hill tin lid | **0.15 mm** pitch; manually set; user described **“140 at 100”** while running. **Left-to-right-only** scanning | User said left-to-right **140 seems good** and that setup has saved substantial time; finished, fully inspected result is not yet firmly recorded | **Promising / in-progress.** Do not silently assume that 140 is feed or 100 is a power percentage without checking the actual job metadata |
| Tin row return / “rewind” | **6,000 mm/min** laser-off row return reported as good | Useful for non-printing return strokes | **User-reported useful**, distinct from proposed *within-row* blank travel |
| Wood artwork — classic Chevy stock car with “J8” | Requested artwork size **9.75 x 6.25 in = 247.65 x 158.75 mm**; most recently selected **4,500 mm/min**, **45% power**, **0.15 mm** pitch, **Stucki dithering**, one pass | No completed wood engraving result documented. User rejected grayscale-power mode due to concern over charring and long dwell in dark regions | **Proposed wood test only**, not a wood preset |
| Historical wood/photo baseline in published repository | Pine layered photo: **25/30/35%**, **2,250 mm/min**, **0.10 mm**, three layers; outlined pine 40% at 3,000 | Historical source-code preset and sample evidence, separate from tonight’s J8 trial | **Historical source baseline**, do not replace |

**Cross-material spacing preference:** The user now prefers **0.15 mm** for image quality and faster run time across the materials being tested, based on recent experience; retain **0.10 mm** as an available deliberate high-density option and use controlled side-by-side tests. On a 2D raster, changing from 0.10 to 0.15 reduces scan-row count by roughly one third for the same image height, before considering travel and acceleration, but does not guarantee better contrast on every substrate.

### Slate appearance and treatment notes

- Earlier slate/coaster imagery showed a faint unwanted **fog/static** or burn in parts of the image area that should have been cleaner. Do not diagnose this as “just missing detail.” Possible causes include preprocessing, thresholding/dither/polarity, wrong image field, power mapping, or motion/calibration; none has been established as the root cause.
- Slate was inspected dry after wiping and some samples were photographed wet or treated with a little vegetable oil. Oil changes the appearance and is **not** evidence that the engraving-path defect was repaired.
- Keep original input, processed/laser-input bitmap, and actual G-code burn-map preview for comparison before another full coaster. Preserve successful examples as baselines while investigating imperfect ones.
- Recent current-run report of 4,500/50%/0.15 must be recorded alongside, **not conflated with**, prior slate evidence around 3,500/50%/0.10.

## 2. Red Hill round tin imaging and placement notes

- Artwork and revisions included circular **RED HILL / PINE SALVE PRODUCTS** bubble lettering and forest/mountain imagery. Fine-detail revision must preserve the lid shape and lettering; do not unintentionally create a full square or rectangle filled burn.
- Existing tin geometry proposal: outer can/lid diameter **50.8 mm (2 in)** and approximately **45.72 mm usable circular face**; prepared artwork around **45.7 x 45.7 mm**. These are geometry/placement assumptions from the project's draft tin preset, not fresh machine measurements of every lid.
- **Observed unresolved:** **Total Parameter / total-travel trace** can draw a square image bounding area around a round lid, while **Image Trace** more accurately follows the image. The square may be a travel envelope rather than a burn command; do not infer a square burn without inspecting G-code + laser-on trace.
- A separate slate setup showed the **top border clipped in Total Travel Parameter**. Investigate travel extent, run-up/out, image origin, margins, trace selection, and clipping independently rather than declaring it a confirmed burn truncation.
- Maintain separate **total movement envelope**, **image/laser-on footprint**, **full burn trace**, and **1%/2% check** semantics. Both trace paths and XY bounds need explicit validation, especially on the round-lid jig.
- The user reported manual placement/setup streamlining and hoped for better output; **time saving and final quality have not yet been measured** in a controlled repeat.

## 3. Six-tin carton jig: pending measurement and positioning work

- The six-position arrangement is in a symmetric carton. Rather than individually resetting zero for each tin, the user wants a single jig origin and six independently nudgeable image locations, with correct Total Parameter and Image Trace positions for the entire group.
- Approximate, **not final**, center-to-center observations: horizontal spacing was around **2 inches, perhaps 1–2 mm less**; vertical row spacing was around **2 inches, perhaps 2–3 mm less**. The numbers should be validated physically before deriving exact XY centers or releasing a six-lid toolpath.
- Use a clear jig diagram, one origin, per-tin image offsets, per-tin circular safe-face masking, and a union of actual travel extents. Ensure moving one image does not silently shift all others or force a new zero.
- Draft tin-preset PR **#1** and general Studio update PR **#2** are not merged at the time of this handoff. Do not treat the jig or newer return-speed feature as deployed.

## 4. Requested software change: fast travel *within* left-to-right rows

### User’s exact motivation

When engraving **left to right only**, Studio can already return to the next row at a higher **laser-off return (“rewind”) speed** (user selected 6,000). However, a **long unmarked stretch in the same left-to-right row** still traverses at the slow engraving feed, even though **S0** / laser off. This wastes time when detailed art has distinct islands or gaps.

**Desired UI:** In **Step 2 > Material & print style > Adjust settings > Scan direction: Left to right only**, put a **Blank Travel Speed (mm/min)** option **beside Laser-off return speed**. Suggested value: **6,000 mm/min**; separate from engraving speed and separate from rewind speed. A dedicated **Transition / offset (mm)** preference should expose the user's requested **2 mm** nominal acceleration/deceleration margin, while protecting the actual marking path dynamically.

**Target effect:** Laser OFF during blank runs, accelerate through sufficiently long gaps, decelerate to exactly the configured burn feed **before** the next mark. Do not change dot coordinates, number of passes, image polarity, line pitch, mark power, dot placement, start point, or per-material engraving feed.

### Crucial acceleration caveat — 2 mm is not universally enough

The **current code** uses planning acceleration **500 mm/s²** (`lps/planner.py: ACCEL`) and a max feed of **6,000 mm/min**. These are source-code planning assumptions and must be verified against the machine/controller if used to guarantee print-edge speed.

For deceleration from 6,000 mm/min (100 mm/s) down to 140 mm/min (~2.33 mm/s), the ideal kinematic distance is:

`d = (v_fast² - v_burn²) / (2 * a) ≈ (10000 - 5.44) / 1000 ≈ 9.99 mm` at 500 mm/s².

A fixed **2 mm** braking zone at that acceleration would permit a much lower peak blank speed, about **2,690 mm/min**, before re-entering the 140-mm/min mark. Controller look-ahead, modal feed, dynamic M4 power, and segment chaining may further affect real behavior. A 2 mm visual preference cannot override the physics.

**Required behavior:** Use the 2 mm user preference as a *minimum extra laser-off guard* when possible; **calculate acceleration/braking distances**, with appropriate margin, from verified controller limits. Only use the full configured blank speed if there is enough distance to accelerate and, crucially, slow to the marking feed before the next laser-on pixel. Otherwise **reduce peak travel speed for that gap or keep the entire gap at marking feed**. Never create mark-entry overspeed.

### Proposed algorithm (not implemented by this PR)

1. Build the existing pixel-power segments for each forward raster row; identify continuous **S0** spans between nonzero burn segments. Do not reclassify tiny dither holes as useful travel opportunities.
2. Only consider gaps large enough for the guard, speed transitions, and a meaningful estimated time saving. Auto-skip gaps that would cause excess G-code chatter.
3. Use only the existing permitted **G1 ... F... S0** moves for blank travel; retain **M4** dynamic power semantics and **M5 S0** at row boundaries. **No G0, no homing, no new axis behavior**.
4. Split a qualifying laser-off gap into acceleration / fast middle / deceleration portions, with a verified safe return to burn feed before the first next `S>0` cell. Speed changes must not shift burn boundaries.
5. Use a separate persisted material setting `blank_feed`, **disabled by default** (backward compatible), and `blank_guard_mm` defaulting to 2 mm when enabled. Keep existing `row_feed`/Rewind Speed semantics unchanged. Recalculate ETA using the actual feed schedule, acceleration, and command overhead.
6. Add the new laser-off feed value to the offline verifier's allowed speeds **only for legitimate S0 gaps**. Reject unexpected `F` values on laser-on segments. Continue verifying each intended pixel burns **exactly once**, all no-burn zones stay blank, and all moves remain in the validated travel envelope.
7. Export the new options to the saved job, job README/G-code header, and Guide. Previews should distinguish laser-off fast travel from marking without implying that a fast traversed rectangle burns.

**Potential edge cases:** negative scan direction, alternating rows (feature may stay disabled), zero-length gaps, dither runs of one/few pixels, round-mask boundaries, no-burn zones, one-dot islands, overscan at image edges, row feed overrides in ladder tests, layer interlace, feature hops, interruption/recovery, simulation, and controller motion buffer timing.

### Acceptance criteria for a follow-on implementation

- Existing jobs and presets behave byte-for-byte the same when disabled, wherever practical; no automatic speed-up of loaded old jobs.
- UI settings appear next to Rewind Speed under **Left to right only** and persist with user presets and saved jobs; invalid values are rejected with clear units.
- Controlled test image: two dark blocks separated by **long blank X section**. Generated commands show S0 motion at a speed above burn feed **only where safely possible**, then burn resumes at its requested feed.
- Controlled short gaps (e.g. 1–5 mm) stay unchanged, or are dynamically capped; no pretend 6,000-mm/min motion where there is insufficient braking room.
- At least two tested burn feeds, including a very slow user tin scenario and a faster slate/wood-like scenario, prove the transition calculation and verifier behavior.
- Offline comparison shows identical burn mask, dimensions, power, origin and intended burn count between optimized and baseline jobs; trace/geometry and forbidden-command checks pass.
- Timings and physical image alignment are compared on scrap before claiming production improvement. No laser test is claimed by a software unit test.

## 5. Suggested controlled next experiments

1. **Tin:** repeat same artwork on matching matte-black lids at the latest promising settings (record what “140 at 100” means exactly), 0.15 mm, left-to-right, 6,000 rewind; measure full elapsed time, mark visibility, uneven heating and photo evidence.
2. **Tin blank-travel A/B (after feature implementation):** compare optimization off vs on with *same* input, origin, power, burn feed and full return speed. Measure runtime and inspect first dots after every blank gap for light/dark bars or misregistration.
3. **Slate:** preserve the 4,500/50%/0.15 reported-good result; diagnose fog/static separately by comparing preview and actual burn map. Run 0.10 vs 0.15 only as a controlled test when ready.
4. **Jig:** remeasure center spacing and per-lid safe diameter, then dry-run all six positions using both total-travel and image/burn trace before a full batch.
5. **Wood:** treat 4,500/45%/0.15/Stucki J8 as a proposed test, with a small scrap proof first; it is unrelated to the tin-speed engineering change.

## 6. GitHub and deployment status

- Source review was against the published repository **Tboy450/laser-photo-studio**, especially `lps/planner.py`, `lps/app.py`, `lps/presets.py`, and `lps/verify.py`, including the unmerged Studio update branch in PR **#2**.
- PR **#2** already proposes **Laser-off return speed** under Scan Direction; it is a **different control** from the within-row blank-speed feature described here.
- **This document is a design/test-report handoff only.** It does **not** assert that blank-travel acceleration code has been implemented, reviewed, run, merged, installed on Windows, or tested on the physical U20.
- Avoid replacing the user's existing installed app or editing an active machine job from this report; implementation should follow through a separate tested change.

## 7. Recommended evidence checklist for subsequent sessions

For each specimen or speed optimization comparison, save: project and sample name; photo of actual engraving; input image and processed laser-input image; material/finish; raster pitch; selected speed and power with units; scan direction; rewind and blank speed; exact applied G-code/header; image and total-travel traces; time start/finish; focus and cleaning state; flags for **confirmed result / tentative / untested**; notes on fog, charring, stripes, laser-off gaps and any controller reset.

The project objective is straightforward: **retain the image quality now seen at 0.15 mm and the left-to-right tin mark quality, while eliminating avoidable slow laser-off travel without changing marking behavior or compromising positioning.**
