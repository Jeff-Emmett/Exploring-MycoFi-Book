"""Preflight checks on a built interior: text-to-trim distances, fonts, ppi."""
from __future__ import annotations

import fitz

from .geometry import PT_PER_IN as IN


def trim_rect(page: fitz.Page) -> fitz.Rect:
    """TrimBox in fitz page space. (fitz's own ``page.trimbox`` ignores a
    non-zero MediaBox x origin, which every page here has.)"""
    doc = page.parent
    def box(key):
        v = doc.xref_get_key(page.xref, key)[1]
        return [float(x) for x in v.strip("[]").split()] if v != "null" else None
    mb = box("MediaBox")
    tb = box("TrimBox") or mb
    return fitz.Rect(tb[0] - mb[0], mb[3] - tb[3], tb[2] - mb[0], mb[3] - tb[1])


def text_margins(doc: fitz.Document, first_page_recto: bool = True):
    """Yield (page_no, edge, inches, text) for the tightest text on each edge."""
    for i, page in enumerate(doc):
        tr = trim_rect(page)
        recto = (i % 2 == 0) == first_page_recto
        worst: dict[str, tuple[float, str]] = {}
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    if not s["text"].strip():
                        continue
                    x0, y0, x1, y1 = s["bbox"]
                    left, right = x0 - tr.x0, tr.x1 - x1
                    d = {"top": y0 - tr.y0, "bottom": tr.y1 - y1,
                         "outside": right if recto else left,
                         "inside": left if recto else right}
                    for k, v in d.items():
                        if k not in worst or v < worst[k][0]:
                            worst[k] = (v, s["text"].strip()[:40])
        for k, (v, t) in worst.items():
            yield i + 1, k, v / IN, t


def margin_violations(doc: fitz.Document, outside: float, inside: float):
    """KDP: outside/top/bottom >= 0.25" from trim, inside >= 0.375" (24-150 pp)."""
    out = []
    for pno, edge, v, t in text_margins(doc):
        need = inside if edge == "inside" else outside
        if v < need - 1e-3:
            out.append((pno, edge, round(v, 3), t))
    return out


def low_ppi_images(doc: fitz.Document, floor: float = 250):
    out = []
    for i, page in enumerate(doc):
        for im in page.get_image_info():
            r = fitz.Rect(im["bbox"]) & page.rect
            if r.width < 0.4 * IN or r.height < 0.4 * IN:
                continue
            ppi = min(im["width"] / (fitz.Rect(im["bbox"]).width / IN),
                      im["height"] / (fitz.Rect(im["bbox"]).height / IN))
            if ppi < floor:
                out.append((i + 1, round(ppi)))
    return out


def unembedded_fonts(doc: fitz.Document):
    bad = set()
    for page in doc:
        for xref, ext, _t, name, *_ in page.get_fonts(full=True):
            if ext == "n/a":
                bad.add(name)
    return sorted(bad)
