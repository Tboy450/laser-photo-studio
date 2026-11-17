# Ongoing learning into Laser Photo Studio

Standing owner instruction, November 15, 2026: keep applying verified project learning to the existing Samples, Guide and justified features, cleanly and consistently. Studio owns app work. Fabrication supplies technical test records; records owns private provenance/corrections; the website owner handles approved public presentation; Sessions manager routes material updates.

## Intake and implementation order

1. Read the latest source handoff and the actual saved job/photo/result where available. Preserve the source ID and distinguish logged commands, operator testimony, timing inference and independent measurements. Resolve corrections explicitly; do not silently substitute a candidate job for a reported event.
2. Attach appropriate evidence to the **existing sample record** (`assets/samples/index.json` for built-ins; the existing local per-preset `photos.json` for user photos). Use `tools/make_samples.py` as the reproducible built-in source. Do not create a competing material-results database. Existing captions remain readable; missing metadata means unknown.
3. Record source/job/photo, actual stock/supplier/finish and sanding/coating, focus, power/controller scale, commanded feed with units, measured/inferred motion and method, raster pitch or N/A, mode/style, pass order, dwell and result/cleanup. Never borrow the current preset's values to fill an old photo's unknown fields. Different stock may be shown as a comparison under a preset, but must not be presented as proving that recipe.
4. Use Proposed, Prepared - not run, Operator report, Physical test or Repeated physical tests as appropriate. Keep the result text and limitations specific. A metadata selection does not certify a process or promote a preset.
5. Add concise Guide corrections or product guidance. Change a feature only when the observed issue supports it; preserve a stated backlog for unvalidated ideas.
6. Keep private SMS/client/formula material out of app samples. Retain raw provenance privately; include only technical facts needed for the example. Public website publication is separate approval/work.
7. Before installing changes, check the actual app/run state and current Git HEAD/changes. If idle cannot be established, work in an isolated candidate. Preserve user changes and pending patches. Test affected behavior with serial access forbidden. No source replacement/restart during a job.
8. Report exact changed files, tests, evidence limits, and whether staged, installed, committed or published. Route material corrections to the appropriate owner through the source handoff/manager; do not infer permission to message or publish from a cross-chat receipt.

## Current reviewed intake â€” November 15

- Initial penetration sequence: retrospective operator linkage to tin penetration and 56 damaged book pages; commands checked in original October 26 pulse/vector history. Exact perforating segment and physical stock/focus remain unknown. No raster DPI. This supersedes the earlier dense-DBZ-only candidate attribution.
- November 12 combo pass 6: saved M3/G4 stationary exposures, not a stopped-M4 job. Weak pinpoint result does not establish a durable dark marking recipe. Surface/coating and cleanup observations matter.
- Prior Red Hill raster pitch was about 0.10 mm / 254 lines per inch. This is scan-row spacing, not visible stripe separation. DPI is inapplicable to single stationary dots and vector-only lines.
- November 13 used-lid speed photo: physical sample with recorded commands and timing/telemetry-based inference near 23.6 mm/min. No independent motion measurement or firmware root cause established. Wipe state, exact coating/thickness and focus are unknown for the sample record.
- Seven DPI bands: prepared, physically untested. Three vertical marks through the new sanded patch: separate proposed surface comparison, not run. Dot test follows the line-test result.
- Crawl exists locally at 053400f and passed offline tests; physical validation remains absent here. Do not rebuild it merely because an older note calls it proposed.

## Backlog, not implemented or validated by this update

- Apply the reviewed PR1 tin50 patch only after checking idle state and HEAD. It remains geometry only. This learning candidate is independent of that unapplied patch.
- Matched before/after wiping photos and controlled sanding/focus comparisons, supplied by fabrication after real tests.
- Durable dark tone/coating claims, firmware root-cause diagnosis, independently measured motion and physical crawl quality.
- Structured per-job machine-profile/focus linkage and optional trusted saved-job metadata import. Current sample fields are manually entered; no automatic claim extraction from images or messages.
- Larger evidence histories/multiple settings per photo and publication review tools if later usage warrants them. The present fields can document ranges and ordered passes as explicit text.

Keep this file and the app Guide synchronized when verified outcomes change. Preserve historical evidence and mark superseded interpretations, rather than rewriting history as a new successful physical test.

