# Size and edge-clearance guidance

Step 3 now distinguishes the outside physical piece dimensions from Picture size. Exact image size uses its box as the image itself, with zero margins and possible stretching. Margins reserve the usable area; they do not erase a decorative border inside an image.

The Picture size section shows the actual planned picture-box gaps to Left, Bottom, Right and Top outside bounds. Negative values mean the picture box extends beyond the piece. A separate message warns when artwork enters a margin, where marks are masked. These are bounding-box clearances, not the nearest powered strokes; round edges, corner shapes and no-burn zones may remove additional marks. While rebuilding, the display explicitly says clearances are not current.

Changing origin changes coordinate numbers, not physical edge gaps. Nudging changes picture placement, not head position or job zero. Image perimeter checks the image box; Total travel includes laser-off run-ups.

Existing placement/job/setup formats are unchanged. Regression proof uses actual Tk controls, known asymmetric clearances, center/lower-left origin, an out-of-bounds nudge, exact sizing, saved job placement and JSON setup reload. No new saved-job importer, automatic border removal or active-app installation is included.
