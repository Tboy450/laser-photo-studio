# Perimeter check and head marker follow-up

During the perimeter check, the machine moves while the head marker stays in place on screen. Check for the same behavior during engraving. Use the controller's reported work coordinates to move the head marker during both operations. In demo mode, use the simulated position. The start point crosshair should stay at the set origin. If live position updates stop, indicate that the marker shows the last reported position.

## Outline check freeze and disconnect

The current outline check emits a `tracing` progress event that the UI handler does not recognize. This was reproduced offline. The exception prevents the next UI event poll from being scheduled, so the head marker can freeze and the UI misses the completion or disconnect notification. The next perimeter check can then be blocked by a stale running flag.

Handle trace progress and keep polling after an unexpected event. Publish head position while travelling between shapes and returning to start. Show **Stopping check** and **Disconnecting** while the worker finishes, and clear the old check state when the worker disconnects. Re-enable the check after a normal finish or cancellation. If an engraving is running in the background, explain that its Stop control owns that job. If the displayed head is outside the grid, show whether its coordinates are current and whether the job start is set before treating that marker as an alignment reference.

## Preview markers and click controls

- Label the red crosshair **Job start (X0 Y0)** and the purple circled marker **Laser head**. The start crosshair shows the job origin. The head marker shows the controller's reported head position.
- Rename **Move the head there** to **Jog physical head to clicked point**. Selecting the option arms the next preview click. Require a valid alignment before jogging, including after a reconnect or controller reset. Use absolute millimeter coordinates in the job's work frame. The click moves the real head with the laser off, and the head marker follows its reported position.
- Split **Say the dot is here** into **Mark observed dot** and **Apply alignment**. Marking adds a temporary preview marker for the physical dot. Applying alignment shows the proposed shift of X0 Y0 on the piece before writing the controller's work offset. The head stays still during both steps. Clear the previous perimeter check after an offset change.
- Make shifting the artwork on the physical piece an explicit action. Keep **Move the picture with the head** separate from normal jogging and identify it as a placement shift, since it moves the head and changes the controller's work offset to follow it.
- Keep **Center of piece**, **Lower-left corner**, and **A spot I pick** visibly tied to Step 3. Neither Step 5 click mode changes this selection. **Set start point here** assigns X0 Y0 to the current physical head location.
- Give **Piece center** and **Image center** separate labels when they differ. Image center means the center of the placed image box. Show one combined label when the centers coincide, and combine it with the job-start label when all three coincide. For the centered Red Hill lid, the piece center, image center, and job start should all line up.

## Setup order for a centered lid

1. **Place the artwork.** Confirm the size and choose the center of the piece as the job start. Center the artwork on that point. Show one fixed target labelled **Center and job start** and a separate moving **Laser head** marker. Label the markers in the preview so they can be distinguished by shape and text.
2. **Align the laser.** Use the jog arrows to put the dot over the physical center. Keep **Move the picture with the head** off. Turn off the dot and select **Set start point here** to register that location as X0 Y0. Show **Start point set** beside the target.
3. **Check the placement.** Choose the perimeter check that answers the setup question. Use the image boundary to verify the centered lid fit and the total travel boundary to check clearance where needed. Mark the relevant check complete after it finishes for this setup.
4. **Start.** Keep the setup state visible next to Start. If the controller resets or alignment is lost, return to the alignment step. If the layout or offset changes, show which check needs to be repeated.

Keep the observed dot and alignment adjustment tools under **Adjust alignment** for jobs that need an off-center reference. Show separate piece and image center labels on demand when they differ.

## Perimeter buttons

Group the check buttons together. Show the path each button will check in the preview.

| Button | Path to check |
| --- | --- |
| Total travel perimeter | Frame the full programmed travel envelope, including laser-off run-ups and other travel that extends beyond the art. |
| Total travel perimeter (1%) | Same full travel rectangle with a 1% visible beam along its edges. Approach and return to zero remain laser off. This is not the round lid or image outline; it may extend past the piece. |
| Image perimeter | Frame the image's full placement box or its selected general shape, such as a circle. Include blank space inside that boundary. |
| Sticker outline | Trace the outside silhouette of the visible artwork, following its shape and leaving interior holes and strokes out of this check. |
| Full burn trace | Use 2% on the planned marking strokes in job order, with the beam off during travel. |
| Dry run | Follow the same planned moves with the beam off throughout. |

Verify that marking the observed dot leaves the controller offset alone, a normal jog leaves the placement fixed, and applying alignment reports how far the job origin will shift. Include an off-center dot and a centered lid in those checks. Verify that the marker follows a check and a print, that the screen paths match the selected checks, and that the four options differ on a job with blank margins, an irregular silhouette, internal detail, and raster run-ups.

## Keep placement and recovery across COM4 disconnects

Implemented in the November 9 source update; see [the recovery implementation note](usb-position-recovery-2026-11-09.md).
This includes completed prints and intentional app Disconnect, plus fixed-distance Park left / Return to zero
buttons beside Start. Queued-motion uncertainty is retained instead of claiming an exact physical stop.

On the Red Hill lid, the operator unplugged USB after jogging the head left for inspection and recovered the center with two 50 mm right jogs. The app should remember the job's placement and the head's last confirmed position for this case and for a dropout mid-print.

- Save the active job identity, selected job zero and artwork placement in local app data. Record the controller's work offset and last reported machine and work coordinates when available. Update the record after setting zero, applying alignment, shifting placement, and completing a jog or park. Confirm idle before recording a completed move. Use an atomic save so a disconnect cannot leave a half-written record.
- After an unplug at rest, show the saved placement and the last confirmed offset from job zero. Reconcile these with the controller's coordinates after reconnecting. Offer a beam-off **Return to job zero** once the coordinates are confirmed. If the controller reset or the head or piece moved, show what needs to be re-established.
- During engraving, extend the existing runner recovery record with the same placement and origin information. Keep acknowledged commands separate from confirmed motion checkpoints. After a dropout, show the last confirmed point and any uncertain stretch so the operator can choose where to resume without blindly repeating or skipping it.
- Verify both paths in demo mode, including an unplug after a completed inspection jog, a dropout with queued moves, and a controller reset. A reconnect should present recovery choices before sending motion.

## Live beam indicator and head marker lag

During the second Red Hill pass at 1,900 mm/min, the operator observed that **Laser on / off** and the head marker's on/off color changed too slowly to track the beam. The head position also looked a little laggy or jerky. The beam indication was the larger issue.

Measure the time from a controller status report through the runner and UI to both indicators, especially on rasters with short marks and gaps. Keep the beam label and marker color tied to the same reported sample. Show when beam status is stale or unavailable, and account for transitions that occur between reports. Then check head-position update cadence separately for smoother display. Verify in demo mode with rapid power transitions, continuous motion, a pause, and a simulated dropout.

## Draw no-burn zones directly on the preview

The Red Hill touch-up exposed a gap in the current workflow. In addition to editing existing zones, let the operator drag on the preview to draw a new rectangle or round zone where the engraving is already dark. Show the proposed boundary while dragging and rebuild **What burns** after release. The drawing tool should operate only in zone editing mode.
