# Optional faster blank gaps in scan-line fills

Problem: row return speed previously applied only between scan rows. Large internal S0 gaps, especially inside a circular border, crossed at the engraving feed. A sparse round logo could therefore spend most of its time moving slowly with the laser off.

Material > Adjust settings now offers **Faster blank gaps inside scan lines (experimental)**. It is off by default and saved with the material recipe/job. Enabled scan-line passes use the return speed for internal S0 gaps at least 1 mm long, only when that speed is faster than engraving. Powered command endpoints, feeds, powers and order remain identical. Short gaps and row run-ups/out remain unchanged. This works with forward and alternating rows, and per-row test feeds. Thin-feature, crawl and dwell generators are unchanged. No vector run mode was added.

The ordinary replay verifier now also rejects a powered stroke at a travel feed even when that feed appears in the allowed travel-speed set. Native source-backed import regenerates the exact gap option; old jobs without the field default off. Saved text/headers state whether the option is enabled. No preset is automatically opted in.

On the prepared round Pine Salve Products artwork (80%, 0.1 mm pitch, forward, 3000 mm/min return), changing 2,279 internal S0 feeds reduces the modeled times from 353.8/131.1/94.0 minutes at 50/140/200 mm/min to 151.6/61.1/46.0. These are software estimates, not measured finish or throughput. M4 and the machine's acceleration/planning still govern physical speed at transitions; the optional change requires a material trial. It does not establish the new black coating's colour response.

Validation: 141 full-suite tests passed in 117.623 s after planner/material/verifier/UI changes. Then 10 focused tests passed in 3.865 s after the saved-description update and additional UI toggle test. Coverage includes backwards defaults, both scan directions, only-S0 feed changes, unchanged small gaps/run-ups, slower return feed, rejection of powered travel feed, exact editable save/reopen, and visible toggle restoring the original job. Tests use isolated data and no real serial access.

Source update, protected runtime installation, already-running Studio process and physical trial are separate states. Installing source on disk does not hot-patch an existing window. The active application and hardware were not controlled during this work.
