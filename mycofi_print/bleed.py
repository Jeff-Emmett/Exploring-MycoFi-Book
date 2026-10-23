"""Give trim-only pages a real 0.125" bleed.

The designer exported every page cropped at the trim, so the bleed ring is white
and any trim drift would show white slivers along the coloured frames. Each page
edge is extended by mirroring the outermost 9pt inside the trim into the bleed —
exact for the solid frames, and a seamless continuation for photos.
"""
from __future__ import annotations

import io

import fitz
import numpy as np
from PIL import Image

from .geometry import BLEED, TRIM_RECT

DPI = 320                   # 9pt -> 40px exactly


def _render(page: fitz.Page, r: fitz.Rect) -> Image.Image:
    pm = page.get_pixmap(dpi=DPI, clip=r)
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)


def _has_ink(page: fitz.Page, r: fitz.Rect) -> bool:
    # Probe 2pt inside ``r``: a 9pt strip rounds to whole pixels and would
    # otherwise pick up a row of the neighbouring area.
    pm = page.get_pixmap(dpi=72, clip=r + (2, 2, -2, -2))
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., :3]
    return bool((a.min(2) < 240).any())


def extend_bleed(page: fitz.Page) -> bool:
    """Mirror every trim edge that carries any ink into its bleed. Where the bleed
    is already painted (the glossary, art run off the gutter) the mirror matches
    what is there, so no edge needs a separate test."""
    t, b = TRIM_RECT, BLEED
    flip_h, flip_v = Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM
    sides = [   # (inside strip, bleed strip, flips)
        (fitz.Rect(t.x0, t.y0, t.x1, t.y0 + b), fitz.Rect(t.x0, 0, t.x1, t.y0), (flip_v,)),
        (fitz.Rect(t.x0, t.y1 - b, t.x1, t.y1), fitz.Rect(t.x0, t.y1, t.x1, t.y1 + b), (flip_v,)),
        (fitz.Rect(t.x0, t.y0, t.x0 + b, t.y1), fitz.Rect(0, t.y0, t.x0, t.y1), (flip_h,)),
        (fitz.Rect(t.x1 - b, t.y0, t.x1, t.y1), fitz.Rect(t.x1, t.y0, t.x1 + b, t.y1), (flip_h,)),
    ]
    pieces = [(src, dst, f) for src, dst, f in sides if _has_ink(page, src)]
    if not pieces:
        return False
    for cx, dx in ((t.x0, -b), (t.x1 - b, b)):          # corners: mirror both ways
        for cy, dy in ((t.y0, -b), (t.y1 - b, b)):
            src = fitz.Rect(cx, cy, cx + b, cy + b)
            dst = src + (dx, dy, dx, dy)
            if _has_ink(page, src):
                pieces.append((src, dst, (flip_h, flip_v)))
    for src, dst, flips in pieces:
        img = _render(page, src)
        for f in flips:
            img = img.transpose(f)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        page.insert_image(dst, stream=buf.getvalue(), keep_proportion=False)
    return True
