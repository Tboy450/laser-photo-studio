# Editable saved picture jobs

Opening a finished job by assigning `App.job` while clearing its picture leaves no source for image controls to rebuild. The former private portrait shortcut did this. A subsequent edit marked the layout pending, but the builder returned without clearing that state. Set job zero then remained blocked.

Use **1 Picture → Open saved Studio picture job…**, select `job.json`, or launch `Laser Photo Studio.pyw --job <job folder>`. Studio reconstructs and verifies the job before adopting any values. A failed import preserves the existing job. Opening a job does not connect, move, set zero, or start engraving.

## Settings ownership

| Settings | Saved source and precedence | Editing and persistence |
| --- | --- | --- |
| Source pixels | `picture.png`, with orientation already applied and tone/dither not applied | The editable source remains available. Saving writes its checksum and orientation contract in `editable_picture`. Reopening does not apply the original rotation/mirror again. |
| Material recipe | Entire `material` snapshot, rather than whichever built-in preset happens to be selected | Loaded recipe values win. A matching existing recipe is reused without editing or adding a preset. Otherwise a separate **Current job settings** row holds the snapshot; its project name is not registered as a material preset. Explicitly choosing a stored material replaces the recipe and image defaults. |
| Image adjustments | `look`: brightness, contrast, gamma, sharpen, negative, black_point, white_point; legacy autolevel remains readable | Current Check controls override image defaults. Edits rebuild actual pixels and commands and invalidate earlier verification. Negative applies once. Save as my preset now captures these effective controls too. |
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
| Image conversion | style, look, pitch, negative, sharpen, contrast, brightness, gamma, autolevel, black_point, white_point, halftone_cell | Conversion algorithm, material appearance, row spacing, and image controls. `look` names preview colors; style and image adjustments change mark commands. |
| Exposure and passes | feed, power, power_min, tone_power, tone_cuts, layer_rule, interlace, widen_gaps, thin_pass, thin_cap, passes | Burn feed, S values, shading/layer rules, row ordering, and fine-feature controls. Style determines which fields apply. |
| Laser-off travel | runup, feature_runup, row_feed, hop_feed, scan_direction | Row/feature acceleration space, row returns, hops, and forward versus alternating scanning. Return speed does not replace burn feed. |
| Suggestions | test_power, test_speed, piece | Test-grid ranges and suggested piece preset. These do not override an explicitly chosen piece. |

Save as my preset stores the effective material recipe and current visible image adjustments. It does not store the photograph, measured piece, or artwork placement; **Save job** stores those. The layer tone cuts from Check are included in the effective recipe.

Recipe matching compares every material field except identity/descriptions/lineage, suggested piece/test ranges, and the separately controlled picture adjustments. Matching keeps the stored preset unchanged and the job's effective image controls intact. The original imported material metadata remains in source provenance. This prevents a previous portrait's project title from becoming a new material entry on each import.

## Physical-size controls

Size labels describe physical shape and dimensions. The measured slate template is **Square 100.6 x 100.6 mm (slate)**, with 5.8 mm margins and 89 mm usable width. The separate generic 100 mm square retains its 3 mm margins for other materials; these are different dimensions. The slate template does not assume rounded corners. Its optional rounding control appears only for the slate option (including a measured slate job), and starts off for a square piece. Existing saved corner radii are preserved exactly. Hot Wheels customization appears only in the Hot Wheels context.

A loaded 100.6 mm square with 5.8 mm margins matches the named slate template. Other measured geometry gets a descriptive measured-size label rather than an unexplained Custom size or an approximate template match. Its corner radius is shown beside the inch measurements. Merely displaying a descriptive label changes no dimensions, margins, masks, origin, artwork width or command.

## Image controls and preview conventions

Auto levels is now an action that writes its 1% histogram endpoints into visible Black point and White point sliders, resets Brightness/Contrast/Gamma visibly to 0/0/1, and leaves Detail/Negative unchanged. A status message identifies Auto-applied versus subsequent Manual edits. There is no hidden Auto flag underneath the new controls. Legacy saved Auto jobs are converted to equivalent visible endpoints without resetting their historical manual values; regression tests require pixel-exact equivalence. The legacy autolevel field remains readable for compatibility. Slider labels update during dragging; an expensive rebuild is requested once on release, with a short debounce for keyboard changes. Negative changes which source tones fire, rather than merely switching preview modes.

The operator reported that Negative appeared to swap **Looks like** and **What burns**, including potentially their keys. A proposed switch of What burns to a monochrome map was withdrawn because it did not establish the cause of that report. The existing preview format is retained. A controlled UI regression checks that the Looks like image has pale slate marks at powered cells and the What burns map colors precisely those cells, and that changing views never changes commands. This offline check does not resolve the reported behavior in the active window; the actual selected view, effective look, material and key still need to be captured together before diagnosing it. Do not report this incident as fixed by changing the display format.

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
