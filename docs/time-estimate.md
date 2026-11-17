# Stable planned-time estimate

The previous live remaining estimate divided elapsed time by estimated progress based on **command count**, then multiplied remaining planned time by that ratio (clamped to0.5–3). Short engraving segments and long laser-off moves have very different durations, so this was not a reliable speed measurement. Leaving running/paused also discarded the current pass's partial contribution, which could make the estimate jump upward by hours on long jobs.

The replacement uses the saved pass commands to establish a fixed planned-time budget for the selected run. Resume excludes earlier completed passes and the skipped command prefix, retaining the prefix coordinates for suffix-distance calculations; a resume lead is accounted separately. It follows the existing planner timing model and splits estimated engraving motion, laser-off motion, dwell and overhead. No laser commands are changed.

Remaining planned time counts down with active elapsed time. Feed holds and photo waits accumulate separately as paused time and do not consume the estimate. Displayed wall elapsed remains available in state.json. Completion is established by the existing runner/controller path, never by the countdown reaching zero. If time runs out before confirmed completion, the UI says **past planned time; completion still pending**. Existing percentage progress still represents streamed command progress, not independently measured executed motion.

This deliberately removes continuous command-count speed correction. It is a stable estimate, not a calibrated completion forecast: actual acceleration, buffering, feed behavior, pauses and parking may differ from the model. Category times are the current run's planned budget; they are not measured laser-on durations. Partial-move resume leads and unplanned overhead remain approximations. Existing timer histories remain unchanged; active/paused counters describe this runner invocation, not reconstructed earlier runs.

## Offline evidence

- Component totals match the existing planner for mixed powered/off moves and dwell commands.
- Synthetic long-job regression reproduces the old3600→7200-second remaining-time jump when transitioning to stopping; the new estimate does not change merely because phase or command density changes.
- Private saved slate trace replay:14,565 samples; old largest upward correction19.84seconds between adjacent samples, while the new countdown is nonincreasing. This trace reproduces oscillation, not the full reported hours-wide range. No private job/image/trace is bundled with this source change.
- Pause/photo-wait and resumed-prefix regressions run offline. No physical validation or active app installation is claimed.
