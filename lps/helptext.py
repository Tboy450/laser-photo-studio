"""Guide text shown by the Guide button. Plain words, short topics.
Markup: '# ' heading, '- ' bullet, '1. ' numbered step, '[image:<path in app folder>]', blank line = gap."""
from __future__ import annotations

from .presets import STYLES, lasergrbl_recipe

START = """# Five steps
1. Picture - open a photo, drawing or logo (phone HEIC photos work). Turn it if it's sideways.
2. Material - pick your material. Green = proven on your U20. Yellow = a starting point from other 20 W lasers: run a test grid first. Proven settings show photos of their test ladders and charts, and of finished pieces made with them; click a photo to enlarge it.
3. Size - enter the piece size, where the origin is (lower-left corner or centre) and any no-burn zones like twine holes.
4. Check - adjust the picture while watching the preview. The app replays every command before anything can run.
5. Laser - connect, set the origin, run the perimeter check with the 1% dot, then Start.

# The preview buttons
- Looks like: roughly how the finished piece will look on the material.
- What burns: each layer in its own colour.
- In LaserGRBL: how LaserGRBL's preview will draw the file.
- Picture: the adjusted picture before it becomes laser moves.

# Good habits
- New material? Burn a test grid first (step 2) and save the best patch as your own preset.
- Add your test and result photos to the setting ('Add my photo...' in step 2), so next time you can see what each setting did.
- Always run the perimeter check before burning.
- Take a photo after each layer; the app pauses for it and files the photos in order."""

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
- File > Open the '... - all passes.nc' file, or one layer file at a time if you want photo pauses.
- Don't import the PNG files and don't press invert: the conversion is already done.
- Put the head on the origin the job expects (step 3) and check the frame first.

# If the USB drops out
Jobs run from this app record exactly where the head stopped and resume safely. In LaserGRBL, don't use Resume or Home after a reconnect: it can jump to old coordinates (that burned the bed on the card)."""

PERIMETER = """# The origin
The origin (X0 Y0) is the spot the job is measured from: the lower-left corner or the centre of the piece (step 3). Jog the head there with the dot on, then press 'Set origin here'. Nothing moves when you set it.

# 2 in reflective tin workpiece
The preset 'Reflective tin lid 2 in (45.72 mm face)' describes the geometry only:
- Outside diameter: 50.8 mm.
- Center origin: X0 Y0 is the physical centre of the lid.
- 2.54 mm margin on each side leaves a 45.72 mm circular artwork area.

This is not a proven engraving setting. The Red Hill tin marks are still being tested, so choose a separate material/style setting and keep its evidence status honest.

# Aligning a tin in a jig
1. Seat the lid fully in its pocket and make sure the jig itself is registered to the machine bed.
2. Use the low-power pointer to locate the actual centre of the lid (or a measured jig reference that has been checked against that centre).
3. Jog the head to that point and press 'Set origin here' in step 5. This sets the work coordinate; it does not move the head.
4. Run the perimeter check. It checks the planned artwork footprint relative to the origin; it cannot detect a lid that is sitting off-centre in its pocket.

# The perimeter check
The head moves to each corner of the burn area with the laser OFF, flashes the 1% positioning dot there (S10, 0.25 s bursts), then comes back to the origin.
- Before each flash it checks the machine is idle with zero output, and that the controller has 1% programmed while the laser is off.
- Each flash is sent with its own 'laser off' command attached.
- Off by a bit? Nudge the art in 0.5-5 mm steps and check again.
- Works for any .nc file too: drop it on the Laser Perimeter Check desktop icon.

The dot is the real engraving laser at very low power, so still wear laser glasses."""

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

WOOD_SURFACE = """# Read the wood surface
A wood image is not a flat, uniform sheet:
- Grain, knots and uneven coloration can change how the finished mark reads.
- Ordered Grid dots place marks on a regular pattern; they can make a test easier to compare across grain, but they do not correct a ridge or a change in surface height.
- A raised or warped area changes the distance from the lens to the wood. Check that the board is supported and the focus remains consistent across the image area.
- Use a small offcut or test area when changing species, surface preparation or image style.

# Stain and finish records
There is no universal stain-before or stain-after setting in the app. Record the finish product, whether it was applied before or after the burn, and its dry/cure state. Compare the result on matching offcuts before choosing a repeatable sequence. A finish that changes contrast is not automatically a better or more durable finish.

# Surface marks
The diode process shown in these examples makes a surface burn. It does not create a routed groove or carved relief. Record appearance, residue and finish separately from physical depth."""


SAFETY = """- Stay with the machine the whole time. Wood, cardboard and leather can catch fire.
- Wear laser safety glasses made for your laser's wavelength, also for the 1% dot.
- Ventilate: smoke from wood, leather and acrylic is unhealthy.
- Never laser PVC, vinyl or faux leather: they release chlorine gas.
- Air assist gives cleaner marks and less fire risk.
- Etched jar lids are decorative only: heat goes through the coating.
- Never use Home on this machine; it has no homing switches."""

FILES = """# Where jobs go
Documents\\Laser Photo Studio\\Jobs\\<date>_<name>\\ (on this PC that's inside OneDrive\\Documents).
- '01 Layer 1.nc', '02 ...': one file per layer, in order.
- '<name> - all passes.nc': everything in one file, for LaserGRBL.
- '1 LOOKS LIKE': the expected result. '2 LASER INPUT': black = laser fires. '3 IN LASERGRBL': its preview. '4 burn map': a colour per layer.
- README.txt explains the folder; photos\\ collects your layer photos.

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
            ("Wood grain & finishing", WOOD_SURFACE),
            ("Using LaserGRBL", LASERGRBL.format(name=mat.name, recipe=lasergrbl_recipe(mat))),
            ("Origin & perimeter check", PERIMETER),
            ("USB dropouts", DROPOUT),
            ("Safety", SAFETY),
            ("Files & previews", FILES)]
