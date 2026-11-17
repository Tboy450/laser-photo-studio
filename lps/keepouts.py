"""Geometry for editable window/no-burn masks. No machine access."""
from __future__ import annotations

import math


def zone_bounds(zone):
    x, y = zone["x"], zone["y"]
    if zone["kind"] == "circle":
        r = zone["r"]
        return x - r, y - r, x + r, y + r
    return x, y, x + zone["w"], y + zone["h"]


def constrain_zone(zone, width, height):
    keys = ("x", "y", "r") if zone["kind"] == "circle" else ("x", "y", "w", "h")
    z = dict(zone)
    for key in keys:
        z[key] = float(z[key])
    if not all(math.isfinite(z[k]) for k in keys):
        raise ValueError("Zone measurements must be finite numbers.")
    if any(z[k] <= 0 for k in keys if k not in ("x", "y")):
        raise ValueError("Zone width, height and radius must be greater than zero.")
    if z["kind"] == "circle":
        r = z["r"] = min(z["r"], width / 2, height / 2)
        z["x"] = min(width - r, max(r, z["x"]))
        z["y"] = min(height - r, max(r, z["y"]))
    else:
        z["w"], z["h"] = min(width, z["w"]), min(height, z["h"])
        z["x"] = min(width - z["w"], max(0, z["x"]))
        z["y"] = min(height - z["h"], max(0, z["y"]))
    return {k: round(v, 3) if k in keys else v for k, v in z.items()}


def drag_zone(zone, width, height, dx, dy, handle="move"):
    """Move or resize a copy, in piece millimeters; resizing never flips a window."""
    z = dict(zone)
    if handle == "move":
        z.update(x=zone["x"] + dx, y=zone["y"] + dy)
    elif zone["kind"] == "circle":
        z["r"] = max(0.1, min(math.hypot(zone["r"] + dx, dy), zone["x"], width-zone["x"],
                               zone["y"], height-zone["y"]))
    else:
        left, bottom, right, top = zone_bounds(zone)
        minimum = min(0.2, width, height)
        if "w" in handle:
            left = min(right-minimum, max(0, left+dx))
        if "e" in handle:
            right = max(left+minimum, min(width, right+dx))
        if "s" in handle:
            bottom = min(top-minimum, max(0, bottom+dy))
        if "n" in handle:
            top = max(bottom+minimum, min(height, top+dy))
        z.update(x=left, y=bottom, w=right-left, h=top-bottom)
    return constrain_zone(z, width, height)
