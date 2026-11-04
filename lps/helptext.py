"""Guide text shown by the Guide button. Plain words, short topics.
Markup: '# ' heading, '- ' bullet, '1. ' numbered step, '[image:<path in app folder>]', blank line = gap."""
from __future__ import annotations

from .presets import STYLES, lasergrbl_recipe

START = """# Five steps
1. Picture - open a photo, drawing or logo (phone HEIC photos work). Turn it if it's sideways.
2. Material - pick your material. Green = proven on your U20. Yellow = a starting point from other 20 W lasers: run a test grid first. Proven settings show photos of their test ladders and charts, and of finished pieces made with them; click a photo to enlarge it.
3. Size - enter the piece size, where the start point is (lower-left corner, centre, or any spot you click on the picture) and any no-burn zones like twine holes.
4. Check - adjust the picture while watching the preview. The app replays every command before anything can run.
5. Laser - connect, set the start point, run the perimeter check with the 1% dot, then Start. The 'Ready to start?' list above the Start button ticks off each of these and says what's still missing.

# The preview buttons
- Looks like: roughly how the finished piece will look on the material.
- What burns: each pass in its own colour.
- In LaserGRBL: how LaserGRBL's preview will draw the file.
- Picture: the adjusted picture before it becomes laser moves.
Each one has a colour key under the preview that says what every colour, dashed box and marker means.

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

# Why LaserGRBL looks like a negative
LaserGRBL never inverts a .nc file. Its preview draws every spot where the laser fires as a light line on a dark background (brighter = more power). So:
- Anodized jobs look like the real result (silver on black).
- Wood jobs look like a negative, even though they burn correctly.
Compare 'In LaserGRBL' with 'Looks like' above the preview.

[image:docs/negatives-explained.png]

# In LaserGRBL's picture import
Its invert (negative) button does the same as Negative here. Press it only when Negative would be on."""

LASERGRBL = """# Settings for '{name}'
In LaserGRBL: File > Open the picture, then {recipe}

# What LaserGRBL's settings mean
- Quality (lines/mm) = 1 divided by the row spacing. 10 lines/mm = 0.1 mm rows.
- S-MAX = the strongest power. S1000 = 100% on your U20 ($30=1000), so S500 = 50%.
- S-MIN = the weakest power. Grayscale only; keep 0 for dots.
- Laser mode M4 (dynamic): power follows the real speed, so row ends and corners don't over-burn.
- The loop counter next to LaserGRBL's run button repeats the whole job: those are extra passes (see 'Too light or too dark?').

# Running this app's files in LaserGRBL
- File > Open the '... - all passes.nc' file, or one pass file at a time if you want photo pauses.
- Don't import the PNG files and don't press invert: the conversion is already done.
- Put the head on the start point the job expects (step 3) and check the frame first.

# LaserGRBL's words and this app's words
- Line To Line Tracing (picture import) = rows across the whole picture, so shapes fill in. Every print style here works like this.
- 1:1 Dithering = dots. Same idea as Classic, Smooth, Crisp and Bright dots here.
- Vectorize = traces the EDGES of shapes, so they come out as outlines, never filled.
- Centerline = one line along the middle of each stroke. Same idea as Thin lines here.
- Quality (lines/mm) = row spacing. 10 lines/mm = 0.1 mm rows = 254 lines per inch.
- S-MAX = power. S600 = 60% on your U20.
- Loop counter = repeat passes.
- Frame = the perimeter check (here the head also flashes the 1% dot at each corner).
- Setting zero in LaserGRBL = 'Set start point here'. The head doesn't move; the spot under it becomes X0 Y0.
- Home / Global Home = never on this machine (no homing switches). This app refuses it.

# Mistakes from the Hot Wheels car
The yellow Mustang roof (stripes + horse, 82.55 x 26.5 mm) went wrong in LaserGRBL in these ways:
- Raster import (File > Open of a picture) burned the whole rectangle: the picture's background counted as something to burn. See 'Backgrounds & stickers'.
- Vectorize gave OUTLINES only. It traces the edges of shapes, so the stripes never filled in. For solid stripes use a raster (line-by-line) conversion of a picture whose background doesn't burn.
- Regenerating the job lost its placement: the stripes ended up off the car's centerline and at an angle. Re-check the position after every change.
- Frame only traces the outer box of the job. It can't show where the windows or the centerline are, so lines burned across the windshield and rear window. Check those points separately with the dot.
- 'Image Proportion' was unlocked, so changing the width didn't change the height to match. Keep it locked.
- The horse ended up too far forward, on the nose.

[image:assets/samples/hw-top.jpg]

# If the USB drops out
Jobs run from this app record exactly where the head stopped and resume safely. In LaserGRBL, don't use Resume or Home after a reconnect: it can jump to old coordinates (that burned the bed on the card)."""

