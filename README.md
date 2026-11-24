# Laser Photo Studio 1.1

Turn a picture into a finished engraving on the **Tronxy Ultrabot U20** in a few clicks: pick the picture, pick
the material, size it, set job zero, check placement, and press Start. Built from
`LASER-AUTOMATION-BRIEF.md` and everything learned on the jar lids, pine planks and anodized cards.

## Install

Right-click **`install.ps1`** and choose *Run with PowerShell*. It's safe to run again, and needs no admin rights.

- **Laser Photo Studio** (Windows Start): opens the full app. Open a picture or an editable Studio job.
- **Laser Perimeter Check** (Windows Start): opens placement checks. Open a compatible `.nc` file to see where it
  will burn and whether it fills shapes or only traces their edges.
- **Pictures for `.nc` files in File Explorer.** The install adds a read-only thumbnail add-on so Explorer draws what
  each `.nc` file will engrave (anodized jobs as silver on black, wood jobs in wood colours). Press F5 or reopen
  the folder afterwards. Laser-off frame files keep the normal icon.

`uninstall.ps1` removes all three. Your jobs, photos and presets are kept.

## The five steps

For a controlled scan-direction comparison, **2 Material → Adjust settings (optional) → Scan direction**
offers **Alternating rows** (the existing default) or **Left to right only** (returns with the laser off).
This keeps the same cells, size, power and feed, but takes longer. It is a diagnostic option for comparing
physical row alignment, not a resolution increase or guaranteed lettering fix. Older jobs retain their
original direction. The **Thin lines (centerlines)** style is a skeleton engraved in raster rows, not a
continuous vector path along each letter.

1. **Picture.** Photos, drawings or logos; phone HEIC photos work. Turn or mirror it if needed.
2. **Material & style.** Green = proven on your U20, yellow = a starting point from other 20 W lasers (test first).
   Each preset explains itself, shows the **G-code settings**, and shows the **energy** of any changes
   compared with the preset, and every setting in the units you'll meet elsewhere (power as `60 % (S600)`, row
   spacing as lines per inch, speed in in/min). Proven presets show **photos**: the ladder and grid tests, their charts, and finished
   pieces made with them (click to enlarge). Add your own test photos to any preset, and save your own presets.
3. **Size & placement.** Files with a saved print size open with **Use exact image size** selected. With this
   option on, **Width** and **Height** set the image size directly. You can edit both fields after choosing a material.
   Material and resolution changes keep your entered dimensions, including fractional millimeters.
   **Keep proportions** links the two fields. Turn it off to enter both independently. In template mode, set the piece
   size (inches shown too), start point (lower-left corner, centre, or **any spot you
   click on the picture**, like a stripe's corner or the windshield's edge), margins and
   no-burn zones (twine holes, screws). **Move the picture** in 0.5-5 mm steps: the blue pad moves the art and its outlines; the
   machine doesn't move. **Toy car (Hot Wheels)...** gives a top view for typical 1:64 body types (coupe,
   fastback, sports car, pickup, van) and your measured Mustang: enter your car's length, width and window
   positions, and the windshield and rear window become no-burn zones, with the start point on the
   windshield's front edge, on the centerline.
   For other cars, **Edit selected** changes a zone's measurements. Tick **Move / resize no-burn zones on the
   preview**, drag inside a window to move it, or drag a corner square to resize it. Round zones have a radius
   handle. This edits only the mask; it never jogs the head. Each edit rebuilds the burn map and clears the old
   perimeter check.
