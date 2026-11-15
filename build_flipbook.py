#!/usr/bin/env python3
"""Compose the flipbook edition (book.mycofi.earth) from the print-ready outputs.

    front cover (trim crop of cover_kdp) + interior pages + back cover
      -> print-ready/ExploringMycoFi_flipbook.pdf

flipbook-service pairs pages 0|1, 2|3 ... (showCover:false), so the front cover sits
left of interior p1 (a recto) and every later spread faces the way the printed book does.
The interior's trailing even-out blank is dropped so the back cover closes the book.

Run after build_print.py, then publish with flipbook-service's scripts/add-flipbook.py.
"""
from pathlib import Path

import fitz

from mycofi_print.geometry import BLEED, TRIM_H, TRIM_W

OUT = Path(__file__).resolve().parent / "print-ready"


def is_blank(page: fitz.Page) -> bool:
    return not (page.get_text().strip() or page.get_images() or page.get_drawings())


def main() -> None:
    cover = fitz.open(OUT / "ExploringMycoFi_cover_kdp.pdf")
    full = cover[0].rect
    front = fitz.Rect(full.x1 - BLEED - TRIM_W, BLEED, full.x1 - BLEED, BLEED + TRIM_H)
    back = fitz.Rect(BLEED, BLEED, BLEED + TRIM_W, BLEED + TRIM_H)
    # web interior = front, blank, interior..., blank, back; already cropped to trim
    web = fitz.open(OUT / "ExploringMycoFi_interior_web.pdf")
    last = web.page_count - 3
    if is_blank(web[last]):
        last -= 1

    page = fitz.Rect(0, 0, TRIM_W, TRIM_H)
    out = fitz.open()
    out.new_page(width=TRIM_W, height=TRIM_H).show_pdf_page(page, cover, 0, clip=front)
    out.insert_pdf(web, from_page=2, to_page=last)
    out.new_page(width=TRIM_W, height=TRIM_H).show_pdf_page(page, cover, 0, clip=back)
    out.set_metadata({"title": "Exploring MycoFi: Mycelial Design Patterns for Web3 and Beyond",
                      "author": "Jeff Emmett & Jessica Zartler"})
    dest = OUT / "ExploringMycoFi_flipbook.pdf"
    out.save(dest, garbage=4, deflate=True)
    print(f"{dest.name}: {out.page_count} pp")


if __name__ == "__main__":
    main()
