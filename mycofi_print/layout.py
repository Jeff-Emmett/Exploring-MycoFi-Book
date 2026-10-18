"""Small typesetting kit for patching pages in the book's own faces.

Coordinates are fitz page space of a *normalized* page (450x666, origin at the
top-left of the bleed, trim = TRIM_RECT).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

from .fonts import Fonts

INK = (0x19 / 255, 0x17 / 255, 0x0C / 255)          # the book's text black
LINK_GREEN = (0x15 / 255, 0x76 / 255, 0x3B / 255)

BODY_SIZE = 8.79          # Neue Haas 55 Roman, body copy
BODY_LEADING = 12.63
HEAD_SIZE = 11.72         # Neue Haas 65 Medium, in-text heads
TITLE_SIZE = 31.24        # Seriously Nostalgic, chapter titles


def remove_text(page: fitz.Page, *rects: fitz.Rect) -> None:
    """Delete the text inside ``rects``; leave images and vector art alone."""
    for r in rects:
        page.add_redact_annot(r)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)


def remove_images(page: fitz.Page, rect: fitz.Rect) -> None:
    """Delete image placements overlapping ``rect`` (text and vectors kept)."""
    page.add_redact_annot(rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_NONE)


@dataclass
class Run:
    text: str
    font: str = "body"                 # key into Fonts
    color: tuple = INK


@dataclass
class Line:
    runs: list[tuple[str, str, tuple]] = field(default_factory=list)
    width: float = 0.0


def _split_long(word: str, font: fitz.Font, size: float, width: float) -> list[str]:
    """Break a token wider than the column (a URL) after / . - _ or ?, else anywhere."""
    if font.text_length(word, size) <= width:
        return [word]
    pieces = re.findall(r"[^/.\-_?=&]*[/.\-_?=&]+|[^/.\-_?=&]+$", word)
    out, cur = [], ""
    for p in pieces:
        if cur and font.text_length(cur + p, size) > width:
            out.append(cur)
            cur = ""
        while font.text_length(p, size) > width:          # no break point at all
            k = len(p)
            while k > 1 and font.text_length(p[:k], size) > width:
                k -= 1
            out.append(p[:k])
            p = p[k:]
        cur += p
    if cur:
        out.append(cur)
    return out


def wrap(runs: list[Run], fonts: Fonts, size: float, width: float,
         indent: float = 0.0) -> list[Line]:
    """Greedy word wrap over styled runs. ``indent`` applies to wrapped lines."""
    words: list[tuple[str, str, tuple]] = []
    for r in runs:
        parts = r.text.split(" ")
        for i, w in enumerate(parts):
            sep = " " if i < len(parts) - 1 else ""
            if w or sep:
                for piece in _split_long(w, fonts[r.font], size, width - indent):
                    words.append((piece, r.font, r.color))
                words[-1] = (words[-1][0] + sep, r.font, r.color)
    lines: list[Line] = []
    cur = Line()
    avail = width
    for text, font, color in words:
        w = fonts[font].text_length(text, size)
        trimmed = fonts[font].text_length(text.rstrip(" "), size)
        if cur.runs and cur.width + trimmed > avail:
            lines.append(cur)
            cur = Line()
            avail = width - indent
        cur.runs.append((text, font, color))
        cur.width += w
    if cur.runs:
        lines.append(cur)
    for ln in lines:            # drop trailing space from the measured width
        t, f, _c = ln.runs[-1]
        ln.width -= fonts[f].text_length(t, size) - fonts[f].text_length(t.rstrip(" "), size)
    return lines


def draw_lines(page: fitz.Page, lines: list[Line], fonts: Fonts, size: float,
               x: float, baseline: float, leading: float, width: float = 0.0,
               align: str = "left", indent: float = 0.0) -> float:
    """Write wrapped lines; returns the baseline after the last line."""
    writers: dict[tuple, fitz.TextWriter] = {}
    y = baseline
    for i, ln in enumerate(lines):
        lx = x + (indent if i else 0.0)
        if align == "center":
            lx = x + (width - ln.width) / 2
        elif align == "right":
            lx = x + width - ln.width
        for text, font, color in ln.runs:
            tw = writers.setdefault(color, fitz.TextWriter(page.rect))
            tw.append((lx, y), text, font=fonts[font], fontsize=size)
            lx += fonts[font].text_length(text, size)
        y += leading
    for color, tw in writers.items():
        tw.write_text(page, color=color)
    return y - leading


def text(page: fitz.Page, fonts: Fonts, xy: tuple[float, float], s: str,
         font: str = "body", size: float = BODY_SIZE, color=INK,
         align: str = "left", tracking: float = 0.0, word_space: float = 0.0) -> float:
    """Single line. ``tracking`` adds that many points after every character
    (for the book's letterspaced Seriously Nostalgic labels); ``word_space`` adds
    to each space (Seriously Nostalgic's own is very tight). Returns width."""
    f = fonts[font]
    width = (f.text_length(s, size) + tracking * max(len(s) - 1, 0)
             + word_space * s.count(" "))
    x, y = xy
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    tw = fitz.TextWriter(page.rect)
    if tracking or word_space:
        for ch in s:
            tw.append((x, y), ch, font=f, fontsize=size)
            x += f.text_length(ch, size) + tracking + (word_space if ch == " " else 0.0)
    else:
        tw.append((x, y), s, font=f, fontsize=size)
    tw.write_text(page, color=color)
    return width


def rounded_rect(page: fitz.Page, r: fitz.Rect, radius: float, fill, opacity: float = 1.0,
                 stroke=None) -> None:
    shape = page.new_shape()
    shape.draw_rect(r, radius=min(radius / min(r.width, r.height), 0.5))
    shape.finish(fill=fill, color=stroke, fill_opacity=opacity, stroke_opacity=opacity,
                 width=0 if stroke is None else 0.75)
    shape.commit()


def fill_rect(page: fitz.Page, r: fitz.Rect, fill) -> None:
    shape = page.new_shape()
    shape.draw_rect(r)
    shape.finish(fill=fill, color=None)
    shape.commit()


def draw_qr(page: fitz.Page, qr, rect: fitz.Rect) -> None:
    """Vector QR from a segno code. No quiet zone: callers place it on white.
    Modules overlap by 0.05pt so viewers don't show hairline seams between them."""
    matrix = [list(row) for row in qr.matrix]
    cell = rect.width / len(matrix)
    shape = page.new_shape()
    for r, row in enumerate(matrix):
        for c, v in enumerate(row):
            if v:
                x, y = rect.x0 + c * cell, rect.y0 + r * cell
                shape.draw_rect(fitz.Rect(x, y, x + cell + 0.05, y + cell + 0.05))
    shape.finish(fill=INK, color=None)
    shape.commit()
