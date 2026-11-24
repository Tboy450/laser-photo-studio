"""Guide text shown by the Guide button. Plain words, short topics.
Markup: '# ' heading, '- ' bullet, '1. ' numbered step, '[image:<path in app folder>]', blank line = gap."""
from __future__ import annotations

from .presets import STYLES

START = """# Five steps
1. Picture - open a photo, drawing or logo (phone HEIC photos work). Turn it if it's sideways.
2. Material - pick your material. Green = proven on your U20. Yellow = a starting point from other 20 W lasers: run a test grid first. Proven settings show photos of their test ladders and charts, and of finished pieces made with them; click a photo to enlarge it.
3. Size - enter the piece size, where the start point is (lower-left corner, centre, or any spot you click on the picture) and any no-burn zones like twine holes.
4. Check - adjust the picture while watching the preview. The app replays every command before anything can run.
5. Laser - connect, set the start point, run the perimeter check with the 1% dot, then Start. The 'Ready to start?' list above the Start button ticks off each of these and says what's still missing.

# The preview buttons
- Looks like: roughly how the finished piece will look on the material.
- What burns: each pass in its own colour.
- Toolpath: planned laser-powered marks on a dark background; any overlaid head marker is separate controller telemetry, not part of the rendered toolpath.
- Picture: the adjusted picture before it becomes laser moves.
Each one has a colour key under the preview that says what every colour, dashed box and marker means.
The Grid tick box draws squares over the piece. Their size follows the zoom (finer on a small piece) and the key says how big they are. The numbers are mm from the start point, the same as the X/Y in step 5, so you can read off where anything will land.

# Colours
The Colours box at the top switches the whole app straight away and remembers your choice: the original light look, Dragonfly dark (navy), or a high-contrast pair (yellow on black, black on white, black on yellow, white on blue, blue on black) if text is hard to read. This Guide names the original colours, like the red crosshair; in other themes the colour key under the preview shows what's what.

# Wide-range lid ladder
Step 2's 'Wide-range lid ladder (2 in circle)...' packs solid patches for every power and speed onto a lid. The app picks the patch size (option A: 6 powers x 8 speeds as 4 mm patches; B: 11 x 8 as 3 mm), or says how many lids it takes. Each speed is a pass, fastest first and slowest last, so with 'Pause after each pass' you can stop before the slow, hot rows. The saved job folder has '5 LADDER MAP - print this' showing every patch's setting; one small mark burns at the top so you can line the map up. Note which lid material you ran it on: it goes in the job name and the map.
Stopped part way? 'Continue a stopped lid ladder...' reads the stopped job, leaves out every speed that finished and the rows already burned, and keeps every patch on its first spot so the first map still applies. Pick the order: fastest first, slowest first, or hottest first (one patch per pass, the slowest speed at 100 % first, then down), and keep 'Pause after each pass' on so the lid can cool between patches. Keep the same job zero: don't move the lid or reset the controller.

# Good habits
- New material? Burn a test grid first (step 2) and save the best patch as your own preset.
- Add your test and result photos to the setting ('Add my photo...' in step 2), so next time you can see what each setting did.
- Always run the perimeter check before burning.
- Take a photo after each pass; the app pauses for it and files the photos in order."""

DARKNESS = """# What makes a mark darker
Darkness comes from how much laser energy each spot gets:
- More power = more energy.
- Slower speed = more energy (the beam stays longer on each spot).
- Another pass = the same energy again, on top.
Energy per mm is roughly power divided by speed, so halving the speed is about the same as doubling the power. Step 2 shows the energy of your settings compared with the preset.

# Which one to change
1. Power first. Your anodized cards ran at S500 = 50% (S1000 = 100% on your U20), so there is room: try 60-75%.
2. Speed second. 2500 -> 1800 mm/min is about 40% more energy, but the job takes longer.
3. Extra passes last. A second pass never lands exactly on the first, so dots blur and fine detail softens.

# Signs of too much
- Dots merge into solid patches and detail disappears.
- Anodized coating turns grey or brown instead of bright silver.
- Wood: dark areas become scorched blobs and thin white gaps close up.

# On wood (Layered style)
Change tone with the tone cut points in step 4, or 'Tone by layer count' in step 2, rather than power. On pine the power shades S200-S350 all burned about the same; extra layers add darkness without blobs."""

