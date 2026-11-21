# Tin laser results: corrected attribution (2026-11-21)

**Status:** operator correction / historical provenance. **Not a new machine test**, preset, or authorization to send laser commands. This file supersedes mistaken descriptions; preserve original photos and previously recorded job metadata separately.

## Operator-confirmed corrections

- **Lighter copper on tins:** **100% power, feed 140**, with historical operator-reported **0.15 mm raster line spacing**, left-to-right travel and **6000 rewind**. Record as *TIN — LIGHT COPPER (operator-reported)*, **not** stainless/silver, coating removal, dark soot, or an untested silver recipe. Units: the GUI's feed is normally mm/min; verify whether the user's original "140" corresponds to that UI field from actual saved job. Do not edit an installed preset blindly.
- **95% / 300:** Prior assistant incorrectly said this **blistered** a metal lid. The operator explicitly disputed this on Nov 21, 2026. **No blistering outcome is established for this setting.** Do not use the old claim as a safety result or silver recipe.
- **Twice-painted gloss tin:** Operator says **this was the only blistered lid** and **it was never run under the laser**. It is a separate non-laser coating incident; do not attribute it to a laser test.
- **Other burn-through lid:** exact settings are **unrecovered**. Do not infer 95%/300, 100%/140, or any other feed/power from the appearance alone.

## What is still unknown for the copper/silver two-tone tin project

- No confirmed **silver/stainless-like** exposed-metal engraving recipe on the current painted tin stock.
- No verified **dark soot on bare metal, wipe-clean** settings retrieved from an actual job record and after-wipe photo.
- The black paint/coating, metal substrate and cleaning chemistry on the target lids have not been identified conclusively.
- Prior 50%/2500 / 0.10 mm **bright silver** test was on **black anodized aluminum cards**, not proof of paint removal from a steel or aluminum tin.
- The old 100%/2500 / 0.10 mm frosted raster was an excessive-coverage **coated steel lid photo** effect that merged fine detail; it does not establish exposed stainless.

## Action for Studio owner

1. Search saved local .nc, job.json and photo labels for the actual **bright metal** / **dark soot that wiped off** result. Match material, job name, date, **before/after-wipe** photos and settings before calling any setting PROVEN.
2. Preserve the existing **LIGHT COPPER 100% at 140** result unchanged.
3. If testing silver, create a distinct **TIN — SILVER / PAINT-REMOVAL (EXPERIMENTAL)** entry and use scrap coupons with isolated small swatches, machine-off G-code simulation and verified ventilation. Don't run gift tins until calibration.
4. Do not hardcode the disproved "95%/300 blistered" caption in samples or handoffs again. The prior source catalog used that language and is corrected in this PR.
5. Record unit labels and provenance; note ambiguous or unretrieved tests as *unknown*, not *failed* or *successful*.

Related private cross-session master handoff: https://github.com/Tboy450/session-handoff-hub/pull/12

## Finish and speed interpretation — additional operator correction (2026-11-21)

- **80% power at 140 mm/min** is the **rose-brass/gold-to-rose copper candidate**, supported by a historical test recollection but not yet linked to a definitive dated job file and after-wipe photo. The operator recalled this on Nov 21 and asked to check it; earlier records say 80%/140 yielded copper-brown and gold-through-rose colors in differing tests.
- **100% power at 140 mm/min** is the operator-confirmed **lighter copper** engraving result, with 0.15 mm pitch, left-to-right and 6000 rewind as its historical run context.
- **Below 140 mm/min**, the operator **likes** the deeper/darker copper tone. The objection is **excessive production time**, NOT that the color is undesirable or too dark. Keep slower speeds as a possible aesthetic reference, while prioritizing 140 mm/min or faster for production-efficiency trials.
- A **dark/soot-like appearance immediately after lasering is not a reason to reject a SILVER candidate**. The operator wants settings where the soot **wipes off** to leave **frosted etched stainless/exposed-metal appearance**. Judge after wiping; record before/after results. Exact silver power/feed remains unverified on current lids.
- This replaces the prior, incorrect 'dark copper is too dark' wording. No physical new test was performed in this chat.

## RECONCILIATION — original wipe-clean frosted result FOUND (Nov 21 archive recovery)

**Historical physical test now identified — S9 / HIST-001, Nov 12, 2026, Forest Products gold-first lid.** Do not keep telling the operator the soot/wipe-to-frosted setting was never recorded. The original private 2026-11-17 records-reading-key archive contains these entries:

