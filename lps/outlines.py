"""Exact cell-edge contours of the cells that will actually engrave. No hull, padding or bounding box."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw


def box_path(bounds):
    x0, y0, x1, y1 = bounds
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def rounded_box_path(bounds, radius):
    x0, y0, x1, y1 = bounds
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    if r <= 0:
        return box_path(bounds)
    n = max(4, math.ceil(math.pi / 4 * math.sqrt(r / 0.1)))
    path = []
    for c, (x, y) in enumerate(((x1-r, y1-r), (x0+r, y1-r), (x0+r, y0+r), (x1-r, y0+r))):
        for i in range(n + 1):
            angle = (c + i / n) * math.pi / 2
            path.append((x + r * math.cos(angle), y + r * math.sin(angle)))
    return path + path[:1]


def image_boundary(bounds, piece_bounds=None, diameter=None):
    """Frame the image box, clipped to the round piece's usable face when applicable."""
    if diameter is None:
        return box_path(bounds)
    px0, py0, px1, py1 = piece_bounds
    cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
    r = diameter / 2
    # Chords stay within the usable circle, with at most ~0.05 mm error.
    n = max(32, math.ceil(math.pi * math.sqrt(r / 0.1)))
    path = [(cx + r * math.cos(math.tau * i / n), cy + r * math.sin(math.tau * i / n)) for i in range(n)]
    for axis, edge, sign in ((0, bounds[0], 1), (0, bounds[2], -1),
                             (1, bounds[1], 1), (1, bounds[3], -1)):
        clipped = []
        for a, b in zip(path[-1:] + path[:-1], path):
            da, db = sign * (a[axis] - edge), sign * (b[axis] - edge)
            if (da < 0) != (db < 0):
                t = da / (da - db)
                clipped.append(tuple(v + t * (w - v) for v, w in zip(a, b)))
            if db >= 0:
                clipped.append(b)
        path = clipped
    return path + path[:1] if len(path) >= 3 else []


def sticker_paths(paths):
    """Clockwise boundaries of separate burn islands, with counterclockwise holes omitted."""
    return [path for path in paths
            if sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(path, path[1:])) < 0]