4. **Look & check.** Brightness, contrast, sharpen, Negative, tone cut points. Every preview mode (Looks like,
   What burns, Toolpath, Picture) has a **colour key** underneath saying what each colour, dashed box and marker
   means, a **Grid** (spacing follows the piece's size; numbers are mm from the start point) helps you read off
   positions, and the app warns when a logo's or sticker's plain background would burn as a filled rectangle. Then every command is replayed
   offline: only allowed powers and speeds, nothing outside the piece, every dot burned exactly once, laser off at
   every start and end. Nothing reaches the laser until this passes. Save the checked job or export G-code.
5. **Laser.** Connect, put the head over the selected **Job zero**, and press **Set job zero here**. The
   **Laser head** circle follows the controller's reported position. Toggle **Centers** to see the piece and
   image centers. **Jog head to clicked point** moves the head with the beam off. **Mark observed dot** puts
   a temporary marker where you click. **Apply alignment** confirms a zero shift while the head stays still.
   Choose a check and review its preview before confirming. **Total travel perimeter** checks clearance,
   **Image Trace** shows the outer edges of the powered artwork, **Stock perimeter** follows the piece with the beam off, and
   **Full burn trace** uses 2% on the marking strokes and zero power for travel. **Dry run** replays the same
   path with the beam off. Check the **Ready to start?** list before Start.

The **Colours** box (top right) switches the whole app live: the original light look, **Dragonfly dark** (the navy,
cyan and amber of the NASA Dragonfly site), or a high-contrast pair for easier reading: yellow on black, black on
white, black on yellow, white on blue, blue on black. Each theme is tested for contrast (WCAG: 7:1 for the pairs'
text).

The **Guide** button (top right) explains power, print styles, G-code settings, preview polarity, job zero,
perimeter checks, filled versus outlined artwork, USB dropouts, safety and saved files.
Blue links in the steps open the right Guide page.

## Literal engraving-outline check at 1%

The **blue lines** follow the boundaries of the actual cells that will engrave, including holes, separate
shapes and window cutouts. The check uses that same path: **M4/S10 = 1%**, laser off between shapes, then back
to start 0,0. It never substitutes a padded rectangle, image box or convex hull. Detailed/dithered pictures
can contain many tiny shapes and take longer to check. Controller settings, override and off state are
verified before tracing. **Dot on (1%)** remains available separately for lining up the start point.

The image's W/H include white space inside the file; the first dark mark need not be the image corner. The
grey **Size box** guide is optional and is not traced. The lower-left / upper-right X/Y explain where the
image sits relative to red **start 0,0**. New exports include grid/image geometry so reopening them in this
app reconstructs their exact outlines. Older/external files without enough geometry ask for the source
picture rather than silently framing a rectangle. A travel perimeter checks the motion envelope separately.

## Safety rules built in

- **Never homes.** `$H`, `G28`/`G30` and `$` setting changes are refused at the lowest level and never sent.
- Checks `$30=1000`, `$31=0`, `$32=1`, `$100=$101=100` before any laser output.
- M4 dynamic power; every move is G1 (laser-off travel is `G1 ... S0`); `M5 S0` at every row end and job end.
- One sender at a time: warns if another known laser-control program is open; only one job runs at a time.
- Opens COM4 with DTR/RTS off. Refuses to start if the controller just rebooted, if the head isn't at the start point,
  or if a job file was edited after checking. Stops if the head is reported outside the job's area.

## Running a job

Jobs run as a separate background process: **closing the app doesn't stop the laser**. Reopen the app to watch:
pass X of N, % done, minutes left, laser ON/off, and the head on the preview. After each pass the head parks and
waits for your photo; photos arriving in your phone folder (`Downloads\Mobile Devices`) are copied into the job in
order. Buttons: Pause / Resume, Stop after this row (keeps position), EMERGENCY STOP.

**If the USB drops out**, press *Resume the job...*: replug and connect, declare the stop point (nothing moves),
check it with the 1% dot, resume. It continues with the very next command, so nothing burns twice. It never homes
and never restarts by itself after a fault.

## Print styles

| Style | What it does | Best for |
|---|---|---|
| **Layered shading** | Builds tone in thin, shrinking passes on interlaced rows, so darks don't blob and edges stay sharp. | Pine and other woods (your best results) |
| **Classic dots** (Floyd-Steinberg) | Tones become tiny dots; more dots = darker. | Anodized aluminum, slate, tile, photos |
| **Smooth dots** (Jarvis) | Dots spread wider for softer tones. | Photos on light woods, slate |
| **Crisp dots** (Stucki) | Like smooth dots, slightly sharper. | Portraits on slate, tile, leather |
| **Bright dots** (Atkinson) | Fewer dots in light areas, punchy contrast. | Materials where burns spread |
| **Grid dots** (ordered) | Even, regular pattern; very predictable heat. | Graphics, uneven grain |
| **Halftone** | Round dots on a grid that grow as it gets darker. | Lids, glass, tile, comic/vintage look |
| **Grayscale power** | One pass; power follows darkness. | Basswood, maple, birch, leather (not pine) |
| **Black & white** | Every spot fully on or off. | Logos, text, line art |
| **Thin lines** | Dark strokes burned as 1-dot centerlines. | Lettering, line drawings on wood |
| **Pencil sketch** | Turns a photo into outline strokes. | A bold, fast first look at a photo |

## Material settings

**Proven on your U20** (S1000 = 100% because `$30=1000`)

| Material | Setting | Notes |
|---|---|---|
| Pine plank, photo | Layered: 25/30/35%, 2250 mm/min, 0.1 mm rows, 3 shrinking layers | Dragon test 12 / North Pole plank |
| Pine, lettering | Centerlines, max 30%, 2250 mm/min | North Pole sign letters |
| Pine, outlines | 40%, 3000 mm/min | A lone thin line only showed at 40% |
| Black anodized aluminum | Classic dots, 50%, 2500 mm/min, 0.1 mm, one pass | Heart and engineering cards |
| Coated steel lid, lines | 57% (S570), 300 mm/min | Vector lines, not photos; decorative only |

**Starting points from other 20 W lasers** (test first: this U20 needed about 3x Snapmaker's energy on pine)

| Material | Start | Source |
|---|---|---|
| Basswood / birch plywood | Grayscale 0-35%, 4000 mm/min | Snapmaker 20 W tested fill: 20% at 4200 |
| Light woods | Smooth dots 35%, 3500 mm/min | community charts |
| Slate | Crisp dots 50%, 3500, Negative on | community 20 W: 40-60% at 3500-4000 |
| Leather (real only, never PVC) | Crisp dots 35%, 4500 | community 20 W: 30-40% at 4000-5000 |
| Cardboard | Classic dots 20%, 6000 | community 20 W: 15-30% at 5000-6000 |
| White tile (black paint) | Crisp dots 90%, 2500 | community 20 W: 80-100% at 2000-3000 |
| Glass (painted/taped) | Halftone 90%, 3000 | community 20 W: 80-100% at 2500-3500 |
| Stainless + marking spray | Classic dots 90%, 1200 | Snapmaker 20 W tested fill: 90% at 1200 |
| Black cast acrylic | Classic dots 50%, 4000, Negative on | community charts |
| Coated steel lid, photo | Halftone 100%, 2500 (experimental) | lid findings |

**Wide-range lid ladder** (step 2): every power x speed as solid patches packed into a 2 in lid (option A: 50-100 %
by 10 x 50-6000 mm/min in 8 log steps, 4 mm patches; option B: by 5 %, 3 mm). One pass per speed, fastest first,
so you can stop before the slow, hot rows. Saves a printable map (`5 LADDER MAP`), burns one orientation mark,
warns about heat and run-ups past the lid edge, and records the lid material. Too many patches: it says how many
lids and makes them one at a time.

**Test grid** (step 2): larger labelled patches, power across and speed down, each with a solid top and a dot ramp.
Run-ups grow automatically with speed (about 10 mm at 6000 mm/min). Save the best patch as your own preset.

## Quick answers

- **Too light?** Raise power first (the anodized preset is only 50%), then slow down; extra passes last, because
  they blur dots. Energy per mm is roughly power ÷ speed.
- **Negative** burns the light parts of a picture. Use it for photos on materials that mark light (anodized,
  slate, black acrylic); keep it off for wood and for black-on-white artwork such as the card `IMPORT.png` files.
- **Preview polarity:** "Looks like" approximates the result; "What burns" identifies layers; "Toolpath" shows planned powered marks against dark. Toolpath is a simulated image, not live head telemetry or laser-off travel. Exported G-code already encodes Negative.
- **After a USB dropout:** use the Studio recovery checklist and verify the stop point before resuming. Never use Home on a machine without homing switches.

## Files

**November 9: saved placement and inspection controls.** Step 5 now has **Restore saved setup / position...**,
plus **Park left 3½ in** and **Return to zero** beside Start. Completed prints, inspection jogs and app
Disconnect preserve the original job reference locally. The runner releases COM4 after finishing; the
inspection buttons can reconnect and restore that reference before moving. A reset during queued motion is
recorded as uncertain, not treated as an exact last-sent stop. See [behavior and verification](docs/usb-position-recovery-2026-11-09.md).

- **Jobs** are saved in `%LOCALAPPDATA%\Laser Photo Studio\Jobs\<date>_<name>\`.
  `passes\01 Layer 1.nc ...` (one per pass), `<name> - all passes.nc` (portable G-code), previews
  (`1 LOOKS LIKE`, `2 LASER INPUT`, `3 TOOLPATH`, `4 burn map`), `README.txt`, `job.json`, `state.json`,
  `log.txt`, `photos\`.
- **Presets and settings** are saved as `my-presets.json` and `settings.json` in `%LOCALAPPDATA%\Laser Photo Studio\`.
- **Sample photos:** built in under `assets\samples\` (made from the project's tests by `tools\make_samples.py`,
  which lists every photo, its caption and which presets show it; sources come from the project's `outputs` folder
  and `Documents\01 Projects\Laser & CNC`). "What went wrong" photos are kept on purpose: the Hot Wheels car shows
  up under the anodized and lid presets. Photos you add go to
  `%LOCALAPPDATA%\Laser Photo Studio\samples\<preset>\`.

## Folder layout

| Path | What |
|---|---|
| `Laser Photo Studio.pyw` | Starts the app |
| `install.ps1`, `uninstall.ps1` | Start menu shortcuts and `.nc` previews |
| `lps\` | The app: planner, offline check, runner, recovery, Guide, simulated laser |
| `thumbnails\` | The File Explorer preview add-on (`NcThumbnails.cs`, `build.ps1`) |
| `assets\`, `tools\` | Icons and sample photos, and the scripts that make them |
| `tests\` | `python -m unittest tests.test_core tests.test_runner`, plus `tests\gui_smoke.py` |
| `docs\` | Pictures used by the Guide |

The tests include a check that the pine recipe reproduces the North Pole plank's proven layers exactly, and full
runs (including a USB dropout and resume) against a simulated laser. **Demo mode** in step 5 uses the same
simulated laser, so you can try everything without the machine.

## Version 1.0 and ideas for later

1.0 covers the brief's "what easier looks like": picture -> preset -> placement -> tone map and layers -> checked
preview -> 1% dot perimeter -> start, with photo pauses, plain progress and one-click resume after a dropout.

Ideas not in 1.0: send jobs from the controller's microSD card or Wi-Fi so USB isn't in the loop; crosshatch and
second-axis rows; presets from the planned 40-80% / 3000-6000 mm/min speed grid; a vector line mode for lids.


## Samples and continuing learning

Open a sample photo and choose **Test record...** for Evidence, Surface and Settings tabs. Your photos have editable records; built-in examples show source-maintained records. Blank fields are unknown, and older photos keep their captions without invented settings. Saving a test record does not change the material preset or a job. The Guide topic **Test records & recent learning** explains current findings and unrun proposals. See `docs/learning-workflow.md` for the ongoing intake, privacy, validation and update process.
