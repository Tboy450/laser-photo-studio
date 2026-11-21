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
