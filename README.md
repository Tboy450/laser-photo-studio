# Laser Photo Studio 1.0

Turn a picture into a finished engraving on the **Tronxy Ultrabot U20** in a few clicks: pick the picture, pick
the material, size it, check it, run the 1% dot perimeter check, press Start. Built from
`LASER-AUTOMATION-BRIEF.md` and everything learned on the jar lids, pine planks and anodized cards.

## Install

Right-click **`install.ps1`** and choose *Run with PowerShell*. It's safe to run again, and needs no admin rights.

- **Laser Photo Studio** (desktop icon): the full app. Drop a picture or `.nc` file on it to open it.
- **Laser Perimeter Check** (desktop icon): opens straight to the 1% dot perimeter check. Drop any `.nc` file on it
  (from this app, LaserGRBL or older project jobs) to see where it will burn, and whether it fills shapes in or
  only burns their **outlines** (what LaserGRBL's Vectorize makes).
- **Pictures for `.nc` files in File Explorer.** Windows only previews picture files; for G-code it shows the icon
  of the program that opens it (LaserGRBL's "LG"). The install adds a small preview add-on, so Explorer draws what
  each `.nc` file will engrave (anodized jobs as silver on black, wood jobs in wood colours). Press F5 or reopen
  the folder afterwards. Laser-off frame files keep the normal icon.

`uninstall.ps1` removes all three. Your jobs, photos and presets are kept.

## The five steps

1. **Picture.** Photos, drawings or logos; phone HEIC photos work. Turn or mirror it if needed.
2. **Material & style.** Green = proven on your U20, yellow = a starting point from other 20 W lasers (test first).
   Each preset explains itself, shows the matching **LaserGRBL settings**, and shows the **energy** of any changes
   compared with the preset, and every setting in the units you'll meet elsewhere (power as `60 % (S600)`, row
   spacing as lines per inch, speed in in/min). Proven presets show **photos**: the ladder and grid tests, their charts, and finished
   pieces made with them (click to enlarge). Add your own test photos to any preset, and save your own presets.
3. **Size & placement.** Piece size (inches shown too), start point (lower-left corner, centre, or **any spot you
   click on the picture**, like a stripe's corner or the windshield's edge), margins and
   no-burn zones (twine holes, screws). **Move the picture** in 0.5-5 mm steps: the blue pad and blue box, and the
   machine doesn't move. **Toy car (Hot Wheels)...** gives a top view for typical 1:64 body types (coupe,
   fastback, sports car, pickup, van) and your measured Mustang: enter your car's length, width and window
   positions, and the windshield and rear window become no-burn zones, with the start point on the
   windshield's front edge, on the centerline.