NEGATIVE = """# What Negative does
Negative burns the LIGHT parts of the picture instead of the dark parts.
- Use it when the laser makes LIGHT marks and you engrave a photo: black anodized aluminum (silver marks), slate (pale grey marks), black acrylic.
- Keep it off for wood, leather and cardboard: the laser makes dark marks there.
- Keep it off for black-on-white artwork that should be marked as drawn, like the card IMPORT.png files. They are already 'black = laser fires'.

# Check polarity before saving
- 'Looks like' previews the expected finished material.
- 'What burns' shows the marks sent to the laser.
- 'Picture' shows the adjusted source before it becomes G-code.
- Exported .nc files contain the final toolpath: changing a picture later does not modify an already exported file."""

GCODE = """# G-code and machine settings
Laser Photo Studio produces verified G-code for its supported controller configuration.
- Power S-values: the U20 uses $30=1000, so S500 means 50% of the configured maximum.
- F values: movement speed in mm/min. F2500 means 2500 mm/min, not 2500 mm/s.
- Row spacing: millimetres between raster lines; 0.15 mm is about 6.67 lines/mm.
- M4: dynamic laser power for moving marks. M5 S0 commands the laser off.
- Negative: image-processing choice applied before the file is built; exported .nc already contains it.
- Layer count, cooling row groups and laser-off run-up distances affect duration and edge quality.
- Check device power scale, axis calibration, acceleration, work offset and travel limits before using exported files on a different machine.

# How to check
Compare Looks like, What burns, and Toolpath before saving. The Toolpath image shows planned powered marks, not unpowered travel or the actual position of a connected laser. Use the app's job verifier and laser-off perimeter check; don't rely on a picture alone for motion safety."""

PERIMETER = """# Place â†’ Set zero â†’ Check â†’ Start
Choose the job zero in Step 3. Use the piece center, the lower-left corner, or a recognizable spot you pick. Put the positioning dot on that same spot on the real piece, then press 'Set job zero here' in Step 5. The head stays still while the controller assigns that spot X0 Y0.

# Read the labeled markers
- Job zero (crosshair): the fixed reference all job coordinates use.
- Laser head (circle): the controller's reported position in that coordinate system. A last-reported label appears if position updates stop.
- Piece center: the midpoint of the material. Image center: the midpoint of the placed picture. Toggle Centers to see both. Coincident points share a label.

# Know what each action changes
- Jog head to clicked point moves the physical head with the beam off. The engraving placement stays fixed.
- Mark observed dot adds a temporary diamond where you click. Apply alignment shows the proposed zero shift and writes it only after you confirm. The head stays still.
- Move the picture in Step 3 to edit the layout. 'Shift engraving placement when jogging' deliberately moves the placement with the arrow buttons. Check the new placement before starting.

# Exact size
On a rectangular piece, 'Use exact image size' lets you set the picture's width and height directly. With 'Keep proportions' on, the starting box uses the source image's shape and the two fields stay linked. Turn it off to enter each dimension independently. If you have yet to choose a piece, a picture file with a saved print size can open in exact mode. Use 'Use the size saved in the file' to apply those dimensions on demand.

For a round lid or a piece with its own outline, turn on 'Use exact image size' and enter Requested width under Picture size. The outline, margins, zero, offsets and image proportions stay in place. If the usable face is smaller than the request, it limits the width and height together. Check shows the grid dimensions and powered mark dimensions separately. The exact mode may change actual cell spacing, so compare saved pairs before switching modes between passes.

To size what actually engraves, choose 'Set engraved width (outside marks)' in Picture size. Enter the width across the outer marks, such as 48.60 mm for a centered ring. Studio samples the artwork around its powered region and scales it proportionally around the same picture center. Check reports any clipping from the rim, outline or no-burn zones. For two layers, compare against the saved companion before starting. Two independently sized masks may have different grids even when their engraved widths agree.

To keep an existing piece, settings, and placement while opening a different picture, use 'Replace picture and keep layout' in step 1. Check the new grid, particularly when the new picture has different proportions. Open the saved Studio job to restore its exact piece and recipe. Use 'Compare another pass' in Check for paired layers.

On rectangles, Exact size uses the picture box's lower-left as job zero unless you choose the center or another spot. Step 5 lists the image corners in X/Y from that zero. Blank space is part of the image box, so the first mark can be offset from 0,0.

# Other cars and editable no-burn zones
The Mustang is one starting shape, not a required car. Pick the nearest body type and measure your own car in Toy car, or add rectangular/circular no-burn zones in step 3. Select a zone and press Edit selected to change X, Y, width/height or radius. Coordinates are measured from the piece's lower-left, even when the job starts at a picked spot.

Tick 'Move / resize no-burn zones on the preview'. Drag inside a window to move it. Select it and drag a corner square to resize; a round zone has a radius handle. Double-click a zone for its measurements. Only the no-burn mask changes, never the laser head or start point. Release the mouse to rebuild the burn map. Zone changes clear the old perimeter check, so check the new layout before starting.

# Choose the check that answers your question
- Total travel perimeter (off): check head clearance around the full travel rectangle, including laser-off run-ups. It can cross a no-burn zone with the beam off.
- Image Trace (1%): follow the outside of the powered artwork shown in the selected passes. Closed holes are skipped and the beam is off between separate exterior shapes. Show all passes for a placement check of the full design.
- Stock perimeter (off): follow the outside edge of the piece entered in Size & placement.
- Full burn trace (2%): replay the checked picture job with 2% on the planned marking strokes and the beam off during travel. This may take as long as the engraving.
- Dry run (off): replay the same path with the beam off throughout.

Each button shows its path before the confirmation. Stop check lets queued moves settle, then returns to job zero while the connection and position are known. Disconnect and window close let queued moves settle at the stop position. Changing the layout or job zero clears completion for the old placement. An imported G-code file can use the checks supported by the geometry the app can read from it.

The dot is the real engraving laser at very low power, so still wear laser glasses.

# Curved or small pieces
Use Image Trace to judge where the visible shapes land. Use Full burn trace and its preview to inspect individual strokes near windows. No-burn zones remove marks from the job.
For toy cars use 'Toy car (Hot Wheels)...' in step 3. It has typical 1:64 body types and your measured Mustang; measure your car, and it turns the windows into no-burn zones and puts the start point on the windshield's front edge (or the middle of the roof, or the nose).

[image:assets/samples/hw-setup.jpg]"""

