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
