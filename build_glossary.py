#!/usr/bin/env python3
"""Typeset ``source/glossary.md`` into the back matter of the KDP interior PDF.

The Scribus/IDML build (``mycofi_publish.py``) regenerates the interior from the
InDesign master, which has no glossary. This script adds one afterwards, so the
glossary survives a rebuild:

  1. Adds a ``Glossary`` line to the CONTENTS page (PDF page 9).
  2. Appends the glossary pages after the Appendix, continuing the page numbering
     and reproducing the book's back-matter layout — lavender trim frame on the
     outer edge, Seriously Nostalgic italic section head, ABC Connect Mono folio.

Every geometry constant below was measured off the existing Appendix spread
(pages 82-83) so the new pages sit on the same grid.

Fonts: Neue Haas Grotesk is not redistributable and is only present in the PDF as
a subset, so body text is set in Nimbus Sans (URW's metrically-identical
Helvetica clone). The two Mycofi display faces are used directly from the
system font install.

Usage::

    python3 build_glossary.py [--in IN.pdf] [--out OUT.pdf]
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

REPO = Path(__file__).resolve().parent
GLOSSARY_MD = REPO / "source" / "glossary.md"
DEFAULT_PDF = REPO / "ExploringMycoFiBook_KDP_6x9_bleed_final.pdf"

# ---- Fonts -----------------------------------------------------------------
MYCOFI_FONTS = Path.home() / ".local/share/fonts/Mycofi"
F_DISPLAY = MYCOFI_FONTS / "SeriouslyNostalgicItal-Reg.otf"   # section heads
F_FOLIO = MYCOFI_FONTS / "ABCConnectMono-Nail.otf"            # page numbers
F_BODY = Path("/usr/share/fonts/opentype/urw-base35/NimbusSans-Regular.otf")
F_BOLD = Path("/usr/share/fonts/opentype/urw-base35/NimbusSans-Bold.otf")

# ---- Page geometry (measured from pages 82/83) -----------------------------
PAGE_W, PAGE_H = 441.0, 666.0

# Raw PDF boxes. Bleed sits on the outer edge only; the spine edge is flush.
BOX_VERSO = dict(media=(-9, -9, 432, 657), trim=(0, 0, 432, 648))
BOX_RECTO = dict(media=(0, -9, 441, 657), trim=(0, 0, 432, 648))

# The trim frame is a single 30pt-wide stroked rectangle, drawn wider than the
# page so only three of its four sides show.
FRAME_COLOR = (0.7244983315467834, 0.724116861820221, 0.8653391599655151)
FRAME_WIDTH = 30.0
FRAME_VERSO = (23.693878, 23.5946045, 858.3061523, 642.4053955)
FRAME_RECTO = (-417.3061218, 23.5946045, 417.3061218, 642.4053955)

TEXT_COLOR = (0x19 / 255, 0x17 / 255, 0x0C / 255)

MARGIN_VERSO = 56.02
MARGIN_RECTO = 46.04
COL_WIDTH = 340.0

HEAD_SIZE = 9.76
HEAD_BASELINE = 63.65

INTRO_SIZE = 8.79
INTRO_BASELINE = 85.10
INTRO_LEADING = 12.60

BODY_SIZE = 6.6
BODY_LEADING = 9.73          # baseline-to-baseline inside an entry
ENTRY_GAP = 3.89             # extra space between entries
BODY_TOP = 154.80            # first baseline on every glossary page
BODY_BOTTOM = 612.0          # last permissible baseline
HANG_INDENT = 8.0            # continuation lines of an entry

HEAD_TEXT = "G L O S S A R Y"
MAX_GLOSSARY_PAGES = 12      # tail window scanned by the already-built guard

FOLIO_SIZE = 7.81
FOLIO_BASELINE = 638.74
FOLIO_X_VERSO = 24.35
FOLIO_X_RECTO = 409.14

# Pages are authored in the same coordinate space as pages 82/83 (PyMuPDF's
# top-left origin on a 441x666 sheet) and then re-boxed, which shifts the
# origin. These offsets keep the ink where it was drawn.
SHIFT_VERSO = (-9.0, 9.0)
SHIFT_RECTO = (0.0, 9.0)


# ---- Glossary source -------------------------------------------------------

def parse_glossary(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """Return (intro paragraph, [(term, definition), ...]) from the markdown."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

    intro_match = re.search(r"^Intro:\s*(.+?)(?=\n\s*\n)", text, flags=re.S | re.M)
    if not intro_match:
        raise SystemExit(f"{path}: no 'Intro:' paragraph found")
    intro = " ".join(intro_match.group(1).split())

    entries = []
    for m in re.finditer(r"^\*\*(.+?)\*\*\s*—\s*(.+?)(?=\n\s*\n|\Z)", text, flags=re.S | re.M):
        term = " ".join(m.group(1).split())
        definition = " ".join(m.group(2).split())
        entries.append((term, definition))
    if not entries:
        raise SystemExit(f"{path}: no '**Term** — definition' entries found")
    return intro, entries


