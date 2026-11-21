# AI handoff: tin two-tone image passes and material settings (2026-11-21)

**Source:** verified against this repository's `main` code on 2026-11-21. The user's installed PC settings files, uncommitted edits, and real laser were not available in this session. **This note does not change code or establish a new validated material preset.**

## Relevant code — inspect these first

- `lps/presets.py`, `Material`: `pitch` is mm per row; `feed` mm/min; `power` is GRBL S (S1000 = 100%); `negative` determines invert; `runup`, `row_feed`, `hop_feed`, `passes` are fields.
- `lps/presets.py` `load_materials`/`save_user_material`: user-defined material presets are JSON in `Documents\\Laser Photo Studio\\my-presets.json`, appended to built-in presets. Read and back up existing file before editing; **do not replace it blindly**.
- `lps/jobs.py` `load_settings`: general connection/application settings are in **separate** `Documents\\Laser Photo Studio\\settings.json`.
- `lps/app.py` `_adv_changed`: UI has row spacing 0.05–0.5 mm, feed clamped 100–6000 mm/min, and UI percent power converted to S units (percent ×10).
- `lps/imaging.py` `load_picture`: PNG is flattened on white and converted to grayscale.
- `lps/planner.py` `plan_cells`: `threshold` burns pixels with lightness <128. For explicit black-on-white engraving masks, use **negative OFF**.
- `lps/planner.py` `build_job` / `JobPlan`: **one Material configuration per job**, including all its passes. Independent copper and silver recipes **cannot currently be assigned to two different passes in a single job**.
- `lps/planner.py` `raster_commands`: `flip` alternates direction each engraved row (serpentine). This is **not** single-direction left-to-right. `row_feed` handles laser-off positioning between rows; the existing `runup` is not a separately configurable 6000-mm/min return/reverse scan with extra 2–3-mm lead-in.
- `lps/jobs.py` jobs are saved in `Documents\\Laser Photo Studio\\Jobs` with per-pass .nc, combined .nc, job.json and previews.
- `lps/presets.py` `PIECES["lid76"]`: built-in 76.2-mm jar lid with 49-mm usable flat face **is not a verified dimension for other gift tins**.

## Physical tin observations from operator (not code tests)

- Reported previously successful **tin** baseline: `0.15 mm` row spacing, speed set to `140`, power `100%`, left-to-right scan, return `6000`. Confirm speed units/app equivalence when importing these historical settings; the current app planner does not offer those exact motion semantics.
- `0.10 mm` might have been chosen to reduce barely visible raster scan lines, but this is a hypothesis, **not a verified historical reason**. Compare 0.10 and 0.15 on scrap using identical artwork.
- Copper tone reportedly looked good at baseline, but the **stainless/silver recipe is not yet verified**. Do not label either RGB mockup colors or a guessed setting as a physical silver pass.
- The built-in coated-steel experimental halftone preset (S1000, 2500 mm/min) is **not** the operator's copper baseline.

## Compatible two-tone interim workflow

Prepare **two strictly co-registered monochrome PNGs**, one intended for each tone: black = intended burn; white = no burn. Keep identical pixel bounds, origin, width, placement, and orientation. Import and verify as two **distinct jobs** in the current version; keep the tin physically fixed. Laser-on decisions/polarity and perimeter check must be verified for each job. Use a sacrificial tin to calibrate two real tone recipes before engraving gifts. A photorealistic mockup is not clean production vector art; remove reflection noise / excessive small details at final dimensions.

## Engineering continuation

1. Add `scan_direction = serpentine | left_to_right` and `rewind_feed` to `Material` and UI, with conservative migration for existing JSON.
2. Update `raster_commands` to return at configured laser-off rate and apply a few millimeters of lead-in and lead-out, without allowing moves outside the safe workpiece or bounds. Test feed and safety with `lps/verify.py`, `lps/machine.py`, `lps/fakegrbl.py`, `tests/test_core.py` and `tests/test_runner.py`.
3. For native two-tone sequencing, implement **per-pass** feed, power, pitch and associated material identifier in the job manifest; pause for a human verification between independent tone jobs.
4. Confirm the current user's PC's `my-presets.json`, `settings.json` and actual flat tin diameter before changing app data. Do **not** expose any private client art or contact details in this public repository.

**Scope:** Documentation/continuation instructions only. No code change, machine contact, physical validation, or saved live material preset in this PR.
