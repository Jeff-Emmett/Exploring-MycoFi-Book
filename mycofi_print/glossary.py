"""Typeset ``source/glossary.md`` as back-matter pages after the Appendix.

Same grid, frame and faces as the Appendix spread (pages 82-83): lavender frame
on the outer edge, Seriously Nostalgic title, Neue Haas body, entries flowing
from the top of every continuation page.
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

from .fonts import Fonts
from .geometry import PAGE_W, blank_page
from .layout import BODY_LEADING, BODY_SIZE, TITLE_SIZE, Run, draw_lines, fill_rect, text, wrap

GLOSSARY_MD = Path(__file__).resolve().parent.parent / "source" / "glossary.md"
LAVENDER = (0.7244983315467834, 0.724116861820221, 0.8653391599655151)
X_VERSO, X_RECTO, WIDTH = 56.0, 47.2, 347.0
ENTRY_SIZE = 7.6
ENTRY_LEADING = 10.4
ENTRY_GAP = 4.2
HANG = 9.0
TOP_NEXT, BOTTOM = 62.0, 606.0


def parse_glossary(path: Path = GLOSSARY_MD) -> tuple[str, list[tuple[str, str]]]:
    """Return (intro paragraph, [(term, definition), ...]) from the markdown."""
    src = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    m = re.search(r"^Intro:\s*(.+?)(?=\n\s*\n)", src, flags=re.S | re.M)
    if not m:
        raise SystemExit(f"{path}: no 'Intro:' paragraph found")
    intro = " ".join(m.group(1).split())
    entries = [(" ".join(t.split()), " ".join(d.split())) for t, d in re.findall(
        r"^\*\*(.+?)\*\*\s*—\s*(.+?)(?=\n\s*\n|\Z)", src, flags=re.S | re.M)]
    terms = len(re.findall(r"^\*\*", src, flags=re.M))
    if not entries or len(entries) != terms:
        raise SystemExit(f"{path}: parsed {len(entries)} of {terms} '**Term** — definition' "
                         "entries (each needs an em dash)")
    return intro, entries


def _new_page(doc: fitz.Document, verso: bool) -> fitz.Page:
    page = blank_page(doc)
    fill_rect(page, page.rect, LAVENDER)
    inner = fitz.Rect(38.7, 38.6, PAGE_W, 627.4) if verso else fitz.Rect(0, 38.6, 411.3, 627.4)
    fill_rect(page, inner, (1, 1, 1))
    return page


def append_glossary(doc: fitz.Document, fonts: Fonts) -> int:
    """Append the glossary to ``doc``; returns the number of pages added."""
    intro, entries = parse_glossary()
    added = 0

    def start():
        nonlocal added
        verso = (doc.page_count + 1) % 2 == 0
        page = _new_page(doc, verso)
        added += 1
        return page, (X_VERSO if verso else X_RECTO)

    page, x = start()
    text(page, fonts, (x, 82.0), "Glossary", font="display", size=TITLE_SIZE)
    y = draw_lines(page, wrap([Run(intro)], fonts, BODY_SIZE, WIDTH), fonts, BODY_SIZE,
                   x, 108.0, BODY_LEADING) + 30.0
    for term, definition in entries:
        runs = [Run(term + " ", "medium"), Run("— " + definition)]
        lines = wrap(runs, fonts, ENTRY_SIZE, WIDTH, indent=HANG)
        if y + (len(lines) - 1) * ENTRY_LEADING > BOTTOM:
            page, x = start()
            y = TOP_NEXT
        y = draw_lines(page, lines, fonts, ENTRY_SIZE, x, y, ENTRY_LEADING,
                       indent=HANG) + ENTRY_LEADING + ENTRY_GAP
    return added
