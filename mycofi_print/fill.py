"""Close gaps where the designer's art stops short of the gutter.

On several left-hand pages a photo or panel bleeds off the outer edge but stops
at x=403, leaving a 38pt white strip down the gutter. Images may cross into the
gutter (only text needs the inside margin), so these fill it:

- ``mirror_extend`` continues soft or patterned art by mirroring its last strip
  (no seams where the art continues elsewhere on the page);
- ``cover_fit`` rescales a self-contained image to a larger box, keeping its
  aspect and cropping the overflow evenly.

Both render what is on the page now, so call them before folios and bleed.
"""
from __future__ import annotations

import io

import fitz
from PIL import Image

DPI = 300


def _render(page: fitz.Page, r: fitz.Rect) -> Image.Image:
    pm = page.get_pixmap(dpi=DPI, clip=r)
    return Image.frombytes("RGB", (pm.width, pm.height), pm.samples)


def _place(page: fitz.Page, img: Image.Image, r: fitz.Rect) -> None:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    page.insert_image(r, stream=buf.getvalue(), keep_proportion=False)


def mirror_extend(page: fitz.Page, edge: float, y0: float, y1: float, to: float) -> None:
    """Mirror the strip left of x=``edge`` into [edge, to] for rows y0..y1."""
    w = to - edge
    img = _render(page, fitz.Rect(edge - w, y0, edge, y1))
    _place(page, img.transpose(Image.Transpose.FLIP_LEFT_RIGHT), fitz.Rect(edge, y0, to, y1))


def mirror_extend_down(page: fitz.Page, edge: float, x0: float, x1: float, to: float) -> None:
    """Mirror the strip above y=``edge`` into [edge, to] for columns x0..x1."""
    h = to - edge
    img = _render(page, fitz.Rect(x0, edge - h, x1, edge))
    _place(page, img.transpose(Image.Transpose.FLIP_TOP_BOTTOM), fitz.Rect(x0, edge, x1, to))


def stretch_extend(page: fitz.Page, src_x0: float, edge: float, y0: float, y1: float,
                   to: float) -> None:
    """Widen the strip [src_x0, edge] across [src_x0, to] for rows y0..y1 (for flat
    or blocky backgrounds, where mirroring would duplicate the art beside them)."""
    img = _render(page, fitz.Rect(src_x0, y0, edge, y1))
    _place(page, img, fitz.Rect(src_x0, y0, to, y1))


def cover_fit(page: fitz.Page, src: fitz.Rect, dst: fitz.Rect) -> None:
    """Redraw the art in ``src`` filling ``dst`` at the same aspect, centre-cropped."""
    img = _render(page, src)
    scale = max(dst.width / src.width, dst.height / src.height)
    cw, ch = dst.width / scale / src.width * img.width, dst.height / scale / src.height * img.height
    left, top = (img.width - cw) / 2, (img.height - ch) / 2
    img = img.crop((round(left), round(top), round(left + cw), round(top + ch)))
    _place(page, img, dst)
