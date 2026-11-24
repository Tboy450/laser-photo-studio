"""Optional tone comparisons using existing visible level-point controls."""
from __future__ import annotations
from . import imaging
from .presets import LOOKS
from PIL import Image
import numpy as np


def options(look):
    black = int(look.get('black_point', 0))
    white = int(look.get('white_point', 255))
    if not 0 <= black < white <= 255:
        raise ValueError('Set valid Black/White points before comparing shadows.')
    result = [('Current', dict(look))]
    point = 'black_point' if look.get('negative', False) else 'white_point'
    for title, increment in (('Darker slate', 12), ('Stronger darks', 24)):
        value = min(white-1, black+increment) if point == 'black_point' else max(black+1, white-increment)
        if value != result[-1][1].get(point, black if point == 'black_point' else white):
            result.append((title, dict(look, **{point:value})))
    return result


def preview(picture, look, crop=None, edge=240):
    """Quick continuous-tone slate approximation, before dithering; no job/machine mutation."""
    w, h = (crop[2]-crop[0], crop[3]-crop[1]) if crop else picture.size
    scale = edge / max(w, h)
    gray = imaging.to_grid(picture, max(1, round(w*scale)), max(1, round(h*scale)), crop, **look)
    bare, mark = (np.asarray(c, dtype=float) for c in LOOKS['slate'])
    amount = (255-gray)/255
    rgb = bare + (mark-bare)*amount[:,:,None]
    return Image.fromarray(np.clip(rgb,0,255).astype('uint8'))
