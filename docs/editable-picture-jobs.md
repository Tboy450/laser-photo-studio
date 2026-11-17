# Editable saved picture jobs

Opening a finished job by assigning `App.job` while clearing its picture leaves no source for image controls to rebuild. The former private portrait shortcut did this. A subsequent edit marked the layout pending, but the builder returned without clearing that state. Set job zero then remained blocked.

Use **1 Picture → Open saved Studio picture job…**, select `job.json`, or launch `Laser Photo Studio.pyw --job <job folder>`. Studio reconstructs and verifies the job before adopting any values. A failed import preserves the existing job. Opening a job does not connect, move, set zero, or start engraving.

## Settings ownership

| Settings | Saved source and precedence | Editing and persistence |
| --- | --- | --- |
| Source pixels | `picture.png`, with orientation already applied and tone/dither not applied | The editable source remains available. Saving writes its checksum and orientation contract in `editable_picture`. Reopening does not apply the original rotation/mirror again. |
| Material recipe | Entire `material` snapshot, rather than whichever built-in preset happens to be selected | Loaded values win over preset defaults. The material tree and advanced controls show the same snapshot. Explicitly choosing another material replaces the recipe and image defaults. |
| Image adjustments | `look`: brightness, contrast, gamma, sharpen, autolevel, negative; missing legacy keys use their material values | Current Check controls override image defaults. Edits rebuild actual pixels and commands and invalidate earlier verification. Negative applies once. Save as my preset now captures these effective controls too. |
| Piece geometry | `piece`: name, shape, width/height, origin and optional spot, margins, corner, keepouts | Exact saved geometry is retained. “Custom size” means measured saved geometry; it is not a fallback permission to ignore dimensions. An explicitly chosen piece survives later material selection. |
| Artwork placement | `placement`: fit, art_w, dx, dy; `keep_proportions` retained separately | Whole-image width and offsets survive saving/reopening. Changes rebuild the layout. |
| USB connection | Machine settings and current port selection, outside picture-job metadata | Loading a job preserves the selected port. No saved picture job silently switches COM4 to COM6. |
| Provenance | Original picture identity/checksum where available, saved source transforms, parent/reference job, any defaults used | Retained for tracing a source and recipe. A referenced prepared job is not proof of a completed physical run. |

The loader recognizes every current `Material` dataclass field. Unknown material, image-adjustment, or placement fields produce an explicit import error rather than being silently discarded. Missing legacy material fields are listed as defaults used. Supported saved image passes are raster rows and features. Generated grids, dwell/crawl jobs, and other unsupported modes must use their original preparation flow or G-code check mode.

## Material schema audit

These are the actual fields from `lps/presets.py`; no extra preset format is introduced:

| Group | Fields | Meaning |
| --- | --- | --- |
| Identity and presentation | key, name, badge, summary, notes, based_on | Snapshot identity, category, explanations, and recipe lineage. A preview sample is not evidence that this picture was physically engraved. |
| Image conversion | style, look, pitch, negative, sharpen, contrast, brightness, gamma, autolevel, halftone_cell | Conversion algorithm, material appearance, row spacing, and image controls. `look` names preview colors; style and image adjustments change mark commands. |
| Exposure and passes | feed, power, power_min, tone_power, tone_cuts, layer_rule, interlace, widen_gaps, thin_pass, thin_cap, passes | Burn feed, S values, shading/layer rules, row ordering, and fine-feature controls. Style determines which fields apply. |
| Laser-off travel | runup, feature_runup, row_feed, hop_feed, scan_direction | Row/feature acceleration space, row returns, hops, and forward versus alternating scanning. Return speed does not replace burn feed. |
| Suggestions | test_power, test_speed, piece | Test-grid ranges and suggested piece preset. These do not override an explicitly chosen piece. |

Save as my preset stores the effective material recipe and current six image adjustments. It does not store the photograph, measured piece, or artwork placement; **Save job** stores those. The layer tone cuts from Check are included in the effective recipe.

## Source and command verification

Before changing UI state, the loader:

1. Confirms a supported Studio picture job and settings schema.
2. Reads the saved pre-tone image and checks its checksum when present.
3. Regenerates the job from the saved material, look, piece, and placement.
4. Compiles it and runs the offline command verifier.
5. Checks every saved pass checksum and requires an exact match between its command body and the reconstructed body.

Legacy jobs without an image checksum still require exact command reconstruction. This proves consistency with the saved commands; it cannot establish provenance that an older file never recorded. The loader rejects mismatches instead of guessing whether a picture is already processed.

G-code check mode now disables material/size tabs and image adjustments, with an explanation that the commands are already encoded. Reopening an editable picture job restores those controls. A missing source or failed build clears the indefinite pending state and shows a blocking error; it does not bypass checks or the normal zero workflow.

## Explicit CLI connection and local receipt

`--job <folder> --connect COM4` explicitly requests a connection after a successful editable import. It uses the regular connection workflow and never moves, declares zero, or starts printing. The normal saved-job shortcut need not include `--connect`.

Optional `--startup-report <local JSON path>` records the loaded settings and connection readiness. It stops polling after a fresh idle connection with a verified current layout, or after a bounded wait. This receipt is startup evidence, not continuing machine monitoring or a completed-print record. It is written locally and is not uploaded.

## Validation and limits

`tests/test_picture_jobs.py` exercises the full material/geometry snapshot, startup selection events, live changes to actual compiled output, one-time inversion, rotated/mirrored save-and-reopen, tampered inputs, unsupported schema, source-less pending failure and zero guard, read-only G-code controls, and effective preset image controls. Physical serial access is forbidden in these tests.

The private portrait was also reconstructed in an isolated Tk app with the actual source and exact saved commands. Customer images, launchers, connection receipts, and recovered correspondence are kept outside this public repository.

Offline verification establishes the consistency of settings and commands. Physical portrait quality and the separate shared computer-control Escape/ownership incident require their own evidence; this change does not claim to fix that provider issue.
