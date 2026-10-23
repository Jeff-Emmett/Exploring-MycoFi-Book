#!/usr/bin/env python3
"""Build the 2nd-edition print interiors from the designer's InDesign export.

    source/pdf/ExploringMycoFiBook_6x9_base.pdf      (InDesign export, 6x9, 83 pp)
      -> repair: page boxes, font encoding, trial-font swap   (mycofi_print.pdffix)
      -> edits from the 2026 edit list                         (mycofi_print.edits)
      -> glossary                                              (mycofi_print.glossary)
      -> drop the two blank lead pages, renumber folios
      -> print-ready/ExploringMycoFi_interior_{kdp,lulu,web}.pdf

Usage::

    .venv/bin/python build_print.py                       # all platforms
    .venv/bin/python build_print.py --platform kdp --isbn-kdp 979-8-...
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import fitz
import pikepdf

from mycofi_print import bleed, checks, cover, edits, pdffix
from mycofi_print.fonts import BASE_PDF, Fonts
from mycofi_print.geometry import BLEED, PT_PER_IN, TRIM_H, TRIM_W, blank_page
from mycofi_print.glossary import append_glossary

REPO = Path(__file__).resolve().parent
OUT_DIR = REPO / "print-ready"
PLATFORMS = ("kdp", "lulu", "web")


def repaired_base() -> bytes:
    pdf = pikepdf.open(BASE_PDF)
    pdffix.normalize_boxes(pdf)
    n_enc = pdffix.fix_encoding(pdf)
    n_font = pdffix.swap_trial_font(pdf)
    print(f"  repaired {n_enc} mis-encoded glyph runs, swapped {n_font} trial-font objects")
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def edited_book(fonts: Fonts) -> bytes:
    doc = fitz.open("pdf", repaired_base())
    n_base = doc.page_count
    page = lambda orig: doc[orig - 1]  # noqa: E731

    edits.p78_rooted(doc, 77, fonts)
    edits.p9_contents(page(9), fonts, glossary_first_orig=n_base + 1)
    edits.p10_p11_praise(page(10), page(11), fonts)
    edits.p13_note(page(13), fonts)
    edits.p25_perspectives(page(25), fonts)
    edits.p46_quadratic_funding(page(46), fonts)
    edits.p62_homage(page(62), fonts)
    edits.p20_gutter(page(20))
    edits.p21_panel(page(21))
    edits.p28_gutter(page(28))
    edits.p36_gutter(page(36))
    edits.p38_gutter(page(38))
    for orig, (label, lines) in edits.TITLE_CARDS.items():
        edits.title_card(page(orig), fonts, label, lines)
    edits.p77_parting(page(77), fonts)
    edits.appendix(page(82), page(83), edits.extract_references(doc), fonts)

    added = append_glossary(doc, fonts)
    print(f"  glossary: {added} pages")
    edits.folios(doc, fonts)
    extended = sum(bleed.extend_bleed(p) for p in doc)
    print(f"  bleed: mirrored trim edges into the bleed on {extended} pages")
    if (doc.page_count - edits.DROPPED) % 2:     # even page count; no folio on the blank
        blank_page(doc)
    doc.delete_pages(list(range(edits.DROPPED)))
    return doc.tobytes(garbage=4, deflate=True)


def platform_pdf(book: bytes, platform: str, isbn: str | None, fonts: Fonts) -> Path:
    doc = fitz.open("pdf", book)
    edits.p6_edition(doc[edits.phys(6) - 1], fonts, isbn)
    data = doc.tobytes(garbage=4, deflate=True)
    pdf = pikepdf.open(io.BytesIO(data))
    pdffix.crop_for(pdf, platform)
    if platform == "web":
        pdf.Root.PageLayout = pikepdf.Name.TwoPageRight
    out = OUT_DIR / f"ExploringMycoFi_interior_{platform}.pdf"
    pdf.docinfo["/Title"] = "Exploring MycoFi: Mycelial Design Patterns for Web3 and Beyond"
    pdf.docinfo["/Author"] = "Jeff Emmett & Jessica Zartler"
    pdf.save(out, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    return out


def preflight(path: Path, platform: str) -> None:
    doc = fitz.open(path)
    viol = checks.margin_violations(doc, outside=0.25, inside=0.375) if platform != "web" else []
    low = checks.low_ppi_images(doc)
    bad = checks.unembedded_fonts(doc)
    r, n = doc[0].rect, doc.page_count
    doc.close()
    print(f"  {path.name}: {n} pp, "
          f"page {r.width / PT_PER_IN:.3f}x{r.height / PT_PER_IN:.3f}in, "
          f"{path.stat().st_size / 1e6:.1f} MB")
    print(f"    KDP margin violations: {len(viol)} {viol[:5]}")
    print(f"    unembedded fonts: {bad or 'none'}; image placements <250ppi: {len(low)} "
          f"(designer export is ~150ppi throughout)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=PLATFORMS + ("all",), default="all")
    ap.add_argument("--isbn-kdp")
    ap.add_argument("--isbn-lulu")
    ap.add_argument("--paper", default="standard-color", choices=sorted(cover.KDP_PER_PAGE),
                    help="KDP paper (sets the spine width)")
    ap.add_argument("--spine-clear", type=float, default=None,
                    help="spine text to spine edge, inches (default: the printer's "
                         f"recommendation, {cover.SPINE_CLEAR})")
    args = ap.parse_args()

    fonts = Fonts()
    print("=== edit ===")
    book = edited_book(fonts)
    OUT_DIR.mkdir(exist_ok=True)
    print("=== platforms ===")
    for platform in PLATFORMS if args.platform == "all" else (args.platform,):
        isbn = {"kdp": args.isbn_kdp, "lulu": args.isbn_lulu}.get(platform)
        out = platform_pdf(book, platform, isbn, fonts)
        preflight(out, platform)
        with fitz.open(out) as built:
            pages = built.page_count
        if platform in ("kdp", "lulu"):
            cov = OUT_DIR / f"ExploringMycoFi_cover_{platform}.pdf"
            info = cover.build(platform, pages, cov, fonts, paper=args.paper,
                               spine_clear=args.spine_clear)
            print(f"  {cov.name}: {info['width_in']:.4f}x{info['height_in']:.4f}in, "
                  f"spine {info['spine_in']:.4f}in, spine title: {info['spine_title']}")
        else:
            add_covers(out, fonts, pages)
    return 0


def add_covers(path: Path, fonts: Fonts, pages: int) -> None:
    """Web edition: front cover, blank, interior, blank, back cover - so the two-up
    view pairs facing pages the way the printed book does."""
    tmp = OUT_DIR / ".cover_web.pdf"
    cover.build("kdp", pages, tmp, fonts)
    wrap = fitz.open(tmp)
    full = wrap[0].rect
    front_trim = fitz.Rect(full.x1 - BLEED - TRIM_W, BLEED, full.x1 - BLEED, BLEED + TRIM_H)
    back_trim = fitz.Rect(BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H)
    page_rect = fitz.Rect(0, 0, TRIM_W, TRIM_H)
    doc = fitz.open(path)
    doc.new_page(pno=0, width=TRIM_W, height=TRIM_H).show_pdf_page(
        page_rect, wrap, 0, clip=front_trim)
    doc.new_page(pno=1, width=TRIM_W, height=TRIM_H)
    doc.new_page(width=TRIM_W, height=TRIM_H)
    doc.new_page(width=TRIM_W, height=TRIM_H).show_pdf_page(page_rect, wrap, 0, clip=back_trim)
    staged = path.with_suffix(".tmp.pdf")
    doc.save(staged, garbage=4, deflate=True)
    doc.close()
    wrap.close()
    tmp.unlink()
    staged.replace(path)


if __name__ == "__main__":
    sys.exit(main())