# ---- Typesetting -----------------------------------------------------------

class Fonts:
    def __init__(self) -> None:
        for f in (F_DISPLAY, F_FOLIO, F_BODY, F_BOLD):
            if not f.exists():
                raise SystemExit(f"missing font: {f}")
        self.display = fitz.Font(fontfile=str(F_DISPLAY))
        self.folio = fitz.Font(fontfile=str(F_FOLIO))
        self.body = fitz.Font(fontfile=str(F_BODY))
        self.bold = fitz.Font(fontfile=str(F_BOLD))


def wrap_entry(term: str, definition: str, fonts: Fonts, width: float):
    """Lay an entry out as lines of (text, font) runs, with a hanging indent.

    The term is set bold and runs into the definition on the same line.
    """
    runs = [(term + " ", fonts.bold)]
    runs += [("— ", fonts.body)]
    runs += [(w + " ", fonts.body) for w in definition.split()]

    lines: list[list[tuple[str, fitz.Font]]] = []
    cur: list[tuple[str, fitz.Font]] = []
    cur_w = 0.0
    avail = width
    for text, font in runs:
        w = font.text_length(text, BODY_SIZE)
        if cur and cur_w + w > avail:
            lines.append(cur)
            cur, cur_w = [], 0.0
            avail = width - HANG_INDENT
        cur.append((text, font))
        cur_w += w
    if cur:
        lines.append(cur)
    return lines


def paginate(intro: str, entries, fonts: Fonts, first_page_no: int):
    """Flow the glossary into pages. Returns a list of page dicts."""
    pages: list[dict] = []
    page_no = first_page_no

    def new_page():
        verso = page_no % 2 == 0
        return {
            "number": page_no,
            "verso": verso,
            "margin": MARGIN_VERSO if verso else MARGIN_RECTO,
            "head": None,
            "intro": None,
            "lines": [],   # (baseline_y, indent, [(text, font)])
        }

    page = new_page()
    page["head"] = HEAD_TEXT

    # Intro paragraph, wrapped to the column.
    intro_lines: list[str] = []
    cur = ""
    for word in intro.split():
        trial = (cur + " " + word).strip()
        if fonts.body.text_length(trial, INTRO_SIZE) > COL_WIDTH and cur:
            intro_lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        intro_lines.append(cur)
    page["intro"] = intro_lines

    y = BODY_TOP
    for term, definition in entries:
        lines = wrap_entry(term, definition, fonts, COL_WIDTH)
        height = (len(lines) - 1) * BODY_LEADING
        if y + height > BODY_BOTTOM:
            pages.append(page)
            page_no += 1
            page = new_page()
            y = BODY_TOP
        for i, line in enumerate(lines):
            page["lines"].append((y + i * BODY_LEADING, 0.0 if i == 0 else HANG_INDENT, line))
        y += height + BODY_LEADING + ENTRY_GAP
    pages.append(page)
    return pages


def render(pages, fonts: Fonts) -> fitz.Document:
    doc = fitz.open()
    for spec in pages:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        dx, dy = SHIFT_VERSO if spec["verso"] else SHIFT_RECTO
        margin = spec["margin"]

        frame = FRAME_VERSO if spec["verso"] else FRAME_RECTO
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(frame[0] + dx, frame[1] + dy, frame[2] + dx, frame[3] + dy))
        shape.finish(color=FRAME_COLOR, width=FRAME_WIDTH, fill=None)
        shape.commit()

        tw = fitz.TextWriter(page.rect)

        if spec["head"]:
            tw.append((margin + dx, HEAD_BASELINE + dy), spec["head"],
                      font=fonts.display, fontsize=HEAD_SIZE)
        if spec["intro"]:
            for i, line in enumerate(spec["intro"]):
                tw.append((margin + dx, INTRO_BASELINE + i * INTRO_LEADING + dy), line,
                          font=fonts.body, fontsize=INTRO_SIZE)

        for baseline, indent, runs in spec["lines"]:
            x = margin + indent + dx
            for text, font in runs:
                tw.append((x, baseline + dy), text, font=font, fontsize=BODY_SIZE)
                x += font.text_length(text, BODY_SIZE)

        folio_x = FOLIO_X_VERSO if spec["verso"] else FOLIO_X_RECTO
        tw.append((folio_x + dx, FOLIO_BASELINE + dy), str(spec["number"]),
                  font=fonts.folio, fontsize=FOLIO_SIZE)

        tw.write_text(page, color=TEXT_COLOR)
    return doc