- `reading-guides/2026-11-17/red-hill/records/RUN-EVIDENCE-REGISTER-2026-11-17.md` **HIST-001**: **Gold first at 80% power / 140 mm/min**, followed by **fast dark/charcoal tone 80% power / 2200 mm/min**. Actual gold-first job ran about **03:58–05:33 on Nov 12** (~95 minute wall window); planner about **5738 seconds**. **After wiping, the dark soot went away and a light frosted etch remained; the gold stayed.** This is a physical observation on *that* tin finish/material, not a claim that a different painted tin at 80/2200 is already proven.
- `reading-guides/2026-11-17/red-hill/records/HANDOFF-INDEX.md`: `UPDATE-2026-11-12-soot-finding/` has source video `gold-first-lid-after-wiping-1000048346.mp4` (also copied into private project-videos), and the `tests/red-hill-forest-products-two-tone-2026-11-12/` folder records the **gold-first run** and its **unrun black-first rebuild**. Ordering matters: Nov 13 separate combo test says soot before gold resists the gold; gold-first survives.
- `reading-guides/2026-11-17/red-hill/tests/fabrication-reading-key-2026-11-17/README.md`: physical sample **S9** documented; separate proposed strips labelled `SOOT` = **80% / 2200**, `ROSE` = **80% / 140**, `SLOW` = **100% / 33**. Those *strip labels* were prepared references, not verified physical strips; physical S9 and HIST-001 are the independent observed evidence.
- `reading-guides/2026-11-17/red-hill/private/TIN-FINISH-COMPARISON-2026-11-17.md` independently records that wiping removed soot while gold remained.

**Corrected process evidence:** the desired silver-looking / frosted after-wipe result is **80% at 2200 mm/min** on the Nov 12 lid. Do not substitute assistant-suggested 100%/450, 100%/500 or 100%/2500 as if they were the identified old run. 80%/140 is the operator's rose-brass/gold reference. **Newer 100% at approximately 480–500 mm/min has now been physically reported to produce light gold-copper** on the current tin stock, not silver. The current stock may differ; verify exact material and cleaning before promoting the historical result to its active preset.

**Provenance:** the private user-connected Google Drive archive `PRIVATE - Record Reading Keys and Toggle Guides - 2026-11-17.zip`, originally preserved as a 78-entry, hash-verified records bundle: https://drive.google.com/file/d/1jOo2zEugCG5weaET_APKavVYuomB7btV/view . Records accessed read-only; do not copy private video, client data or raw chat transcripts into public Studio source.

## Current Red Hill tin two-tone pass and lid-lettering work order (operator update, 2026-11-21)

### Frosted stainless / wiped-soot mask — 80% power, 1800–2200 mm/min

- **Operator-selected working speed band:** **80% power, 1800–2200 mm/min** for the separately registered **stainless-looking / frosted-after-wipe mask**. Do not substitute the copper recipe or assume temporary dark soot means a bad result.
- **Historical confirmed endpoint:** **80% / 2200 mm/min**, Nov 12 S9/HIST-001 physical result. Gold-first followed by a faster dark/soot pass; wiping cleared soot to **light frosted metal**, with gold remaining. Preserve **gold / rose-brass at 80% / 140 mm/min** as the other color/pass.
- **1800 mm/min is an operator-selected candidate lower endpoint, not independently proven to achieve stainless on current lid stock**; treat the entire span as an operator-approved trial/working band while explicitly labelling 2200 as historical physical evidence. Apply the paired mask only after correct image registration; finish is judged *after wiping*.
- The **1800–2200 value in this section is the ENGRAVING FEED for the silver/soot mask**, not the separate experimental **blank travel/rewind speed** described in PR #11. Keep these settings in independent fields. Do not alter other proven presets or automatically trigger machine motion.

### Typography and circular coverage — requested edit to Red Hill lid artwork

- **Make the existing RED HILL / FOREST PRODUCTS / PINE SALVE lid lettering visibly larger and/or thicker**, and where possible scale the complete graphic to **occupy more of the measured usable flat lid face**, reducing the apparent margin and sensitivity to a slightly off-center position.
- **Preserve original logo structure, split shaded two-tone regions, wording approved for the actual artwork, and circular layout**; no bubble letters, thick outer-border/half-filled headline substitutes, or blanket rectangular background burns. Do not accidentally swap lettering or brand words between different Red Hill art versions; `FOREST PRODUCTS` and `PINE SALVE` may be separated in the current requested revision.
- Prior operator note: **increase narrow gaps/negative spaces among the FOREST PRODUCTS letters and around the A/P transition**, so letters survive on the physical lid. Thicken or enlarge **stems and counters** without closing inner holes, gaps, or nearby lines; maintain the 0.15 mm raster baseline and provide 0.10 mm alternate only if actually warranted by detail/scan-line comparison.
- The exact engraved outer diameter, true lid center and safe margin **must use the actual measured lid**, not be guessed from a nominal 2-in lid. Aim for a visually fuller lid while leaving **a defined safe unburned ring** and no crop/run-off at the rim. Do not use enlarged art as a substitute for correct jig centering; allow a final registered trace.
- **Deliverables for artwork owner:** revised **flat B/W burn-mask PNG** at measured art size for each pass, high-resolution preview, two-tone alignment proof and a side-by-side comparison against the current smaller/thinner version, with wording, dimensions, orientation and safe face noted. This is a change request only, **not a claim that images were edited or tested**.

**Owner split:** Studio PR #10 documents material/color history and the artwork update requirement. Studio PR #11 owns adaptive *travel* engineering (separate feed). The actual art files and private project photos belong in restricted Google Drive; no customer media should be committed to this public repository.