DROPOUT = """# What is saved
The local Recovery record keeps the picture, material settings, size, masks, placement, selected job zero, controller work offset, and reported machine/work coordinates. Completed inspection jogs and parks have a separate confirmed idle checkpoint. Trace progress and engraving command indices are saved separately: accepted means queued, not necessarily completed.

# Unplugged after an inspection jog
1. Reconnect in step 5, then choose Restore saved setup / position.
2. Confirm that the head and material have stayed physically in place since the saved completed move. The app restores the saved layout and coordinate reference without moving the head, even if the controller restarted.
3. Move head to job zero returns to the saved project center/corner with the laser off. A normal inspection jog never relocates the picture.

# Interrupted while moving
A replug may reset the controller. The saved last-sent endpoint is only a candidate; it is not an encoder measurement. If the controller kept its frame and was not reset, Restore saved setup can use its current idle report after your confirmation. If the frame changed mid-move, the app retains the evidence instead of automatically assigning the last-sent endpoint.
For an engraving, Resume after dropout shows the last reported position, confirmed idle point, and sent/accepted indices. Check the candidate position before declaring or resuming it. Reconnects do not automatically jog or start a job. Never Home this machine: it has no homing switches.

# Where the record lives
%LOCALAPPDATA%\\Laser Photo Studio\\Recovery\\COM4.json (local disk, not OneDrive). Earlier references are preserved in the history subfolder. Demo mode uses a separate demo-COM4.json. Engraving state.json also carries the position record.

# Fewer dropouts
- A short, shielded USB cable with a ferrite clip, in a port on the back of the PC.
- Keep the USB cable away from the laser's power lead.
- Don't move the cable during a job."""

BACKGROUNDS = """# Why a rectangle burns
A picture is always a rectangle. Every pixel in it is either 'burn' or 'don't burn', including the background around your logo, sticker or stripes. If the background counts as 'burn', the whole rectangle burns.
- With Negative OFF (wood, leather, card) dark pixels burn: the background must be WHITE.
- With Negative ON (anodized, slate, black acrylic) light pixels burn: the background must be BLACK.
- Transparent backgrounds (PNG stickers) are turned into white. That's right with Negative off, but with Negative on the white burns, so the rectangle burns.

# How to spot it before burning
- 'What burns' (preview): anything coloured gets the laser. If the whole art box is coloured, the background is burning.
- The app warns you when the picture burns right to the edge of its box all the way round.

# How to fix it
1. Use a picture with a plain background: white when Negative is off, black when it's on. A photo-editor or 'remove background' tool, then fill the background with that colour.
2. Or flip Negative, if the art itself is drawn the other way round.
3. Check 'What burns' again: only the shapes should be coloured.

# Fills and outlines
A filled shape (a solid stripe) needs the laser to scan rows across it, which Studio's raster styles do. A vector outline or centerline follows an edge or a middle line, leaving the fill blank. That's what happened on the Hot Wheels car.
To check a file before burning it, open it with 'Check a G-code file instead...' in step 5 (or drop it on the Laser Perimeter Check icon). The app says 'Fills shapes in' or warns 'OUTLINES ONLY'.

[image:assets/samples/hw-front.jpg]"""

