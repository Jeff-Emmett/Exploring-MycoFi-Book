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


def _needs_bleed(page: fitz.Page) -> bool:
    """True when the bleed ring is blank but the trim edge carries ink."""
    t, b = TRIM_RECT, BLEED
    pm = page.get_pixmap(dpi=36)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., :3]
    k = 36 / 72
    o, x0, x1, y0, y1 = int(b * k), int(t.x0 * k), int(t.x1 * k), int(t.y0 * k), int(t.y1 * k)
    ring = np.concatenate([a[:o].reshape(-1, 3), a[-o:].reshape(-1, 3),
                           a[:, :o].reshape(-1, 3), a[:, -o:].reshape(-1, 3)])
    edge = np.concatenate([a[y0:y0 + 2].reshape(-1, 3), a[y1 - 2:y1].reshape(-1, 3),
                           a[:, x0:x0 + 2].reshape(-1, 3), a[:, x1 - 2:x1].reshape(-1, 3)])
    return (ring.min(1) > 245).mean() > 0.9 and (edge.min(1) < 245).mean() > 0.05


def extend_bleed(page: fitz.Page) -> bool:
    if not _needs_bleed(page):
        return False
    t, b = TRIM_RECT, BLEED
    flip_h, flip_v = Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM
    pieces = [
        (fitz.Rect(t.x0, t.y0, t.x1, t.y0 + b), fitz.Rect(t.x0, 0, t.x1, t.y0), (flip_v,)),
        (fitz.Rect(t.x0, t.y1 - b, t.x1, t.y1), fitz.Rect(t.x0, t.y1, t.x1, t.y1 + b), (flip_v,)),
        (fitz.Rect(t.x0, t.y0, t.x0 + b, t.y1), fitz.Rect(0, t.y0, t.x0, t.y1), (flip_h,)),
        (fitz.Rect(t.x1 - b, t.y0, t.x1, t.y1), fitz.Rect(t.x1, t.y0, t.x1 + b, t.y1), (flip_h,)),
    ]
    for cx, dx in ((t.x0, -b), (t.x1 - b, b)):          # corners: mirror both ways
        for cy, dy in ((t.y0, -b), (t.y1 - b, b)):
            src = fitz.Rect(cx, cy, cx + b, cy + b)
            pieces.append((src, src + (dx, dy, dx, dy), (flip_h, flip_v)))
    for src, dst, flips in pieces:
        img = _render(page, src)
        for f in flips:
            img = img.transpose(f)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        page.insert_image(dst, stream=buf.getvalue())
    return True
