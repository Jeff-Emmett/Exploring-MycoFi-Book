"""One-piece wrap cover (back | spine | front) for KDP and Lulu.

Art comes from the designer's InDesign cover (``cover.pdf``: page 1 front, page 2
back) with its text and copy boxes stripped; all type is reset as vector text in
the book's faces. Spine width follows each printer's published formula, so the
cover must be rebuilt whenever the interior page count changes.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import fitz
import numpy as np
import pikepdf
import segno
from PIL import Image, ImageFilter

from .fonts import Fonts
from .geometry import BLEED, PT_PER_IN, TRIM_H, TRIM_W
from .layout import Run, draw_lines, draw_qr, remove_text, rounded_rect, text, wrap

REPO = Path(__file__).resolve().parent.parent
ART = REPO / "cover.pdf"

SAFE = 36.0                         # 0.5" — Lulu's safety margin; KDP needs less
# Spine thickness per page, inches. KDP: kdp.amazon.com/help/topic/G201953020.
KDP_PER_PAGE = {"standard-color": 0.002252, "premium-color": 0.002347,
                "bw-white": 0.002252, "bw-cream": 0.0025}
# Spine text to spine edge, inches. The printers ask for 0.0625 (KDP) and 0.125
# (Lulu) to absorb fold drift; the author chose the largest type the spine holds,
# so only a hair of clearance is kept by default (see build(spine_clear=)).
KDP_SPINE_CLEAR = 0.0625
LULU_SPINE_CLEAR = 0.125
SPINE_CLEAR = 0.02
TITLE_ART_GAP = 8.0                 # pt between the title's ink and the mushroom art
TITLE_LINE_GAP = 2.0                # pt between "Exploring" descenders and "MycoFi"

BG = (0.13141070306301117, 0.11682306975126266, 0.11407645046710968)
TITLE_YELLOW = (0xFB / 255, 0xEA / 255, 0x6A / 255)
SUB_PINK = (0xFC / 255, 0xE3 / 255, 0xEC / 255)
BOX_YELLOW = (0.9852292537689209, 0.9159380197525024, 0.4142976999282837)
BOX_PINK = (0.9884946942329407, 0.8893263339996338, 0.9240406155586243)

BLURB_LEAD = "Exploring MycoFi: Mycelial Design Patterns for Web3 and Beyond"
BLURB_REST = (" guides readers on an underground exploration into the world wise web of "
              "mycelial networks, the most prolific producers of public goods on Earth. This "
              "book examines how the evolutionary adaptability of fungi could help us imagine "
              "biomimetic alternatives to status-quo economic systems that demand infinite "
              "growth on a finite planet.")
PATTERNS_INTRO = "MycoFi translates six design patterns of mycelial ecologies to Web3 economies:"
PATTERNS = ["Network Infrastructure", "Fractal Nature", "Emergent Coordination",
            "Dynamic Flow", "Mutual Reciprocity", "Polycentric Pluralism"]
CLOSING = ("If there is any hope for a transition away from extraction, domination, and "
           "planetary overshoot, towards regeneration, equity, and planetary healing, our "
           "economies must be realigned with nature’s ecologies - and for that, we can’t afford "
           "to ignore what mushrooms have to teach us.")
ENDORSEMENTS = [
    # Opening sentence of his full endorsement (interior p. 8), verbatim.
    ("“MycoFi beautifully illustrates and underscores that mycelium’s design is borne from "
     "the universe.”",
     "Paul Stamets, renowned mycologist and author of Mycelium Running"),
    ("“Fungi invite us to participate in a commons-based economy where resources are "
     "metabolized, shared, and regenerated simultaneously through the very same process. "
     "MycoFi is less about how to imitate them than how to join in the dance.”",
     "Douglas Rushkoff, author and host of Team Human"),
    ("“Nature is a magical long-term, stable code base, with time for revisions and "
     "optimization. Hopefully, this work will provide another reminder that the answers "
     "have always been there. Let’s listen together.”",
     "Amber Case, author of Calm Technology"),
]
BUY_IT_FORWARD = "https://mycofi.earth/buy-it-forward"
BUY_IT_FORWARD_NOTE = ("Want to see these ideas myceliate? Buy-it-forward to provide a book "
                       "to disseminate to the network.")



def spine_inches(platform: str, pages: int, paper: str = "standard-color") -> float:
    if platform == "kdp":
        return pages * KDP_PER_PAGE[paper]
    if platform == "lulu":
        return pages / 444 + 0.06       # Lulu Book Creation Guide p.13
    raise ValueError(platform)


# CMYK fills of the back cover's yellow and pink copy boxes in the designer file.
BOX_FILLS = ([0.019989, 0.0400085, 0.710938, 0], [0, 0.129883, 0.0100098, 0])


@lru_cache(maxsize=None)
def _ink(font_path: Path, s: str) -> tuple[float, float]:
    """(lowest, highest) ink of ``s`` in em, from the glyph outlines."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont
    font = TTFont(font_path)
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    lo = hi = 0.0
    for ch in s:
        if ord(ch) in cmap:
            pen = BoundsPen(glyphs)
            glyphs[cmap[ord(ch)]].draw(pen)
            if pen.bounds:
                lo, hi = min(lo, pen.bounds[1]), max(hi, pen.bounds[3])
    upm = font["head"].unitsPerEm
    return lo / upm, hi / upm