def find_outer_circle(paths, geom):
    """Recognize an enclosing round exterior. An open arc also has a closed pixel contour,
    but that contour does not wind around the center of the circle."""
    if len(paths) != 1:
        return None
    points = np.asarray(paths[0])
    low, high = points.min(axis=0), points.max(axis=0)
    center = (low + high) / 2
    width, height = high - low
    radius = max(width, height) / 2
    tolerance = 2.5 * max(geom.x_pitch, geom.y_pitch)
    samples = np.vstack((points, (points[:-1] + points[1:]) / 2))
    radii = np.linalg.norm(samples - center, axis=1)
    if radius <= 3 * tolerance or abs(width - height) > tolerance or np.any(abs(radii - radius) > tolerance):
        return None
    angles = np.unwrap(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    if abs(angles[-1] - angles[0]) < math.pi:
        return None
    return (*center, 2 * radius)


def intended_circle(mask, geom):
    paths = exterior_contours(mask, geom.x0, geom.yt, geom.x_pitch, geom.y_pitch)
    return find_outer_circle(paths, geom)


def circular_image_guide(job, border="", partner=None):
    """One positioning circle in work coordinates, independent of engraving commands."""
    g = job.geom
    cx, cy = (g.x0 + g.x1) / 2, (g.y0 + g.yt) / 2
    diameter = min(g.art_w, g.art_h)
    source = "placed image (no outer ring detected)"
    if border.strip():
        try:
            inset = float(border)
        except ValueError:
            inset = math.nan
        if not math.isfinite(inset) or inset < 0 or 2 * inset >= diameter:
            return [], f"Enter a border from 0 to less than {diameter / 2:g} mm per side, or leave it blank for Auto."
        diameter -= 2 * inset
        source = f"placed image, {inset:g} mm border per side"
    else:
        for layer, label in ((job, "printed outer ring"), (partner, "paired layer's printed outer ring")):
            if layer is None:
                continue
            circle = (layer.intended_circle if layer.clipped_cells else
                      find_outer_circle(layer.trace_paths(), layer.geom))
            if circle:
                cx, cy, diameter = circle
                source = label
                break
    px0, py0, px1, py1 = g.piece_rect
    radius = diameter / 2
    usable = (px1 - px0) / 2 - job.piece["margins"][0]
    offset = math.hypot(cx - (px0 + px1) / 2, cy - (py0 + py1) / 2)
    if offset + radius > usable + 1e-7:
        return [], (f"The {diameter:.2f} mm image circle extends {offset + radius - usable:.2f} mm beyond "
                    "the usable lid face. Adjust the picture size or placement in Size. Changing the guide alone does not move the print.")
    # A multiple of four includes every cardinal point and closes once.
    n = 4 * max(8, math.ceil(math.pi * math.sqrt(radius / 0.05) / 4))
    path = [(cx + radius * math.cos(math.tau * i / n), cy + radius * math.sin(math.tau * i / n))
            for i in range(n)]
    return [path + path[:1]], f"One circle, {diameter:.2f} mm diameter, center X {cx:.2f} Y {cy:.2f} mm. Based on {source}."


def image_edge_feedback(job, paths):
    """Compare planned marks to the alignment guide; distinguish clipping before output."""
    messages = []
    warn = bool(job.clipped_cells)
    if warn:
        messages.append(f"The usable edge or a no-burn zone clips {job.clipped_cells:,} artwork cells.")
    if not paths or job.gray is None or job.piece.get("outline"):
        return " ".join(messages), warn
    g = job.geom
    if job.piece.get("shape") != "circle":
        box = job.burn_bbox()
        if box:
            gaps = (box[0] - g.x0, g.x1 - box[2], box[1] - g.y0, g.yt - box[3])
            messages.append("Blank to image edge: " + ", ".join(f"{side} {gap:.2f}" for side, gap in
                            zip(("left", "right", "bottom", "top"), gaps)) + " mm.")
        return " ".join(messages), warn
    path = np.asarray(paths[0])
    lo, hi = path.min(axis=0), path.max(axis=0)
    cx, cy = (hi + lo) / 2
    radius = (hi[0] - lo[0]) / 2
    # Only the extremes of each powered row can be farthest from the guide center.
    cells = np.zeros((g.rows, g.cols), dtype=bool)
    for p in job.passes:
        cells |= p.cells > 0
    rows = np.flatnonzero(cells.any(axis=1))
    if rows.size:
        left = cells.argmax(axis=1)[rows]
        right = g.cols - cells[:, ::-1].argmax(axis=1)[rows]
        dx = np.maximum(abs(g.x0 + left * g.x_pitch - cx), abs(g.x0 + right * g.x_pitch - cx))
        dy = g.yt - (rows + .5) * g.y_pitch - cy
        gap = radius - float(np.hypot(dx, dy).max())
        if gap <= -.005:
            messages.append(f"Artwork extends {abs(gap):.2f} mm past the guide. The guide does not crop the print.")
            warn = True
        elif gap >= .005:
            messages.append(f"The nearest mark stops {gap:.2f} mm inside the guide.")
        else:
            messages.append("The outermost mark meets the guide (within 0.01 mm).")
        edge = find_outer_circle(job.trace_paths(), g)
        if edge and math.hypot(edge[0] - cx, edge[1] - cy) + abs(edge[2] / 2 - radius) < max(g.x_pitch, g.y_pitch):
            messages.append("A continuous circular border follows this guide at the print resolution.")
        else:
            messages.append("This layer has no confirmed continuous border along the guide.")
            box = job.burn_bbox()
            gaps = (box[0] - lo[0], hi[0] - box[2], box[1] - lo[1], hi[1] - box[3])
            messages.append("At the four image extents: " + ", ".join(
                f"{side} {abs(v):.2f} mm {'past' if v < -.005 else 'inside'}"
                for side, v in zip(("left", "right", "bottom", "top"), gaps)) + ".")
    else:
        messages.append("This layer has no powered marks.")
    padding = (lo[0] - g.x0, g.x1 - hi[0], lo[1] - g.y0, g.yt - hi[1])
    if min(padding) >= -.001 and max(padding) >= .005:
        messages.append("Image edge to guide: " + ", ".join(f"{side} {gap:.2f}" for side, gap in
                        zip(("left", "right", "bottom", "top"), padding)) + " mm.")
    return " ".join(messages), warn


def cell_contours(mask):
    """Closed edge loops in (column,row) coordinates, including holes and separate islands.

    Directed edges keep the burned cell on the right. Right turns at diagonal contacts
    keep islands separate. The edge bitmap uses one byte/vertex instead of a Python
    dictionary for every edge, so detailed photographs remain practical.
    """
    m=np.asarray(mask,dtype=bool)
    h,w=m.shape
    p=np.pad(m,1)
    edges=np.zeros((h+1,w+1),dtype=np.uint8)
    edges[:h,:w] |= (m & ~p[:-2,1:-1]).astype(np.uint8)
    edges[:h,1:] |= (m & ~p[1:-1,2:]).astype(np.uint8)*2
    edges[1:,1:] |= (m & ~p[2:,1:-1]).astype(np.uint8)*4
    edges[1:,:w] |= (m & ~p[1:-1,:-2]).astype(np.uint8)*8
    directions=((1,0),(0,1),(-1,0),(0,-1))
    loops=[]
    for index in np.flatnonzero(edges):
        sr,sc=divmod(int(index),w+1)
        while edges[sr,sc]:
            r,c=sr,sc
            direction=next(d for d in range(4) if int(edges[r,c]) & (1<<d))
            previous=direction
            points=[(c,r)]
            while True:
                if direction!=previous:
                    points.append((c,r))
                previous=direction
                edges[r,c] &= np.uint8(255 ^ (1<<direction))
                dx,dy=directions[direction]
                c,r=c+dx,r+dy
                if (r,c)==(sr,sc):
                    break
                bits=int(edges[r,c])
                direction=next(d for d in ((direction+1)%4,direction,(direction-1)%4,(direction+2)%4)
                               if bits & (1<<d))
            points.append(points[0])
            loops.append(points)
    return loops


def physical_contours(mask, geom):
    return positioned_contours(cell_contours(mask), geom.x0, geom.yt, geom.x_pitch, geom.y_pitch)


def exterior_contours(mask, x0, yt, dx, dy):
    """Trace only artwork edges facing the outside, including concave boundaries."""
    exterior, holes = [], []
    for path in cell_contours(mask):
        area = sum(ax * by - bx * ay for (ax, ay), (bx, by) in zip(path, path[1:]))
        (exterior if area > 0 else holes).append(path)
    if holes:
        # Double the lattice so cell centres and edges are distinct. Test one
        # powered cell beside each contour to omit islands inside a closed hole.
        rows, cols = mask.shape
        inside = Image.new("1", (2 * cols + 1, 2 * rows + 1))
        draw = ImageDraw.Draw(inside)
        for path in holes:
            draw.polygon([(2 * c, 2 * r) for c, r in path], fill=1)

        def outside(path):
            (c, r), (nc, nr) = path[:2]
            dc = (nc > c) - (nc < c)
            dr = (nr > r) - (nr < r)
            return not inside.getpixel((2 * c + dc - dr, 2 * r + dr + dc))

        exterior = [path for path in exterior if outside(path)]
    return positioned_contours(exterior, x0, yt, dx, dy)


def positioned_contours(loops, x0, yt, dx, dy):
    return [[(round(x0 + c * dx, 3), round(yt - r * dy, 3)) for c, r in loop] for loop in loops]
