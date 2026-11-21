"""Guide text shown by the Guide button. Plain words, short topics.
Markup: '# ' heading, '- ' bullet, '1. ' numbered step, '[image:<path in app folder>]', blank line = gap."""
from __future__ import annotations

from .presets import STYLES

START = """# Five steps
1. Picture - open a photo, drawing or logo (phone HEIC photos work). Turn it if it's sideways.
2. Material - pick your material. Green = proven on your U20. Yellow = a starting point from other 20 W lasers: run a test grid first. Proven settings show photos of their test ladders and charts, and of finished pieces made with them; click a photo to enlarge it.
3. Size - enter the piece size, where the origin is (lower-left corner or centre) and any no-burn zones like twine holes.
4. Check - adjust the picture while watching the preview. The app replays every command before anything can run.
5. Laser - connect, set the origin, run the perimeter check with the 1% dot, then Start.

# The preview buttons
- Looks like: roughly how the finished piece will look on the material.
- What burns: each layer in its own colour.
- Toolpath: planned laser-powered marks on a dark background, brighter for higher commanded power; not a live motion trace.
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

PERIMETER = """# The origin
The origin (X0 Y0) is the spot the job is measured from: the lower-left corner or the centre of the piece (step 3). Jog the head there with the dot on, then press 'Set origin here'. Nothing moves when you set it.

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
- '<name> - all passes.nc': everything in one G-code file, without photo pauses.
- '1 LOOKS LIKE': the expected result. '2 LASER INPUT': black = laser fires.
- '3 TOOLPATH': simulated powered marks, not head movement. '4 burn map': a colour per layer.
- README.txt explains the folder; photos\\ collects your layer photos.

# Pictures for .nc files in File Explorer
Windows typically shows a generic icon for G-code. install.ps1 adds a read-only thumbnail preview for compatible .nc files; press F5 or reopen the folder after installing. uninstall.ps1 removes it.

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
            ("Negative & previews", NEGATIVE),
            ("Print styles", styles_text()),
            ("G-code & machine settings", GCODE),
            ("Origin & perimeter check", PERIMETER),
            ("USB dropouts", DROPOUT),
            ("Safety", SAFETY),
            ("Files & previews", FILES)]