def _spine_line(page: fitz.Page, fonts: Fonts, s: str, font: str, size: float, cx: float,
                y: float, color, from_top: bool) -> None:
    """Spine text reading top-to-bottom (letter tops toward the front cover), ink
    centred on ``cx``; starts at ``y`` if ``from_top`` else ends there."""
    lo, hi = _ink(fonts.paths[font], s)
    baseline_x = cx - (lo + hi) / 2 * size
    y0 = y if from_top else y - fonts[font].text_length(s, size)
    w = fitz.TextWriter(page.rect)
    w.append((baseline_x, y0), s, font=fonts[font], fontsize=size)
    w.write_text(page, color=color, morph=(fitz.Point(baseline_x, y0), fitz.Matrix(-90)))


def _ink_mask(page: fitz.Page, clip: fitz.Rect) -> np.ndarray:
    """Pixels (1 per pt) of ``clip`` that differ visibly from the cover's dark ground."""
    pm = page.get_pixmap(dpi=72, clip=clip)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., :3]
    ground = np.array(BG) * 255
    return np.abs(a.astype(int) - ground).sum(2) > 60


def _text_mask(fonts: Fonts, size: float, s: str, x: float, baseline: float,
               w: float, h: float) -> np.ndarray:
    doc = fitz.open()
    p = doc.new_page(width=w, height=h)
    tw = fitz.TextWriter(p.rect)
    tw.append((x, baseline), s, font=fonts["display"], fontsize=size)
    tw.write_text(p, color=(0, 0, 0))
    pm = p.get_pixmap(dpi=72)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., 0] < 128


def _grow(mask: np.ndarray, pt: float) -> np.ndarray:
    r = max(1, round(pt))
    img = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.asarray(img) > 0


def _shift_down(mask: np.ndarray, dy: int) -> np.ndarray:
    out = np.zeros_like(mask)
    out[dy:] = mask[:mask.shape[0] - dy]
    return out


