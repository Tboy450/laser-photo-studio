# Plan: tone layers for tin lids: gold + frost etch (2026-11-12)

> **Update, 2026-11-12 about 6:48 AM: the fast "charcoal" tone is soot.** On these reflective lids the fast tone
> (about 2200–4300 mm/min) is soot sitting on the surface. After wiping it's only a **light frosted etch that still
> looks like stainless**. The gold stays. Source: `pine salve - red hill\UPDATE-2026-11-12-soot-finding\`.
>
> - In this plan the fast tone is now called **"frost etch (soot until wiped)"**.
> - **Judge every result after wiping**, and say whether a photo is before or after.
> - A permanent dark tone on these lids is **unproven**. It needs more exposure: repeat passes, finer row pitch, or
>   wiping between passes. It can't come from a slower speed, because of the ~24 mm/min floor.
> - Idea, proposed only: soot as a temporary stencil for gold.
>
> The tone-layer feature itself doesn't change: tones are just presets, so their names and settings can follow the
> tests.

**Status:** a plan only. Nothing here is built yet. The user is printing, so **no app changes until the prints are
done.**

## The goal

- Gold and frost-etch **tint standards** (and a dark tone, if one proves permanent) for the Red Hill tin lids, so a design prints in those two tones the
  same way every time. No AI image tools in the loop.
- **A simple way in Laser Photo Studio to split one design into a gold layer and a frost-etch layer and burn one, then
  the other.** The order should be a one-click choice.

## What we know (from the lid tests, Nov 10–12)

### Speed sets the colour

On these lids, **speed sets the colour; power barely matters** between 70 and 100 %.

| Tone | Setting |
|---|---|
| Gold / rose-copper | about 80 % / 140 mm/min |
| Frost etch (soot until wiped; looked like charcoal before wiping) | about 80 % / 2200–4300 mm/min |

- Below about 24 mm/min the machine doesn't go any slower.
- Ladder squares don't predict colours on a real design: shapes and stroke width change the shade.
- **Thin fast-tone lettering is the weak point.** It's still missing detail after two passes, and after wiping the
  fast tone is only a light frost.

### Each tone is its own pass

Each tone must be **its own pass at its own speed**: one 1-bit mask per tone. This is how the Matthew lid
and the new Forest Products jobs were built. Today that needs a hand-written `prepare.py` plus a `.pyw` launcher.
That's what this plan replaces.

### Order test (prepared, not yet run)

`pine salve - red hill\tests\red-hill-forest-products-two-tone-2026-11-12\` has two jobs:
- gold first: gold 80 % / 140, then frost etch 80 % / 2200 (**ran 2026-11-12**: after wiping, the fast tone is a light frost);
- black first: the same two passes, other way round (**held** after the soot finding, until reviewed).

Both use the same two masks, left to right only, zero at the lid centre. Its result decides the **default order**.

### Material

The user thinks the lids are bare aluminium alloy. Gold and copper heat tints are typical of **tin-plated
steel**, not aluminium.

Quick check: **a fridge magnet sticks to tinplate (steel) and not to aluminium.** The answer matters for the preset
names and for what to buy next time. It doesn't change anything else in this plan.

---

## Phase 0: no code (now, while printing)

1. Run the gold-first / black-first pair. Photograph each lid:
   - after pass 1 and at the end;
   - one straight-on shot under one light;
   - one shot tilted about 30°;
   - a bare lid in the frame if possible.
2. Do the magnet test on a lid.
3. **Tone overlap test** (prepared: `pine salve - red hill\tests\tone-overlap-2026-11-12\`, about 40 min, one
   fresh lid).
   - It compares gap 0.2 mm, touching, 0.1 mm overlap and 0.3 mm overlap.
   - It tests **gold over the fast tone** (upper half) and **the fast tone over gold** (lower half). Set A also
     tests the soot-as-stencil idea: does soot from the fast pass change the gold burned over it?
   - **Held** after the soot finding, until reviewed. If it runs, photograph it before and after wiping.
   - It adds a half-overprinted square and 0.1–0.5 mm lines of one tone on a solid field of the other.
   - Results decide the layer feature's edge setting: gap, touch or overlap. If one tone reads well **on top of**
     the other, add an "on top" layer option: burn the field solid, then the detail over it, with no cut-out
     needed. That's simpler for drawings and keeps fine detail.
4. Run the lettering speed test when the user sends the image. This decides the fast-tone standard (2200 vs
   3000 vs bolder strokes).

## Phase 1: tone standards (small, low risk)

Every tone preset's note says **"judge after wiping"**. The preset preview colours come from photos taken after
wiping.

### Tone presets

Add **tone presets** for this lid stock. Each tone is a name, power, speed and preview colour:
- `Tin lid - Gold` 80 % / 140
- `Tin lid - Frost etch` 80 % / 2200: **soot until wiped; judge after wiping**
- `Tin lid - Dark`: **only if a test proves a permanent dark.** The research note
  (`pine salve - red hill\UPDATE-2026-11-12-soot-finding\RESEARCH-permanent-dark-2026-11-12.md`) says:
  - a bare lid is unlikely to go black under this diode;
  - more heat may reach a permanent purple or dark-blue temper colour.
- Idea only, untested: `Coating mark (spray / dry moly)`, a real black from a marking coating or black tins with the
  background ablated
- `Tin lid - Copper` kept for later

All marked **EXPERIMENTAL** until confirmed on two lids. Where:
- `presets.py` gets a `TONES` list (key, name, material key, power, feed, preview RGB, note).
- The preview colours come from photos of real design burns, not the ladder squares.

### Standard swatch job

Add a **standard swatch job**: about 5 min, one tiny piece of real design in each tone. It includes:
- a word at the smallest lettering size we use;
- a few rays;
- a 3 mm solid.

Burn it on the edge or underside of a lid from each new batch of lids. If the swatch matches the reference photo,
the presets hold. If not, adjust before burning good lids. Built with `ladder.py`'s placement helpers, zero at the
lid centre, with keep-clear spots.

## Phase 2: tone layers in the app (the main feature)

### What the user sees (one new style, "Tone layers")

1. **Step 1 – Picture.** Open the design as **one flat-colour picture**:
   - fast-tone (frost etch) parts black;
   - gold parts a gold or yellow colour;
   - background white, meaning bare tin.

   Any drawing program works (Paint, Inkscape, Canva). Draw with three colours: no AI, no tracing.

   Also allowed: **two separate black-and-white pictures** (one per tone, same size), via "Add layer picture…".

2. **Step 2 – Material / style: "Tone layers".** The app finds the colours in the picture and lists them as layers:

   ```
   Layer        Picture colour   Burns as              Order
   ■ Frost      black            Tin - Frost etch 80/2200 1  [↑][↓]
   ■ Gold       yellow           Tin - Gold 80/140         2  [↑][↓]
   □ Bare       white            (not burned)
   [Swap order]   Silver gap between tones: [0.25] mm   [x] One tone per shape
   ```

   - Each colour gets a tone preset from a drop-down. A colour can also be marked "not burned".
   - **Eyedropper:** click anywhere in the picture to add that colour as a layer. This is for mockups that aren't
     perfectly flat. The nearest key colour wins, with a tolerance slider. There's no hue maths for the user to set.
   - **Swap order** is one click. After the gold-first / black-first test, the winner becomes the default.

3. **Preview.**
   - "What burns" shows each layer in its tone colour.
   - The burn map shows one colour per pass.
   - "Show one layer" buttons isolate gold or frost etch, so the user can check each one before burning.
   - Thin strokes in the fast-tone layer get a warning badge ("below 0.3 mm: may come out faint") with a
     **"Make strokes bolder (+0.05 mm)"** option, depending on the lettering test.

4. **Step 5 – Burn.**
   - The passes run in the listed order from one Start: one connection, one zero (the lid centre).
   - *Pause after each pass* defaults to on for tone layers, so the lid can cool and be photographed.
   - The step 5 header names the passes: "Pass 1 of 2: FROST ETCH 80 % / 2200 · Pass 2 of 2: GOLD 80 % / 140".

5. **Saving.** The job folder keeps:
   - the original picture;
   - each layer's mask PNG;
   - a `layers.json` (colours, presets, order, gap).

   So **Open saved job…** (Phase 3) reopens it exactly, and a re-run with the order swapped is one click.

### How it works

- **New `lps/tonelayers.py`:**
  - `find_colours(picture, max_colours=6)`: the main flat colours, ignoring anti-alias fringe pixels.
  - `split(picture, keys, tolerance)`: one boolean mask per layer (nearest key colour per pixel).
  - `one_tone_per_shape(masks)`: the majority tone per connected shape, from `make_matthew.py`.
  - `silver_gap(masks, mm, pitch)`: erodes the lower-priority tone next to the other, from `make_matthew.py` and
    `new_design.py`.
  - `bolden(mask, mm)`.

  All plain numpy/PIL, which the app already uses (`imaging.label_components`).
- **`planner.plan_cells` gets a `"tonelayers"` branch:** one `PassPlan` per layer, in order. Each has
  `cells = mask & allowed` at that tone's power and `feed` = that tone's speed. `PassPlan` already has a per-pass
  `feed`, and `verify` already accepts several S/F values. This is exactly what the Red Hill `prepare.py` scripts do
  today, so they become the test oracle: the same masks must give identical commands.
- **Material** gains `layers` (a list of colour → tone key, plus the order), `tone_gap_mm`, `one_per_shape` and
  `bolden_mm`. Old presets load unchanged (defaults empty).
- **Left to right only** for tin (`scan_direction='forward'`), the user's rule, "for now".

### Tests (targeted)

- `split` on a 3-colour test image: exact masks; fringe pixels go to the nearest key colour.
- Silver gap: no cell in two layers; the gap is the asked-for width.
- The Forest Products masks run through `"tonelayers"` give the same pass commands as its `prepare.py`
  (gold-first and black-first).
- Swap order changes only the pass order.
- An old preset file still loads.

## Phase 3: from the lid tests session's handoff

From `pine salve - red hill\HANDOFF-TO-LASER-PHOTO-STUDIO-2026-11-12.md`:

1. **Open saved job…** (step 1).
   - Load a job folder or `job.json` that Studio made.
   - Check each pass file's sha256.
   - Show the preview and enable Start, with the normal pauses and recovery.
   - When the user opens Studio's own `all passes.nc` and a matching `job.json` sits beside it, offer to load the job
     instead of check mode.

   This **retires the `.pyw` launchers**, which don't open on this PC: there's no `.pyw` file association.
2. **Until then:** `install.ps1` makes `.lnk` shortcuts for launchers, or registers `.pyw` with the Store
   `pythonw.exe`.
3. **Check mode:** grey out the material, size and placement fields, labelled "not used: the G-code file sets these".
   The "open it in LaserGRBL" message should add that reconnecting restarts this controller, so zero must be set
   again.
4. **`jobs.save_job`:** write to a temp file, then rename. Give a clear message when a pass file is open in another
   program (it raised `OSError 22`).

## Phase 4: speed and connection

### Skip long gaps at laser-off speed

Today a row's unburned stretch between two burned parts is crossed at the **burn speed**. At 140 mm/min that's what
makes the gold pass 81 min, and a gold outer ring would make it 131 min. Change `raster_commands`:
- when a gap is longer than 2 run-ups plus about 1 mm, end the segment with a run-out;
- cross the gap at `row_feed` with the laser off;
- run in again at burn speed before the next segment.

With M4 dynamic power this is safe. Expect the gold pass to drop to roughly a third of the time; check it with the
estimate. `verify` must still pass, and the simulated burn must match cell for cell.

### Keep one COM4 connection

Keep one COM4 connection open through passes, parking and Continue. Reconnecting restarts the controller and loses
zero. This is already on the update list.

## Order of work, and what I'd do first

1. Phase 0 now (the user's prints, magnet test, lettering test).
2. Phase 1, tone presets and the swatch: small, and useful right away.
3. Phase 2, tone layers: the main feature, about a day of careful work with the tests above.
4. Phase 3, item 1 (Open saved job) right after, because it removes the launcher problem.
5. Phase 4 when there's time. The gap skip is the biggest time saver for slow gold passes.

## Rules

- Never change the app while the user is mid-print.
- Never send anything to COM4; the user runs every job.
- Job zero = the lid centre.
- Classic dots, not Black & white.
- Left to right only on tin.
- No OneDrive.
