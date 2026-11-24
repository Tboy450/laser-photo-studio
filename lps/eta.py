"""Stable planned-time countdown; never infer elapsed motion from command count."""
from __future__ import annotations

import math


def components(body, start_index=0, accel=500.0):
    # Same time model as planner.estimate_seconds, split into meaningful categories.
    result = dict(engraving_s=0.0, laser_off_s=0.0, dwell_s=0.0, overhead_s=0.0)
    x = y = 0.0
    for index, command in enumerate(body):
        category, seconds = "overhead_s", 0.003
        if command.startswith("G4 P"):
            result_key, value = "dwell_s", float(command[4:])
        elif command.startswith("G1 "):
            words = dict((p[0], float(p[1:])) for p in command.split()[1:])
            nx, ny, speed = words['X'], words['Y'], words['F'] / 60.0
            distance = math.hypot(nx-x, ny-y)
            value = distance / speed + (speed / accel if distance > 0 and abs(ny-y) > 1e-9 else 0.0)
            result_key = "engraving_s" if words.get('S', 0) > 0 else "laser_off_s"
            x, y = nx, ny
        else:
            result_key, value = "overhead_s", 0.05 if command.startswith('M4') else 0.0
        if index >= start_index:
            result[category] += seconds
            result[result_key] += value
    return result


def remaining(budget_s, active_s):
    return max(0.0, budget_s - active_s)