def _fit_title(fonts: Fonts, art: np.ndarray, x_left: float, x_right: float, y_top: float):
    """Largest "Exploring" / "MycoFi" (second line starting under the i) that stays
    inside the safe area and clear of the art. Returns (size, b1, x2, b2)."""
    h, w = art.shape
    keep_out = _grow(art, TITLE_ART_GAP)
    disp = fonts["display"]
    hi1 = _ink(fonts.paths["display"], "Exploring")[1]
    for size in np.arange(110.0, 40.0, -0.5):
        x2 = x_left + disp.text_length("Explor", size)
        if max(x_left + disp.text_length("Exploring", size),
               x2 + disp.text_length("MycoFi", size)) > x_right:
            continue
        b1 = y_top + hi1 * size
        line1 = _grow(_text_mask(fonts, size, "Exploring", x_left, b1, w, h), TITLE_LINE_GAP)
        b2_ref = b1 + 0.5 * size
        line2 = _text_mask(fonts, size, "MycoFi", x2, b2_ref, w, h)
        for dy in range(0, round(0.8 * size)):          # tightest leading that clears line 1
            moved = _shift_down(line2, dy)
            if not (moved & line1).any():
                break
        if not (moved & keep_out).any():
            return float(size), b1, x2, b2_ref + dy
    raise SystemExit("cover title: no size fits above the art")


@lru_cache(maxsize=None)
def _art_bytes(page_index: int) -> bytes:
    """One page of the designer cover with its type and copy boxes removed."""
    pdf = pikepdf.open(ART)
    page = pdf.pages[page_index]
    if page_index == 1:
        # The boxes are plain path fills over complete artwork: stop filling them.
        colour_ops = {pikepdf.Operator(o) for o in ("g", "rg", "sc", "scn", "cs")}
        ops, fill, saved = [], None, []
        for operands, op in pikepdf.parse_content_stream(page):
            if op == pikepdf.Operator("k"):
                fill = [float(v) for v in operands]
            elif op in colour_ops:
                fill = None
            elif op == pikepdf.Operator("q"):
                saved.append(fill)
            elif op == pikepdf.Operator("Q") and saved:
                fill = saved.pop()
            if op in (pikepdf.Operator("f"), pikepdf.Operator("f*")) and fill and any(
                    max(abs(a - b) for a, b in zip(fill, box)) < 1e-4 for box in BOX_FILLS):
                op = pikepdf.Operator("n")
            ops.append((operands, op))
        page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(ops))
    buf = io.BytesIO()
    pdf.save(buf)
    src = fitz.open("pdf", buf.getvalue())
    src.select([page_index])
    remove_text(src[0], *(fitz.Rect(w[:4]) for w in src[0].get_text("words")))
    return src.tobytes()


def _art(page_index: int) -> fitz.Document:
    return fitz.open("pdf", _art_bytes(page_index))