# ---- Contents page ---------------------------------------------------------

CONTENTS_PAGE_INDEX = 8       # PDF page 9
CONTENTS_LABEL_BASELINE = 460.46    # 'Appendix' row
CONTENTS_NUMBER_BASELINE = 460.62   # its folio sits a hair lower
CONTENTS_ROW_STEP = 19.45
CONTENTS_LABEL_X = 38.20
CONTENTS_NUMBER_X = 234.12
CONTENTS_LABEL_SIZE = 8.79
CONTENTS_NUMBER_SIZE = 7.81
# Nimbus Sans has no medium weight; overprinting at a sub-point offset lands
# between its regular and bold, close to Neue Haas Grotesk 65 Medium.
FAUX_MEDIUM_SMEAR = 0.15


def add_contents_row(doc: fitz.Document, fonts: Fonts, page_no: int) -> None:
    """Append a 'Glossary <page>' row under 'Appendix' on the CONTENTS page.

    The book sets contents labels in Neue Haas Grotesk 65 Medium. Nimbus Sans has
    no medium, so the label is filled and hairline-stroked to match the weight.
    """
    page = doc[CONTENTS_PAGE_INDEX]

    for smear in (0.0, FAUX_MEDIUM_SMEAR):
        tw = fitz.TextWriter(page.rect)
        tw.append((CONTENTS_LABEL_X + smear, CONTENTS_LABEL_BASELINE + CONTENTS_ROW_STEP),
                  "Glossary", font=fonts.body, fontsize=CONTENTS_LABEL_SIZE)
        tw.write_text(page, color=TEXT_COLOR)

    tw = fitz.TextWriter(page.rect)
    tw.append((CONTENTS_NUMBER_X, CONTENTS_NUMBER_BASELINE + CONTENTS_ROW_STEP),
              str(page_no), font=fonts.body, fontsize=CONTENTS_NUMBER_SIZE)
    tw.write_text(page, color=TEXT_COLOR)


# ---- Assembly --------------------------------------------------------------

def set_boxes(page, verso: bool) -> None:
    spec = BOX_VERSO if verso else BOX_RECTO
    media = RectangleObject(spec["media"])
    trim = RectangleObject(spec["trim"])
    page.mediabox = media
    page.cropbox = media
    page.bleedbox = media
    page.trimbox = trim
    page.artbox = trim


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", type=Path, default=DEFAULT_PDF)
    ap.add_argument("--out", dest="dst", type=Path, default=None)
    args = ap.parse_args()
    dst = args.dst or args.src

    fonts = Fonts()
    intro, entries = parse_glossary(GLOSSARY_MD)

    doc = fitz.open(args.src)
    n_existing = doc.page_count
    # Refuse to append twice. The head is only set on the glossary's own first
    # page, which lands somewhere in the last few pages of an already-built PDF.
    for i in range(max(0, n_existing - MAX_GLOSSARY_PAGES), n_existing):
        if HEAD_TEXT in doc[i].get_text():
            doc.close()
            raise SystemExit(
                f"{args.src} already carries a glossary (page {i + 1}); "
                "rebuild the interior from Scribus first")

    first_page_no = n_existing + 1
    pages = paginate(intro, entries, fonts, first_page_no)
    print(f"  {len(entries)} entries -> {len(pages)} pages "
          f"({first_page_no}-{first_page_no + len(pages) - 1})")

    add_contents_row(doc, fonts, first_page_no)
    body_bytes = doc.tobytes()
    doc.close()

    gloss = render(pages, fonts)
    gloss_bytes = gloss.tobytes()
    gloss.close()

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(body_bytes)).pages:
        writer.add_page(page)
    for spec, page in zip(pages, PdfReader(io.BytesIO(gloss_bytes)).pages):
        set_boxes(page, spec["verso"])
        writer.add_page(page)

    # --in and --out are the same file in the normal publish flow, so stage the
    # result and swap it in atomically rather than truncating the input.
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        writer.write(fh)
    os.replace(tmp, dst)
    print(f"  wrote {dst} ({dst.stat().st_size:,} bytes, "
          f"{n_existing + len(pages)} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