SAFETY = """- Stay with the machine the whole time. Wood, cardboard and leather can catch fire.
- Wear laser safety glasses made for your laser's wavelength, also for the 1% dot.
- Ventilate: smoke from wood, leather and acrylic is unhealthy.
- Never laser PVC, vinyl or faux leather: they release chlorine gas.
- Air assist gives cleaner marks and less fire risk.
- Etched jar lids are decorative only: heat goes through the coating.
- Never use Home on this machine; it has no homing switches."""

FILES = """# Where jobs go
Documents\\Laser Photo Studio\\Jobs\\<date>_<name>\\ (on this PC that's inside OneDrive\\Documents).
- '01 Layer 1.nc', '02 ...': one file per pass, in order.
- '<name> - all passes.nc': everything in one G-code file, without photo pauses.
- '1 LOOKS LIKE': the expected result. '2 LASER INPUT': black = laser fires.
- '3 TOOLPATH': simulated powered marks, not head movement. '4 burn map': a colour per pass.
- README.txt explains the folder; photos\\ collects photos after each pass.

# Pictures for .nc files in File Explorer
Windows typically shows a generic icon for G-code. install.ps1 adds a read-only thumbnail preview for compatible .nc files; press F5 or reopen the folder after installing. uninstall.ps1 removes it.

# Your presets and settings
Saved presets are in %LOCALAPPDATA%\\Laser Photo Studio\\my-presets.json. Use the Settings button to change the port and phone photo folder.

# Sample photos
The photos under 'About this setting' come from the project's tests and finished pieces (the app's assets\\samples folder). Photos you add go to %LOCALAPPDATA%\\Laser Photo Studio\\samples\\<setting>\\ and can be removed again in the photo viewer."""


def styles_text() -> str:
    out = []
    for s in STYLES.values():
        out += [f"# {s['name']}", s["what"], f"Why: {s['why']}", f"Best for: {s['best']}", ""]
    return "\n".join(out).strip()


LEARNING = """# Samples are evidence for a stated setup
Open a photo under About this setting, then Test record. User photos have editable Evidence, Surface and Settings tabs. Blank fields mean unknown, not a default borrowed from the selected preset. Old photos remain available without inventing missing metadata.
Keep source/job/photo, actual substrate and preparation, focus, power, commanded feed, motion evidence, row pitch, M3/M4, passes/dwell and cleanup/result together. A photographed result, an operator report, a prepared experiment and a repeated physical test are different evidence states. None automatically promotes a material preset.

# Recent reflective-lid learning
- The November 13 speed-line sample used 100% with commanded feeds 50, 44, 33 and 22 through 12 mm/min. Saved telemetry/timing suggests a low-feed floor near 23.6 mm/min; it is not independent motion metrology or a verified firmware diagnosis. Displayed F alone does not prove physical travel speed.
- Prior Red Hill raster jobs used about 0.10 mm row pitch (254 lines/in). That is spacing between raster scan rows, not necessarily the gap between visible test stripes. Smaller pitch changes raster overlap/exposure; it does not add energy to a single vector line or stationary dot.
- November 12 combo pass 6 uses M3 with timed G4 dwells at 80/100%, 5/10/20/40 seconds. The reported weak pinpoint result cannot be explained by stopped M4 dynamic power: this saved pass used M3. No durable dark recipe was established.
- Judge tones before AND after wiping. A dark-looking deposit that wipes away is not established as a permanent dark metal mark. Record sanding, coating, cleaning and whether wiping was done; do not infer them from appearance.

# Historical penetration report
The operator retrospectively linked tin penetration and 56 damaged book pages to the initial October 26 pulse/vector test sequence. Saved transcript commands establish a 1% two-second stationary M3 pulse, an 80% 10 mm M4 line at F3000, then an 80% 10 x 10 mm M4 outline at F240. These are historical evidence, not a suggested test. The exact perforating command, stock thickness and focus are unconfirmed. None of these has raster DPI. A book is unsuitable backing; deeper-penetration planning needs identified stock/thickness/focus and a noncombustible beam stop.

# Portrait and slate comparisons
Retain the source's fine portrait texture unless a controlled physical comparison supports removing it. Detail (sharpen) at 0 means no extra sharpening, not no source detail. Positive values apply UnsharpMask after resizing; they are not a calibrated physical detail percentage. Contrast 5 applies a 1.05 multiplier around mid-gray before clipping, not extra laser power.
Judge light-mark polarity from the actual powered-cell map and material result, including eye orientation. A generated redraw is not evidence of a pixel-preserving local inversion. Regional lens inversion and hybrid scan directions are future experiments; Studio currently applies Negative and scan direction globally. Any future hybrid must partition one master dither on shared coordinates with no missing or overlapping active cells. Layered Shading is tonal coverage, not calibrated depth control.
The public Artemis sample is documented at https://tboy450.github.io/laser-studio/#slate-coasters . Exact photographed-job settings and runtime still need reconciliation. See docs/portrait-slate-learning.md in the source repository for the correction history and future-feature criteria. Suggested sharpening/dither changes are not proven presets.

# Pending experiments and boundaries
A published illustration can show a prepared plan; publication does not establish a completed physical test. The seven-band DPI test is prepared, not physically run. The three vertical marks through the newly sanded patch (soot, rose-brass, slow centre-line) are a different proposed surface comparison, not a result and not the seven-band test. The later dot test remains a proposal after the DPI result. Crawl code passed offline tests but has no physical validation recorded here.
Surface changes, focus, actual motion and drawing method can affect results; do not turn one successful lid into a universal production recipe."""