def build(platform: str, pages: int, out: Path, fonts: Fonts, paper: str = "standard-color",
          spine_title: bool | None = None, spine_clear: float = SPINE_CLEAR) -> dict:
    spine = spine_inches(platform, pages, paper) * PT_PER_IN
    clear = spine_clear * PT_PER_IN
    W, H = 2 * (BLEED + TRIM_W) + spine, TRIM_H + 2 * BLEED
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)

    back = fitz.Rect(0, 0, BLEED + TRIM_W, H)
    spine_r = fitz.Rect(back.x1, 0, back.x1 + spine, H)
    front = fitz.Rect(spine_r.x1, 0, W, H)
    page.draw_rect(page.rect, color=None, fill=BG)

    # Art, scaled to the panel height and cropped on the spine side.
    for idx, panel, spine_side_left in ((0, front, True), (1, back, False)):
        src = _art(idx)
        sr = src[0].rect
        need_w = sr.height * panel.width / panel.height
        clip = (fitz.Rect(sr.x1 - need_w, 0, sr.x1, sr.y1) if spine_side_left
                else fitz.Rect(0, 0, need_w, sr.y1))
        page.show_pdf_page(panel, src, 0, clip=clip)

    # ---- front ----
    # Title: as large as the clear band above the mushroom allows, measured
    # against the art itself. The subtitle sits in the pocket left of the stem
    # below the cap (x < ~205pt from the fold, y 345-440).
    fx = front.x0 + SAFE
    art = _ink_mask(page, front)
    size, b1, x2, b2 = _fit_title(fonts, art, SAFE, TRIM_W - SAFE, BLEED + SAFE)
    text(page, fonts, (fx, b1), "Exploring", font="display", size=size, color=TITLE_YELLOW)
    text(page, fonts, (front.x0 + x2, b2), "MycoFi", font="display", size=size,
         color=TITLE_YELLOW)
    for i, line in enumerate(("Mycelial Design", "Patterns for Web3", "and Beyond")):
        text(page, fonts, (fx, 372 + i * 24), line, font="medium", size=20, color=SUB_PINK)
    right = front.x1 - BLEED - SAFE
    for i, name in enumerate(("Jeff Emmett", "Jessica Zartler")):
        text(page, fonts, (right, H - BLEED - SAFE - 56 + i * 27), name, font="display",
             size=23, color=TITLE_YELLOW, align="right", word_space=2.4)
    text(page, fonts, (right, H - BLEED - SAFE - 4), "Foreword by Scott Morris",
         font="display", size=10, color=TITLE_YELLOW, align="right", word_space=1.2)

    # ---- spine ----
    if spine_title is None:
        spine_title = (spine - 2 * clear) >= 4.5 and pages > 80
    if spine_title:
        # Both lines are sized so their ink fills the spine minus ``clear`` on each
        # side; the author line has no descenders, so it is capped below the title
        # to keep the hierarchy. Each line keeps the 0.5" safe distance from the
        # head and foot trim.
        avail = spine - 2 * clear
        cx = spine_r.x0 + spine / 2
        end_inset = BLEED + SAFE
        title, authors = "Exploring MycoFi", "Emmett & Zartler"
        lo, hi = _ink(fonts.paths["display"], title)
        t_size = avail / (hi - lo)
        lo, hi = _ink(fonts.paths["display"], authors)
        a_size = min(avail / (hi - lo), t_size * 0.85)
        _spine_line(page, fonts, title, "display", t_size, cx, end_inset, TITLE_YELLOW, True)
        _spine_line(page, fonts, authors, "display", a_size, cx, H - end_inset, SUB_PINK, False)

    # ---- back ----
    bx0, bx1 = BLEED + SAFE, BLEED + TRIM_W - SAFE
    width = bx1 - bx0
    pad = 16.0
    size, lead = 9.5, 13.4
    inner = width - 2 * pad
    blurb = wrap([Run(BLURB_LEAD, "medium"), Run(BLURB_REST)], fonts, size, inner)
    intro = wrap([Run(PATTERNS_INTRO, "medium")], fonts, size, inner)
    closing = wrap([Run(CLOSING)], fonts, size, inner)
    numbered = [Run(f"{i}. ", "medium") if k == 0 else Run(name + "   ", "italic")
                for i, name in enumerate(PATTERNS, 1) for k in (0, 1)]
    rows = [numbered[:6], numbered[6:]]
    pattern_lines = [wrap(r, fonts, size, inner) for r in rows]
    if any(len(pl) > 1 for pl in pattern_lines):
        raise SystemExit("numbered design patterns no longer fit two lines")
    n = len(blurb) + len(intro) + len(rows) + len(closing)
    y_box = BLEED + SAFE
    box_h = n * lead + 3 * 7 + 2 * pad - 4
    rounded_rect(page, fitz.Rect(bx0, y_box, bx1, y_box + box_h), 12, fill=BOX_YELLOW)
    y = y_box + pad + size
    y = draw_lines(page, blurb, fonts, size, bx0 + pad, y, lead) + lead + 7
    y = draw_lines(page, intro, fonts, size, bx0 + pad, y, lead) + lead + 3
    for pl in pattern_lines:
        draw_lines(page, pl, fonts, size, bx0 + pad, y, lead, width=inner, align="center")
        y += lead
    y = draw_lines(page, closing, fonts, size, bx0 + pad, y + 4, lead)

    qsize, qlead = 8.6, 11.6
    blocks = []
    for q, who in ENDORSEMENTS:
        blocks.append((wrap([Run(q)], fonts, qsize, inner), who))
    eh = (2 * pad + qsize * 0.75
          + sum(len(ls) * qlead for ls, _ in blocks) + (len(blocks) - 1) * (qlead + 8))
    ey = y_box + box_h + 12
    rounded_rect(page, fitz.Rect(bx0, ey, bx1, ey + eh), 12, fill=BOX_PINK)
    y = ey + pad + qsize
    for lines, who in blocks:
        y = draw_lines(page, lines, fonts, qsize, bx0 + pad, y, qlead) + qlead
        text(page, fonts, (bx1 - pad, y), who, font="medium", size=qsize, align="right")
        y += qlead + 8

    # QR + note (bottom left). The bottom-right 2" x 1.2" stays clear for the
    # printer's ISBN barcode: KDP and Lulu both stamp their own there.
    barcode_zone = fitz.Rect(BLEED + TRIM_W - 18 - 144, H - BLEED - 18 - 86.4,
                             BLEED + TRIM_W - 18, H - BLEED - 18)
    # Laid out bottom-up: the note bubble on the safe line, the QR card above it.
    note_size, note_lead, note_pad = 8.0, 10.6, 7.0
    note_w = barcode_zone.x0 - 10 - bx0
    note = wrap([Run(BUY_IT_FORWARD_NOTE, "medium")], fonts, note_size, note_w - 2 * note_pad)
    note_h = (len(note) - 1) * note_lead + note_size * 0.95 + 2 * note_pad
    bubble = fitz.Rect(bx0, H - BLEED - SAFE + 4 - note_h, bx0 + note_w, H - BLEED - SAFE + 4)
    q_side = 92.0
    qr_bg = fitz.Rect(bx0, bubble.y0 - 8 - (q_side + 22), bx0 + q_side + 16, bubble.y0 - 8)
    q_bottom = qr_bg.y0 + 8 + q_side
    rounded_rect(page, qr_bg, 8, fill=(1, 1, 1))
    draw_qr(page, segno.make(BUY_IT_FORWARD, error="m"),
            fitz.Rect(bx0 + 8, q_bottom - q_side, bx0 + 8 + q_side, q_bottom))
    text(page, fonts, (qr_bg.x0 + qr_bg.width / 2, q_bottom + 9), "mycofi.earth/buy-it-forward",
         font="medium", size=6.2, align="center")
    rounded_rect(page, bubble, 10, fill=BOX_YELLOW)
    draw_lines(page, note, fonts, note_size, bubble.x0 + note_pad,
               bubble.y0 + note_pad + note_size * 0.75, note_lead)
    if bubble.intersects(barcode_zone):
        raise SystemExit("buy-it-forward note runs into the barcode area")
    if qr_bg.y0 < ey + eh + 6:
        raise SystemExit(f"back cover copy overruns the QR band (ends {ey + eh:.0f})")

    page.set_trimbox(fitz.Rect(BLEED, BLEED, W - BLEED, H - BLEED))
    if platform == "lulu":
        # Lulu wants one flattened image page at 300-600 ppi; 400 keeps type crisp.
        pm = page.get_pixmap(dpi=400)
        flat = fitz.open()
        fp = flat.new_page(width=W, height=H)
        fp.insert_image(fp.rect, stream=pm.tobytes("jpeg", jpg_quality=92))
        flat.save(out, garbage=4, deflate=True)
    else:
        doc.save(out, garbage=4, deflate=True)
    return {"spine_in": spine / PT_PER_IN, "width_in": W / PT_PER_IN, "height_in": H / PT_PER_IN,
            "spine_title": spine_title, "barcode_zone": barcode_zone}
