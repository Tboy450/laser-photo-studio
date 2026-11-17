# USB position memory and inspection controls — November 9, 2026

## Delivered behavior

The setup worker and detached print runner now keep a durable local record of the same job reference. It covers setting zero, applying alignment, completed inspection jogs, placement checks, interrupted engraving, normal print completion and the app's Disconnect button. A new connection does not replace the saved position with rebooted X0 Y0.

Beside **Start engraving** in Step 5:

- **Park left 3½ in** moves the physical head, with the laser off, to **X -88.9 mm, Y 0** in the current job frame. It is an absolute destination: clicking again does not add another 88.9 mm. It ignores the arrow-jog option that shifts engraving placement.
- **Return to zero** moves the physical head, with the laser off, to the same **X0 Y0**. Neither button establishes a new zero or moves the artwork. With a centered lid, this is the original lid center; with a corner-origin job, it remains that corner.
- If disconnected, either button connects and offers restoration of the saved setup/reference before carrying out the requested move. Confirm that the head and material have not moved since the displayed completed checkpoint. Cancellation does not send the move. The controls are unavailable during an active print or placement check.

The runner still closes its port after finishing so it does not monopolize COM4. It now persists the confirmed final position, work offset where reported, and job context before releasing it. The UI does not automatically reconnect or move merely because printing finished. Clicking an inspection button requests that reconnect/recovery/move sequence. App Disconnect preserves the journal too.

**Restore saved setup / position...** is also available separately under Connect. Restoration itself does not move the head. It restores the original picture, rotation/mirroring, physical dimensions, origin choice, image offsets, material/power/feed/style, tone controls, scan direction and no-burn masks without applying file DPI or refitting. A changed source-image hash is rejected. Previous placement-check confirmations are cleared.

## Local storage

Default Windows location:

```text
%LOCALAPPDATA%\Laser Photo Studio\Recovery\COM4.json
%LOCALAPPDATA%\Laser Photo Studio\Recovery\history\
```

The paths are under the same local data root as settings, not OneDrive. An explicit `LASER_PHOTO_STUDIO_DATA_DIR` override still applies. Demo mode uses a separate `demo-COM4.json`. Each newly established reference archives the previous record, including interrupted paths. Writes use a unique temporary file, flush/fsync and atomic replacement. Telemetry writes are throttled; the start of movement, completed idle checkpoints and disconnects are saved immediately.

Saved fields include source path and hash, exact setup, job folder, operation, last reported status, last confirmed idle status, attempted command, fully written command, separate motion commands, trace progress and reset/disconnect flags. Runner state additionally distinguishes written and acknowledged command indices. Machine/work positions and the work offset are recorded when supplied or derivable from the controller report; missing fields stay missing.

## Recovery limits

- A completed move is recorded only after an Idle/laser-off response with no pending acknowledgements. After an unplug at rest, the operator's confirmation that nothing physically moved allows the saved work position to be re-declared following a reset. This changes the controller reference without physically moving the head.
- A sent or acknowledged endpoint is not proof that motion reached it. A reset during a queued movement leaves an uncertain interval. The UI preserves that evidence and does not silently declare the last sent endpoint as the physical stop.
- For an interrupted check with a still-valid coordinate frame, fresh idle telemetry can be used after confirming no reset or physical movement. A changed or unavailable offset cannot prove that continuity.
- Jogging before restoring a lost reference invalidates the old idle checkpoint as the current head location. Its record remains available for investigation.
- This does not repair the USB cable/driver/controller cause of disconnects, add homing, or reconstruct unreported physical motion. Existing runs made before this update may lack the setup snapshot. Use their archived recovery evidence rather than claiming the new feature recorded them retroactively.
- External-file checks are recorded, but the full setup-restoration dialog currently handles app-created picture/grid jobs. It points to an external file for reopening rather than silently substituting a picture job.

## Verification and implementation

**77 tests passed, zero failures/errors/skips, in 74.122 seconds.** This includes the core planner, simulated runner, scan direction, placement UI, outline checks and 19 position-memory/inspection regressions. `git diff --check` also passed.

The historical regression log remains in the private project archive.

Tests cover completed-print persistence with a nonzero work offset; app Disconnect after inspection; park/return through the normal demo buttons; repeated park clicks; unchanged image geometry and job zero; controller reset after parking; interrupted trace evidence; no blind movement after reset during motion; partial writes; unchanged legacy job context; exact setup/mask restoration; changed source rejection; competing runner lock and final-save failures. All physical serial opens are forbidden during verification. No real laser was connected, moved or fired for this change.

Code: `lps/position_memory.py`, `lps/machine.py`, `lps/worker.py`, `lps/runner.py`, `lps/app_laser.py`, `lps/app.py`, recovery dialog/help, and `tests/test_position_memory.py`.

Updated source is used on the next normal app launch. The running application was not closed, reconfigured or restarted. The separate physical small-letter investigation remains unresolved; its new scan-direction option is diagnostic, not proof of a lettering fix.