PERIMETER = """# The start point
The start point (also called the origin, 0,0 or X0 Y0) is the spot the job is measured from, and where you put the laser dot before starting. In step 3 choose the lower-left corner, the centre, or 'A spot I pick' and click any spot on the picture: the corner of a stripe, the middle of a windshield's edge, anything you can find on the real piece. The red crosshair shows it. Move the head there with the dot on, then press 'Set start point here'. Nothing moves when you set it.

# The two crosshairs
- Red crosshair: the start point, where you put the dot on the real piece.
- Purple marker: where the controller THINKS the head is. When they sit on top of each other, the picture will land where you expect.
In step 5 you can line them up by clicking the preview:
- 'move the head there': the head moves to the spot you click, laser off.
- 'say the dot is here': look where the dot really is on your piece and click that spot on the picture. Nothing moves; the purple marker jumps there.

# Two kinds of moving
- Move the picture (step 3, and under the perimeter check; blue box in the preview): the picture shifts on the piece and the job is rebuilt. The machine doesn't move.
- Move the laser head (step 5, purple marker in the preview): the real head moves, laser off. The picture stays put.
- Move the picture with the head (tick it in step 5): the head moves and keeps its X/Y, so the whole picture shifts on the real piece with it, like sliding the piece under the laser. Run the perimeter check again afterwards.
The X/Y numbers in step 5 are where the controller THINKS the head is, measured from the start point. They only match the real spot after you set the start point.

# The perimeter check
The head moves to each corner of the burn area with the laser OFF, flashes the 1% positioning dot there (S10, 0.25 s bursts), then comes back to the start point.
- Before each flash it checks the machine is idle with zero output, and that the controller has 1% programmed while the laser is off.
- Each flash is sent with its own 'laser off' command attached.
- Off by a bit? Move the picture in 0.5-5 mm steps and check again.
- Works for any .nc file too: drop it on the Laser Perimeter Check desktop icon. It also tells you whether the file fills shapes in or only traces their outlines.
- Moving the picture or setting a new start point means a new perimeter check: the 'Ready to start?' list unticks it.

The dot is the real engraving laser at very low power, so still wear laser glasses.

# Curved or small pieces
The perimeter check, like LaserGRBL's Frame, only shows the outer box of the burn. On a toy car or anything with windows, edges or a centerline, also put the dot on those points before burning: on the Hot Wheels car the box looked right, but the stripes crossed the windows and missed the centerline.

[image:assets/samples/hw-setup.jpg]"""

DROPOUT = """# What happens
When the USB drops out, the controller restarts and forgets where the head is. The job record keeps the last command sent, and the head stops at the end of that command.

# Resume safely
1. Plug back in and connect. Unlock if asked. Never Home this machine: it has no homing switches.
2. Declare the stop point. This tells the controller where the head is; nothing moves.
3. Turn the 1% dot on. It should sit at the end of the last burned line; nudge if needed.
4. Resume. It continues with the very next command, so nothing burns twice.

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
- In LaserGRBL: if its preview shows a solid rectangle around the art, stop and fix the picture.

# How to fix it
1. Use a picture with a plain background: white when Negative is off, black when it's on. A photo-editor or 'remove background' tool, then fill the background with that colour.
2. Or flip Negative, if the art itself is drawn the other way round.
3. Check 'What burns' again: only the shapes should be coloured.

# Fills and outlines
A filled shape (a solid stripe) needs the laser to scan rows across it, which this app's styles and LaserGRBL's raster import do. LaserGRBL's Vectorize and Centerline only trace edges or middle lines, so shapes come out as outlines. That's what happened on the Hot Wheels car.
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
- '<name> - all passes.nc': everything in one file, for LaserGRBL.
- '1 LOOKS LIKE': the expected result. '2 LASER INPUT': black = laser fires. '3 IN LASERGRBL': its preview. '4 burn map': a colour per pass.
- README.txt explains the folder; photos\\ collects your photos after each pass.

# Pictures for .nc files in File Explorer
Windows only shows pictures for picture files. For .nc files it shows the icon of the program that opens them (LaserGRBL's 'LG'). install.ps1 adds a small preview add-on so Explorer draws what each .nc file will engrave; press F5 or reopen the folder after installing. uninstall.ps1 removes it.

# Your presets and settings
Saved presets: Documents\\Laser Photo Studio\\my-presets.json. Port and phone-photo folder: the Settings button.

# Sample photos
The photos under 'About this setting' come from the project's tests and finished pieces (the app's assets\\samples folder). Photos you add go to Documents\\Laser Photo Studio\\samples\\<setting>\\ and can be removed again in the photo viewer."""


def styles_text() -> str:
    out = []
    for s in STYLES.values():
        out += [f"# {s['name']}", s["what"], f"Why: {s['why']}", f"Best for: {s['best']}", ""]
    return "\n".join(out).strip()


def topics(mat) -> list:
    return [("Start here", START),
            ("Too light or too dark?", DARKNESS),
            ("Negatives & LaserGRBL", NEGATIVE),
            ("Print styles", styles_text()),
            ("Using LaserGRBL", LASERGRBL.format(name=mat.name, recipe=lasergrbl_recipe(mat))),
            ("Start point & perimeter check", PERIMETER),
            ("Backgrounds & stickers", BACKGROUNDS),
            ("USB dropouts", DROPOUT),
            ("Safety", SAFETY),
            ("Files & previews", FILES)]