DEVELOPER_CONTACT = "https://tboy450.github.io/#contact"

ABOUT = """# Developed by HASK
Laser Photo Studio was created to make laser software clearer and more controllable: explain confusing controls, provide the adjustments people need, and replace misleading terminology with plain language.

# Compatibility
This version supports the Grbl-based Tronxy Ultrabot U20 setup. That connection is compatibility context; the app's purpose is a clearer engraving workflow.

# Contact HASK
Open the public contact page:
""" + DEVELOPER_CONTACT


ROUND_TINS = """# 2 in reflective tin lid (template)
Step 3's 'Reflective tin lid 2 in (45.72 mm face, centre zero)' is a size template only:
- Outside diameter 50.8 mm, 2.54 mm margin all round, so the usable face is a 45.72 mm circle.
- Job zero is the physical centre of the lid.
- The lid ladders use exactly the same geometry, so a ladder job and a tin job line up on the same lid.

It is not an engraving recipe. Pick the material and style separately; the tin results are still being tested, so
keep their evidence status honest.

Precedence: a loaded saved job keeps its own size; editing width, height, margins or origin turns the template into
a measured size; picking a template replaces the size and rebuilds the job. The note under the template list says
which of these applies right now.

# Centring a tin in a jig
1. Seat the lid fully in its pocket, and check the jig itself is registered to the bed.
2. Use the low-power dot to find the actual centre of the lid (or a jig reference checked against that centre).
3. Jog there and press 'Set job zero here' in step 5. That sets the work coordinate; it does not move the head.
4. Run the perimeter check. It checks the planned footprint around job zero; it cannot see a lid that sits off-centre
   in its pocket."""


MACHINE_CHANGE = """# When the laser hardware changes
A PROVEN label belongs to the exact setup that was tested, not just the frame name or the advertised wattage.
- A different diode module, lens, controller, firmware or axis calibration can change the result.
- After a hardware change, treat old results as history: don't carry their PROVEN label forward automatically.
- Recheck focus and placement, burn new test grids, and compare real samples before saving new proven presets.
- Keep the old photos and settings, so the new setup can be compared with the old one."""


WOOD_SURFACE = """# Reading the wood surface
Wood is not a flat, even sheet:
- Grain, knots and uneven colour change how the finished mark reads.
- Ordered dots are easier to compare across grain, but they don't fix a ridge or a change in surface height.
- A raised or warped area changes the lens-to-wood distance. Support the board and check focus across the image.
- Use an offcut or test area when changing species, surface preparation or image style.

# Stain and finish records
There is no universal stain-before or stain-after setting. Record the finish product, whether it went on before or
after the burn, and its dry/cure state. Compare matching offcuts before choosing a sequence.

# Surface marks
A diode burn marks the surface. It doesn't cut a routed groove or carve relief, so record appearance, residue and
finish separately from depth."""


def topics(mat) -> list:
    return [("Start here", START),
            ("Too light or too dark?", DARKNESS),
            ("Negative & previews", NEGATIVE),
            ("Print styles", styles_text()),
            ("Test records & recent learning", LEARNING),
            ("G-code & machine settings", GCODE),
            ("Start point & perimeter check", PERIMETER),
            ("Round tins & jig centring", ROUND_TINS),
            ("Wood grain & finishing", WOOD_SURFACE),
            ("Machine changes & revalidation", MACHINE_CHANGE),
            ("Backgrounds & stickers", BACKGROUNDS),
            ("USB dropouts", DROPOUT),
            ("Safety", SAFETY),
            ("Files & previews", FILES),
            ("About & contact", ABOUT)]
