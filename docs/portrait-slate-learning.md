# Portrait slate: evidence and development criteria

Reviewed November 17, 2026. This is a learning record and future-feature specification, not a new material preset. The [public Artemis's Place case study](https://tboy450.github.io/laser-studio/#slate-coasters) shows the physical sample and distinguishes photographs from digital preparation. The exact photographed run still needs reconciliation to its saved job and actual runtime. Private conversation archives and full reference portraits are not part of this document.

## Corrections to preserve

- The selected composition contains the owner **with** Artemis and the title; a dog-only variation is a different design. Preserve recognizable likeness, background and untouched source variants.
- Fine texture was reported to improve the pine result despite slight blur, and later slate observations supported retaining texture. Do not simplify fur, beard or background by default. Removing an artificial mockup rim is different from deleting real portrait detail.
- Check eye orientation against the actual source. The intended relationship discussed for this composition was a darker brown iris on the viewer's left and a lighter blue iris on the right. A color mockup cannot prove burn density or the final pale-mark polarity.
- Real reflected objects and their geometry already survived in the reported sample. The remaining question concerns mirror-coated-glass appearance. A generated comparison replaced reflected objects; it was not a true inversion and cannot establish whether inversion helps.
- The reported physical contrast was slightly stronger than the supplied image. Extra sharpening and contrast are proposed comparisons, not established improvements. Stucki versus Floyd–Steinberg has no measured winner for this portrait.
- Earlier split-layer work reportedly left gaps. Future hybrid scanning must demonstrate exact coverage rather than accepting seams as an unavoidable material effect.

## Keep planning, preparation and results distinct

| Stage | Record | Evidence limit |
| --- | --- | --- |
| Earlier planning | 25% at 4000 mm/min; roughly 84 mm artwork; Jarvis/Stucki suggestions | Unvalidated suggestions, superseded for the later prepared setup |
| Proposed calibration | 25/35% at 4000 and 45/50% at 3500; 0.10 versus 0.15 mm rows | No completed grid or resolving-ability measurement established |
| Later Windows preparation | 89 × 89 mm art on a measured 100.6 mm raw slate blank; 50%, 3500 mm/min, 0.10 mm rows, Stucki, Negative on, left-to-right | Preparation record; does not identify the settings that produced each finished photograph |
| Return-speed source update | Selectable laser-off row return; local slate reopen setup selects 4500 mm/min | Preserve this newer work. Approximately 168/61/53 minutes at 600/3000/4500 returns are planner estimates, not measured runtimes |
| Physical evidence | Blank, process and finished sample photographs published in the public case study | Physical sample documented; repeatability, exact execution settings and actual duration remain open |

0.10 and 0.15 mm row pitches correspond to 254 and about 169 rows per inch. These numbers describe sampling, not independently measured physical resolution. Do not overwrite the newer 89 mm preparation or return-speed control with the earlier suggestions. Per-job placement nudges belong to that job, not to a universal slate preset.

## What the current image controls actually do

Checked against `lps/imaging.py::to_grid` and `tone_lut`, with the controls assembled in `lps/app_place.py`:

1. Crop, then optional automatic levels (`cutoff=1`).
2. Apply contrast around gray 128 with multiplier `(100 + contrast) / 100`, then brightness and gamma, clipping to 0–255.
3. Resize to the engraving grid using Lanczos.
4. If sharpening is greater than zero, apply Pillow UnsharpMask with radius 1.2 grid pixels, integer percent equal to the sharpening value, and threshold 2.
5. Apply Negative, then the selected planner style converts the grid into powered cells.

**Detail (sharpen) = 0** skips extra UnsharpMask; it does not remove source detail. Proposed values 5 and 10 mean UnsharpMask percent 5 and 10, not a calibrated 5% or 10% physical detail improvement. From contrast 0, contrast 5 means a 1.05 multiplier around mid-gray before clipping; it is not 5% more laser power. These controls change the processed engraving image, not merely the decorative preview. Keep automatic levels, brightness, gamma, dither and polarity recorded when comparing them.

## Future comparisons and acceptance criteria

None of the following is shipped or physically validated by this documentation update.

### True masked lens inversion

- Use conventional raster processing with the untouched original plus a versioned, same-size binary lens mask. For the selected grayscale/color channels, invert as `255 - original` inside the mask and copy all other pixels exactly, preserving dimensions and alpha. A feathered mask, if later proposed, is a separate experiment.
- Record source, mask and output hashes. Supply original, inverted, difference and actual planned burn-map comparisons at identical physical scale and processing settings.
- Difference outside the mask must be zero; the interior must equal the specified inversion. No reflected objects, perspective, facial features or scenery may be synthesized or replaced.
- Review the powered-cell map and eventual pale marks, including eye orientation; do not stack another inversion based only on a filename or mockup label. Current Studio has a global Negative control, not a regional lens editor.

### Detail, contrast and dither comparisons

- Use a crop containing fur, beard, eyes and letters without changing its physical scale. Preserve the untouched baseline and full composition.
- Change one variable at a time: sharpening 0 → 5 → 10; contrast 0 → 5 separately; Stucki versus Floyd–Steinberg separately. These are proposed experiments, not instructions to run equipment.
- Hold power, engraving feed, return rate, row pitch, passes, direction, polarity and all other image controls constant. Save exact processed masks/jobs and compare them with matched physical photographs, including cleanup state.
- Judge fine gaps, identity and reflection appearance, not a decorative mockup's smoothness. Promote no preset or winner until a physical comparison supports it.

### Hybrid scan direction without seams

- Current Studio chooses one scan direction for the job. Proposed regional one-direction fine detail and alternating broad shading requires a separate feature.
- Dither the complete master grid **once**, then partition its active cells using a same-grid region mask. Do not independently crop, resize, re-dither or fit either partition.
- Both partitions must retain the full canvas, origin, pitch, dimensions, transform and placement. Their active-cell union must equal the master exactly; their active intersection must be empty for one-exposure coverage. Recombined power values must equal the master cell for cell.
- Emit missing/extra/overlap difference maps and counts; all must be zero. Verify rasterized powered commands cover the intended cell boundaries and power values, including partition seams, with no accidental second exposure.
- Test empty/full regions, irregular boundaries, isolated fine strokes, alternating/forward transitions and legacy jobs. Retain power-off travel and run-up behavior. Compare total planned time including extra repositioning, and label that estimate separately from measured runtime.
- Physical registration, finish and time improvements require a later matched test; exact digital coverage alone does not prove them.

### Wood relief as a separate investigation

Existing Layered Shading varies tonal coverage; it is not calibrated depth control. A proposed pine comparison at 45%, 2250 mm/min, 0.10 mm rows and 1/2/3 passes on small squares was not documented as run and must not become a slate or production preset.

Any future depth-map/removal work needs material, focus, pass order, registration, cleaning and measured recess/tactile evidence. Do not infer depth from a shaded preview or slate photograph. Stencil cutting and finish-shopping suggestions remain separate deferred work.

## Link each physical result to the actual run

Use the existing sample Test record, rather than inventing a second results database. Record source/artwork hash, processed master/mask hashes, saved job and pass-file hashes, machine/focus, substrate/finish, image controls, polarity, dither, dimensions, origin/placement, power, engraving feed, row pitch, direction, return speed, passes, actual runtime and post-cleaning observations. Distinguish operator reports from saved-command evidence and independently measured motion.

Current Test record fields can hold these facts as explicit text under source/job, drawing style, feed, pass order, result and limitations. Dedicated hash/runtime/region fields and automatic import are not implemented; keep original execution artifacts in the project archive and reference them. Blank or unresolved fields remain unknown.

Open reconciliation: identify which saved job/artwork and execution record produced each physical photo, whether return speed changed between runs, actual duration and cleanup state. Prepared settings must not fill these gaps by assumption.
