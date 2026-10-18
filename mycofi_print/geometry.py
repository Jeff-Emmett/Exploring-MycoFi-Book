"""Page geometry shared by every module (points; 72 per inch).

Interior pages are normalized to a 450x666 MediaBox at PDF origin (-9, -9): 0.125"
bleed on all four sides around the 6x9 trim. In fitz page space (origin at the
top-left of the bleed) the trim is TRIM_RECT.
"""
import fitz

PT_PER_IN = 72.0
BLEED = 9.0
TRIM_W, TRIM_H = 432.0, 648.0
PAGE_W, PAGE_H = TRIM_W + 2 * BLEED, TRIM_H + 2 * BLEED

TRIM_PDF = (0.0, 0.0, TRIM_W, TRIM_H)                                # PDF space
FULL_BLEED_PDF = (-BLEED, -BLEED, TRIM_W + BLEED, TRIM_H + BLEED)   # PDF space
TRIM_RECT = fitz.Rect(BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H)  # fitz space


def blank_page(doc: fitz.Document, pno: int = -1) -> fitz.Page:
    """A normalized (full-bleed, 450x666) blank page."""
    page = doc.new_page(pno=pno, width=PAGE_W, height=PAGE_H)
    page.set_mediabox(fitz.Rect(FULL_BLEED_PDF))
    return page
