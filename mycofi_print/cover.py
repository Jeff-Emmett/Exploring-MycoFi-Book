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
import pikepdf
import segno

from .fonts import Fonts
from .geometry import BLEED, PT_PER_IN, TRIM_H, TRIM_W
from .layout import Run, draw_lines, draw_qr, remove_text, rounded_rect, text, wrap

REPO = Path(__file__).resolve().parent.parent
ART = REPO / "cover.pdf"

SAFE = 36.0                         # 0.5" — Lulu's safety margin; KDP needs less
# Spine thickness per page, inches. KDP: kdp.amazon.com/help/topic/G201953020.
KDP_PER_PAGE = {"standard-color": 0.002252, "premium-color": 0.002347,
                "bw-white": 0.002252, "bw-cream": 0.0025}
KDP_SPINE_CLEAR = 0.0625            # text to spine edge
LULU_SPINE_CLEAR = 0.125            # Lulu Book Creation Guide p.17

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
PATTERNS = ["Network Infrastructure  •  Fractal Nature  •  Emergent Coordination",
            "Dynamic Flow  •  Mutual Reciprocity  •  Polycentric Pluralism"]
CLOSING = ("If there is any hope for a transition away from extraction, domination, and "
           "planetary overshoot, towards regeneration, equity, and planetary healing, our "
           "economies must be realigned with nature’s ecologies - and for that, we can’t afford "
           "to ignore what mushrooms have to teach us.")
ENDORSEMENTS = [
    ("“Fungi invite us to participate in a commons-based economy where resources are "
     "metabolized, shared, and regenerated simultaneously through the very same process. "
     "MycoFi is less about how to imitate them than how to join in the dance.”",
     "Douglas Rushkoff, author and host of Team Human"),
    ("“Nature is a magical long-term, stable code base, with time for revisions and "
     "optimization. Hopefully, this work will provide another reminder that the answers "
     "have always been there. Let’s listen together.”",
     "Amber Case, author of Calm Technology"),
    # Closing sentence of his full endorsement (interior p. 8), verbatim.
    ("“By learning from mycelium, our species can achieve the next quantum level in our "
     "evolution.”",
     "Paul Stamets, renowned mycologist and author of Mycelium Running"),
]
BUY_IT_FORWARD = "https://mycofi.earth/buy-it-forward"


def spine_inches(platform: str, pages: int, paper: str = "standard-color") -> float:
    if platform == "kdp":
        return pages * KDP_PER_PAGE[paper]
    if platform == "lulu":
        return pages / 444 + 0.06       # Lulu Book Creation Guide p.13
    raise ValueError(platform)


# CMYK fills of the back cover's yellow and pink copy boxes in the designer file.
BOX_FILLS = ([0.019989, 0.0400085, 0.710938, 0], [0, 0.129883, 0.0100098, 0])


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
          spine_title: bool | None = None) -> dict:
    spine = spine_inches(platform, pages, paper) * PT_PER_IN
    clear = (KDP_SPINE_CLEAR if platform == "kdp" else LULU_SPINE_CLEAR) * PT_PER_IN
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
    fx = front.x0 + SAFE
    text(page, fonts, (fx, 112), "Exploring", font="display", size=68, color=TITLE_YELLOW)
    text(page, fonts, (fx, 182), "MycoFi", font="display", size=68, color=TITLE_YELLOW)
    for i, line in enumerate(("Mycelial Design Patterns", "for Web3 and Beyond")):
        text(page, fonts, (fx, 428 + i * 25), line, font="medium", size=21, color=SUB_PINK)
    right = front.x1 - BLEED - SAFE
    for i, name in enumerate(("Jeff Emmett", "Jessica Zartler")):
        text(page, fonts, (right, H - BLEED - SAFE - 24 + i * 24), name, font="display",
             size=19, color=TITLE_YELLOW, align="right", word_space=2.0)

    # ---- spine ----
    if spine_title is None:
        spine_title = (spine - 2 * clear) >= 4.5 and pages > 80
    if spine_title:
        avail = spine - 2 * clear
        size = avail / 0.92          # Seriously Nostalgic: ascender-to-descender ~0.92 em
        title = "Exploring MycoFi"
        tw = fonts["display"].text_length(title, size)
        cx = spine_r.x0 + spine / 2
        # Reads top-to-bottom; letter tops face the front cover, so the baseline
        # sits left of centre.
        baseline_x = cx - size * 0.32
        y0 = (H - tw) / 2
        w = fitz.TextWriter(page.rect)
        w.append((baseline_x, y0), title, font=fonts["display"], fontsize=size)
        w.write_text(page, color=TITLE_YELLOW,
                     morph=(fitz.Point(baseline_x, y0), fitz.Matrix(-90)))

    # ---- back ----
    bx0, bx1 = BLEED + SAFE, BLEED + TRIM_W - SAFE
    width = bx1 - bx0
    pad = 16.0
    size, lead = 9.5, 13.4
    inner = width - 2 * pad
    blurb = wrap([Run(BLURB_LEAD, "medium"), Run(BLURB_REST)], fonts, size, inner)
    intro = wrap([Run(PATTERNS_INTRO, "medium")], fonts, size, inner)
    closing = wrap([Run(CLOSING)], fonts, size, inner)
    n = len(blurb) + len(intro) + len(PATTERNS) + len(closing)
    y_box = BLEED + SAFE
    box_h = n * lead + 3 * 7 + 2 * pad - 4
    rounded_rect(page, fitz.Rect(bx0, y_box, bx1, y_box + box_h), 12, fill=BOX_YELLOW)
    y = y_box + pad + size
    y = draw_lines(page, blurb, fonts, size, bx0 + pad, y, lead) + lead + 7
    y = draw_lines(page, intro, fonts, size, bx0 + pad, y, lead) + lead + 3
    for line in PATTERNS:
        text(page, fonts, ((bx0 + bx1) / 2, y), line, font="italic", size=size, align="center")
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

    # QR (bottom left); the bottom-right 2" x 1.2" stays clear for the printer's
    # ISBN barcode (KDP and Lulu both stamp their own when they assign the ISBN).
    q_side = 72.0
    q_bottom = H - BLEED - SAFE - 12
    qr_bg = fitz.Rect(bx0, q_bottom - q_side - 8, bx0 + q_side + 16, q_bottom + 14)
    rounded_rect(page, qr_bg, 8, fill=(1, 1, 1))
    draw_qr(page, segno.make(BUY_IT_FORWARD, error="m"),
             fitz.Rect(bx0 + 8, q_bottom - q_side, bx0 + 8 + q_side, q_bottom))
    text(page, fonts, (qr_bg.x0 + qr_bg.width / 2, q_bottom + 9), "mycofi.earth/buy-it-forward",
         font="medium", size=5.6, align="center")
    barcode_zone = fitz.Rect(BLEED + TRIM_W - 18 - 144, H - BLEED - 18 - 86.4,
                             BLEED + TRIM_W - 18, H - BLEED - 18)
    if ey + eh > barcode_zone.y0 - 6 or qr_bg.y0 < ey + eh + 6:
        raise SystemExit(f"back cover copy overruns the QR/barcode band (ends {ey + eh:.0f})")

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