4. **Look & check.** Brightness, contrast, sharpen, Negative, tone cut points. Every preview mode (Looks like,
   What burns, In LaserGRBL, Picture) has a **colour key** underneath saying what each colour, dashed box and marker
   means, a **Grid** (spacing follows the piece's size; numbers are mm from the start point) helps you read off
   positions, and the app warns when a logo's or sticker's plain background would burn as a filled rectangle. Then every command is replayed
   offline: only allowed powers and speeds, nothing outside the piece, every dot burned exactly once, laser off at
   every start and end. Nothing reaches the laser until this passes. Save the job or open it in LaserGRBL.
5. **Laser.** Connect, **move the laser head** (purple pad, purple marker in the preview) to the start point, set it,
   **perimeter check**, then Start. Hover over any button to see what it moves, or whether nothing moves. The
   **Ready to start?** list above Start ticks off each step (picture checked, connected, start point set, perimeter
   check done for this start point and picture, head at the start point) and says what's missing. Moving the
   picture or setting a new start point unticks the perimeter check. **Two crosshairs** line things up: red = the
   start point, where you put the dot; purple = where the controller thinks the head is. Click the preview to move
   the head there, or to say "the dot is really here" (nothing moves). Tick **Move the picture with the head** to
   shift the whole picture on the real piece as you jog.

The **Colours** box (top right) switches the whole app live: the original light look, **Dragonfly dark** (the navy,
cyan and amber of the NASA Dragonfly site), or a high-contrast pair for easier reading: yellow on black, black on
white, black on yellow, white on blue, blue on black. Each theme is tested for contrast (WCAG: 7:1 for the pairs'
text).

The **Guide** button (top right) explains everything in plain words: too light or too dark, negatives and
LaserGRBL's preview, print styles, LaserGRBL settings (with the Hot Wheels car's mistakes and a list of LaserGRBL's
names next to this app's), start point and perimeter check (moving the picture vs moving the head), backgrounds & stickers (why a whole rectangle burns, fills vs outlines), USB dropouts, safety and files.
Blue links in the steps open the right Guide page.

## Perimeter check with the 1% dot

The head visits each corner of the burn area with the laser **off**, then flashes your positioning dot there:
**S10 = 1%** bursts of 0.25 s, exactly like `Positioning Laser.exe`. Before each flash it checks the machine is idle
with zero output and that the controller has S10 programmed while the laser is off; each flash goes out with its own
`M5 S0` off command. It returns to the start point afterwards. Choose 1-6 flashes per corner, and optional dots along the
edges. The **Dot on (1%)** button gives a steady dot (auto-off after 60 s) for lining up the start point.

## Safety rules built in

- **Never homes.** `$H`, `G28`/`G30` and `$` setting changes are refused at the lowest level and never sent.
- Checks `$30=1000`, `$31=0`, `$32=1`, `$100=$101=100` before any laser output.
- M4 dynamic power; every move is G1 (laser-off travel is `G1 ... S0`); `M5 S0` at every row end and job end.
- One sender at a time: warns if LaserGRBL or Positioning Laser is open; only one job runs at a time.
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

**Test grid** (step 2): larger labelled patches, power across and speed down, each with a solid top and a dot ramp.
Run-ups grow automatically with speed (about 10 mm at 6000 mm/min). Save the best patch as your own preset.

## Quick answers

- **Too light?** Raise power first (the anodized preset is only 50%), then slow down; extra passes last, because
  they blur dots. Energy per mm is roughly power ÷ speed.
- **Negative** burns the light parts of a picture. Use it for photos on materials that mark light (anodized,
  slate, black acrylic); keep it off for wood and for black-on-white artwork such as the card `IMPORT.png` files.
- **LaserGRBL never inverts a `.nc` file.** Its preview draws laser-on areas light on dark, so wood jobs *look*
  negative there. See the **In LaserGRBL** preview and `docs/negatives-explained.png`.
- **In LaserGRBL, after a USB dropout**, don't use Resume or Home: it can jump to old coordinates.

## Files

- **Jobs:** `Documents\Laser Photo Studio\Jobs\<date>_<name>\` (on this PC inside `OneDrive\Documents`):
  `passes\01 Layer 1.nc ...` (one per pass), `<name> - all passes.nc` (for LaserGRBL), previews
  (`1 LOOKS LIKE`, `2 LASER INPUT`, `3 IN LASERGRBL`, `4 burn map`), `README.txt`, `job.json`, `state.json`,
  `log.txt`, `photos\`.
- **Presets and settings:** `Documents\Laser Photo Studio\my-presets.json`, `settings.json`.
- **Sample photos:** built in under `assets\samples\` (made from the project's tests by `tools\make_samples.py`,
  which lists every photo, its caption and which presets show it; sources come from the project's `outputs` folder
  and `Documents\01 Projects\Laser & CNC`). "What went wrong" photos are kept on purpose: the Hot Wheels car shows
  up under the anodized and lid presets. Photos you add go to
  `Documents\Laser Photo Studio\samples\<preset>\`.

## Folder layout

| Path | What |
|---|---|
| `Laser Photo Studio.pyw` | Starts the app |
| `install.ps1`, `uninstall.ps1` | Desktop icons and `.nc` previews |
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
