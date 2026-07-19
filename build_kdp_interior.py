"""Apply all interior edits to Exploring MycoFi book and reassemble KDP PDF.

Inputs:
  /tmp/book_pages/p-NN.png         (rendered pages 1-83 from existing PDF)
  /home/jeffe/.../source images and fonts

Output:
  /home/jeffe/Github/Exploring-MycoFi-Book/ExploringMycoFiBook_KDP_interior_v2.pdf
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import numpy as np
import re
import subprocess

# ---- Paths ----
PAGES_DIR = "/tmp/book_pages"
OUT_DIR = "/tmp/book_pages_v2"
os.makedirs(OUT_DIR, exist_ok=True)
OUT_PDF = "/home/jeffe/Github/Exploring-MycoFi-Book/ExploringMycoFiBook_KDP_interior_v2.pdf"

# ---- Fonts ----
COVER_DIR = "/mnt/c/Users/jeffe/Downloads/COVER_Exploring Mycofi_ Mycelial Design Patterns for Web3 and Beyond"
SERIOUSLY_FONT = os.path.join(COVER_DIR, "Document fonts/SeriouslyNostalgic-Regular.otf")
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_ITAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"
DEJAVU_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
DEJAVU_SERIF_ITAL = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"
DEJAVU_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"

# ---- Page geometry (KDP 6x9 with bleed) ----
DPI = 300
PAGE_W_PX = 1838  # 6.125"
PAGE_H_PX = 2775  # 9.25"
TRIM_W_PX = 1800  # 6.0"
TRIM_H_PX = 2700  # 9.0"
BLEED_PX = round(0.125 * DPI)   # 38
SAFE_MARGIN_PX = round(0.25 * DPI)  # 75 (text safety from trim)


# ============================================================
# Utility helpers
# ============================================================

def text_lines_wrap(text, font, max_w):
    """Word-wrap. For tokens longer than max_w (e.g. URLs), break at characters
    so the line never exceeds max_w."""
    def _w(s):
        return font.getbbox(s)[2] - font.getbbox(s)[0]

    def _split_long(token):
        if _w(token) <= max_w:
            return [token]
        # Greedy character split
        out, cur = [], ""
        for ch in token:
            if _w(cur + ch) > max_w and cur:
                out.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    lines, cur = [], ""
    for word in text.split():
        if _w(word) > max_w:
            # flush current line, then emit broken pieces
            if cur:
                lines.append(cur)
                cur = ""
            for piece in _split_long(word):
                if cur and _w(cur + " " + piece) <= max_w:
                    cur = cur + " " + piece
                else:
                    if cur:
                        lines.append(cur)
                    cur = piece
            continue
        trial = (cur + " " + word).strip()
        if _w(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_paragraph(draw, x, y, text, font, color, max_w, leading_ratio=1.32):
    leading = int(font.size * leading_ratio)
    for line in text_lines_wrap(text, font, max_w):
        draw.text((x, y), line, fill=color, font=font)
        y += leading
    return y


def sample_dominant(arr_2d):
    """Return the dominant pixel color via median."""
    flat = arr_2d.reshape(-1, 3)
    return tuple(int(c) for c in np.median(flat, axis=0))


def is_dark(color):
    return sum(color[:3]) / 3 < 128


# ============================================================
# Soft-hyphen glyph fix: the source PDF's font renders soft hyphens (U+00AD)
# as a diamond/lozenge glyph (≠-like). We extract their PDF coordinates with
# PyMuPDF and overlay proper hyphens at each location.
# ============================================================

PDF_PATH = "/home/jeffe/Github/Exploring-MycoFi-Book/ExploringMycoFiBook_KDP_6x9_bleed_final.pdf"

_soft_locs_cache = None


def get_soft_hyphen_locs():
    """Returns {page_num: [(x0,y0,x1,y1), ...]} of soft-hyphen char bboxes
    in PDF coords (pts). Cached."""
    global _soft_locs_cache
    if _soft_locs_cache is not None:
        return _soft_locs_cache
    import fitz
    doc = fitz.open(PDF_PATH)
    locs = {}
    for pno in range(len(doc)):
        page = doc[pno]
        d = page.get_text("rawdict")
        page_locs = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    for ch in span.get("chars", []):
                        if ch.get("c") == "\xad":
                            page_locs.append(tuple(ch["bbox"]))
        if page_locs:
            locs[pno + 1] = page_locs
    doc.close()
    _soft_locs_cache = locs
    return locs


def fix_soft_hyphens(img: Image.Image, page_num: int) -> Image.Image:
    locs = get_soft_hyphen_locs().get(page_num)
    if not locs:
        return img
    SCALE = PAGE_W_PX / 441.0  # PDF page width in pts
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    img2 = Image.fromarray(arr.copy())
    draw = ImageDraw.Draw(img2)

    for bbox in locs:
        x0 = int(bbox[0] * SCALE)
        y0 = int(bbox[1] * SCALE)
        x1 = int(bbox[2] * SCALE)
        y1 = int(bbox[3] * SCALE)
        # Erase rect: narrow (to avoid clipping adjacent letters) but tall
        # enough to fully cover the diamond glyph's vertical extent.
        bbox_h = y1 - y0 if y1 > y0 else 45
        if bbox_h > 55:
            glyph_w, glyph_h = 22, 40   # heading
        else:
            glyph_w, glyph_h = 16, 32   # body
        # The soft-hyphen char in the PDF is zero-width; the rendered glyph
        # starts at x0 and extends ~glyph_w to the right.
        ex0 = max(0, x0)
        ex1 = min(w, x0 + glyph_w)
        cy = y1 - int(bbox_h * 0.45)
        ey0 = max(0, cy - glyph_h // 2)
        ey1 = min(h, cy + glyph_h // 2)
        cx = (ex0 + ex1) // 2

        # Sample bg from horizontally-adjacent clean area (left & right of glyph)
        pad = 30
        left = arr[ey0:ey1, max(0, ex0 - pad):ex0]
        right = arr[ey0:ey1, ex1:min(w, ex1 + pad)]
        samples = []
        if left.size:
            samples.append(left)
        if right.size:
            samples.append(right)
        if samples:
            cat = np.concatenate(samples, axis=1).reshape(-1, 3)
            # Use the brightest pixels (background) — discard dark text pixels
            sums = cat.sum(axis=1)
            bright = cat[sums.argsort()[-max(1, len(cat) // 4):]]
            bg = tuple(int(c) for c in np.median(bright, axis=0))
        else:
            bg = (255, 255, 255)

        # Erase the diamond glyph
        draw.rectangle((ex0, ey0, ex1, ey1), fill=bg)

        # Sample text color from nearby dark pixels (text strokes)
        ncrop = arr[max(0, ey0 - 40):min(h, ey1 + 40),
                    max(0, ex0 - 120):min(w, ex1 + 120)].reshape(-1, 3)
        sums = ncrop.sum(axis=1)
        dark = ncrop[sums.argsort()[:max(1, len(ncrop) // 20)]]
        text_color = tuple(int(c) for c in np.median(dark, axis=0))

        # Pick font size proportional to the glyph metric height. For body
        # text (bbox ~45 px), use ~36; for headings (bbox ~60 px), use ~48.
        h_metric = y1 - y0 if y1 > y0 else 45
        if h_metric > 55:
            font_size = 56
        elif h_metric > 40:
            font_size = 38
        else:
            font_size = 32
        font = ImageFont.truetype(DEJAVU, font_size)

        hyphen = "-"
        hb = font.getbbox(hyphen)
        hw = hb[2] - hb[0]
        hh = hb[3] - hb[1]
        # Center hyphen on glyph center, with slight upward bias since the
        # bbox y range covers ascender height (hyphen sits at x-height).
        tx = cx - hw // 2 - hb[0]
        ty = cy - hh // 2 - hb[1] - int(h_metric * 0.05)
        draw.text((tx, ty), hyphen, fill=text_color, font=font)
    return img2


# ============================================================
# 1) PAGE-NUMBER REPOSITIONING (all pages)
# ============================================================

PN_PAGES_SKIP = {1}  # cover/title pages with no number


def reposition_page_number(img: Image.Image, page_num: int) -> Image.Image:
    """Overlay a bold page number in the outer-bottom corner of every page.
    Uses adaptive color (sampled from local backdrop) so it's visible against
    any background. Adds a small contrasting stroke for legibility."""
    if page_num in PN_PAGES_SKIP:
        return img
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    is_odd = page_num % 2 == 1
    pn_font = ImageFont.truetype(DEJAVU_BOLD, 38)
    s = str(page_num)
    bb = pn_font.getbbox(s)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    margin = round(0.32 * DPI)
    ty = h - margin - th
    tx = (w - margin - tw) if is_odd else margin

    # Sample local backdrop color (where the number will sit + a bit around)
    sx0 = max(0, tx - 20)
    sy0 = max(0, ty - 10)
    sx1 = min(w, tx + tw + 20)
    sy1 = min(h, ty + th + 10)
    sample = arr[sy0:sy1, sx0:sx1].reshape(-1, 3)
    avg = sample.mean(axis=0)
    luma = float(0.2126 * avg[0] + 0.7152 * avg[1] + 0.0722 * avg[2])
    if luma < 128:
        text_color = (245, 245, 245)
        stroke_color = (0, 0, 0)
    else:
        text_color = (25, 25, 25)
        stroke_color = (255, 255, 255)

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    # Draw with a thin stroke so it pops against complex backdrops
    draw.text((tx, ty), s, fill=text_color, font=pn_font,
              stroke_width=2, stroke_fill=stroke_color)
    return img


def draw_page_number_only(img: Image.Image, page_num: int) -> Image.Image:
    return reposition_page_number(img, page_num)


# ============================================================
# 2) IMAGINING FUNGAL FUTURES — remove white frame
# Pages: 30, 40, 48, 56, 64, 72
# Approach: detect the white rectangular frame around the photo, fill it with
# the page's background color (sampled from the colored top portion).
# ============================================================

FUNGAL_PAGES = {30, 40, 48, 56, 64, 72}


def remove_white_frame(img: Image.Image) -> Image.Image:
    """Remove white margin/frame surrounding the photo. Find the photo's
    bounding box (non-white content in lower half) and fill ONLY the surrounding
    frame area with the page's colored background. Photo content untouched."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]

    # Sample the page's background color from the upper portion (above photo,
    # contains the title text on a colored bg).
    upper_bg = arr[int(h * 0.04):int(h * 0.28), int(w * 0.04):int(w * 0.96)].copy()
    luma = upper_bg.mean(axis=2)
    valid = (luma > 80) & (luma < 245)
    if valid.any():
        bg_color = tuple(int(c) for c in np.median(upper_bg[valid], axis=0))
    else:
        bg_color = (200, 200, 200)

    # Find the photo bounding box: non-white pixels in the lower 55% of page.
    lower_y = int(h * 0.45)
    lower = arr[lower_y:]
    non_white = ~((lower[..., 0] > 240) & (lower[..., 1] > 240) & (lower[..., 2] > 240))
    rows_have = non_white.any(axis=1)
    cols_have = non_white.any(axis=0)
    if not rows_have.any() or not cols_have.any():
        return img
    # Add small inset to avoid stray pixels
    photo_y0 = lower_y + int(np.argmax(rows_have))
    photo_y1 = h - int(np.argmax(rows_have[::-1]))
    photo_x0 = int(np.argmax(cols_have))
    photo_x1 = w - int(np.argmax(cols_have[::-1]))

    # Now: fill the FRAME (white margin around photo bbox) with bg_color.
    # That's the four rectangles outside the photo bbox in the lower portion.
    # Top frame band:
    arr[lower_y:photo_y0, :] = bg_color
    # Bottom frame band:
    arr[photo_y1:, :] = bg_color
    # Left frame strip (between page edge and photo):
    arr[photo_y0:photo_y1, :photo_x0] = bg_color
    # Right frame strip:
    arr[photo_y0:photo_y1, photo_x1:] = bg_color
    return Image.fromarray(arr)


# ============================================================
# 3) p77 — title + center vertical alignment
# ============================================================

def rebuild_p77(img: Image.Image) -> Image.Image:
    """Non-destructive vertical centering on p77.

    Approach:
      1. cv2.inpaint() removes the original italic poem text — the surrounding
         pink/lavender gradient is reconstructed naturally.
      2. Re-render the poem text in DejaVu Italic at a vertically centered
         position (centered on the gradient region above the mushroom imagery).
      3. Overlay the new title above.
    The mushroom imagery in the lower portion is preserved intact.
    """
    import cv2

    w, h = img.size
    arr = np.array(img.convert("RGB"))

    # Region holding the original italic poem (upper third + a bit beyond
    # to ensure no descenders or trailing lines remain).
    TXT_Y0, TXT_Y1 = 250, 1350
    TXT_X0, TXT_X1 = 80, w - 80

    region = arr[TXT_Y0:TXT_Y1, TXT_X0:TXT_X1]
    luma = region.mean(axis=2)
    text_mask_local = (luma < 165).astype(np.uint8) * 255
    text_mask_local = cv2.dilate(text_mask_local,
                                 np.ones((7, 7), np.uint8),
                                 iterations=2)
    full_mask = np.zeros(arr.shape[:2], dtype=np.uint8)
    full_mask[TXT_Y0:TXT_Y1, TXT_X0:TXT_X1] = text_mask_local

    inpainted = cv2.inpaint(arr, full_mask, inpaintRadius=12,
                            flags=cv2.INPAINT_TELEA)
    img = Image.fromarray(inpainted)
    draw = ImageDraw.Draw(img)

    # Re-render poem text. Use DejaVu Serif Italic for a nice flowing feel.
    body_font = ImageFont.truetype(DEJAVU_SERIF_ITAL, 42)
    title_font = ImageFont.truetype(SERIOUSLY_FONT, 84)
    body_text = (
        "Root into your body, and feel the coherence of the billions of "
        "microscopic organisms that comprise you. Root into your community, "
        "and dream of new ways we can merge our voices in collective wisdom. "
        "Root into the land, and tread lightly on this precious planet, for "
        "she is our great mother and our only home."
    )
    title_text = "A parting thought from the mushrooms:"

    inner_w = (TXT_X1 - TXT_X0) - 80
    body_lines = text_lines_wrap(body_text, body_font, inner_w)
    body_leading = int(42 * 1.55)
    body_h = len(body_lines) * body_leading

    # Vertically center title + body in the gradient zone (above mushrooms)
    GRAD_TOP = round(0.5 * DPI)   # 0.5"
    GRAD_BOT = 1500
    title_h = title_font.getbbox(title_text)[3] - title_font.getbbox(title_text)[1]
    gap = 40
    total_h = title_h + gap + body_h
    block_top = (GRAD_TOP + GRAD_BOT) // 2 - total_h // 2
    if block_top < GRAD_TOP:
        block_top = GRAD_TOP

    # Title centered horizontally with soft drop shadow
    tb = title_font.getbbox(title_text)
    t_w = tb[2] - tb[0]
    title_x = (w - t_w) // 2
    draw.text((title_x + 2, block_top + 2), title_text,
              fill=(255, 255, 255), font=title_font)
    draw.text((title_x, block_top), title_text,
              fill=(110, 50, 100), font=title_font)

    # Body lines centered horizontally
    body_y = block_top + title_h + gap
    body_x_pad = (w - inner_w) // 2
    for line in body_lines:
        b = body_font.getbbox(line)
        bw = b[2] - b[0]
        draw.text(((w - bw) // 2, body_y),
                  line, fill=(70, 40, 80), font=body_font)
        body_y += body_leading
    return img


# ============================================================
# 4) p13 — add ChatGPT sentence
# ============================================================

def patch_p13(img: Image.Image) -> Image.Image:
    """Add 'ChatGPT prompts were used only to generate the voice of the
    mushrooms…' sentence to Notes from Creators. Insert it after the
    'oriented toward a Web3 audience' phrase. We do this as a small overlay
    box in the lower portion of the existing text area."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img, "RGBA")

    # Add an italicized note as a box at the bottom of the text area.
    box_x0 = round(0.6 * DPI)
    box_x1 = w - round(0.6 * DPI)
    box_y0 = h - round(1.3 * DPI)
    box_y1 = h - round(0.7 * DPI)
    draw.rounded_rectangle((box_x0, box_y0, box_x1, box_y1),
                           radius=20, fill=(255, 255, 255, 240))
    note_font = ImageFont.truetype(DEJAVU_ITAL, 28)
    note = ('Note: ChatGPT prompts were used only to generate the '
            '"voice of the mushrooms" at the beginning and end of the book.')
    inner_w = box_x1 - box_x0 - 60
    y = box_y0 + 30
    for line in text_lines_wrap(note, note_font, inner_w):
        draw.text((box_x0 + 30, y), line, fill=(50, 50, 60, 255), font=note_font)
        y += int(28 * 1.4)
    return img


# ============================================================
# 5) p25 — emphasize 1, 2, 3 perspectives
# ============================================================

def patch_p25(img: Image.Image) -> Image.Image:
    """Erase the original 'This book will cover each of these patterns…'
    paragraph and redraw it as an emphasised numbered list."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]

    # Original paragraph occupies roughly y=200..490, full text width
    erase_y0, erase_y1 = 200, 500
    erase_x0, erase_x1 = round(0.5 * DPI), w - round(0.5 * DPI)
    # White page background, so simple flood fill with white works.
    arr[erase_y0:erase_y1, erase_x0:erase_x1] = (255, 255, 255)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Body font sized to match book interior body
    body_font = ImageFont.truetype(DEJAVU, 32)
    bold_font = ImageFont.truetype(DEJAVU_BOLD, 32)
    leading = int(32 * 1.45)
    text_color = (40, 40, 40)
    accent = (180, 100, 30)  # warm orange for numbers

    inner_x = erase_x0
    inner_w = erase_x1 - erase_x0
    indent = 60  # for list continuation

    y = erase_y0 + 8
    intro = "This book will cover each of these patterns in turn:"
    draw.text((inner_x, y), intro, fill=text_color, font=body_font)
    y += leading + 8

    items = [
        "from a mycelial mindset to understand how mushrooms demonstrate them",
        "looking at a few myco-mimetic examples of that pattern at work in the Web3 space",
        "ending with some imaginative provocations of what a more fungal future could look like in Web3 and beyond.",
    ]
    for i, txt in enumerate(items, start=1):
        # Number (bold, accent color)
        num_str = f"{i}."
        draw.text((inner_x, y), num_str, fill=accent, font=bold_font)
        # Body wrap with indent
        body_x = inner_x + indent
        body_w = inner_w - indent
        for line in text_lines_wrap(txt, body_font, body_w):
            draw.text((body_x, y), line, fill=text_color, font=body_font)
            y += leading
        y += 4  # extra gap between items
    return img


# ============================================================
# 6) p46 — fix premature line break in QF paragraph
# Approach: locate "but it" line and the wider lines below; apply a small
# repaint. Simplest: leave alone but add an inset text overlay correcting wrap.
# Real fix needs re-typeset; punt with no-op + flag.
# ============================================================

def patch_p46(img: Image.Image) -> Image.Image:
    return img  # acknowledge; visual reflow needs InDesign


def add_buchman_to_p11(img: Image.Image) -> Image.Image:
    """Add Ethan Buchman quote to the existing praise page p11, styled to
    match the four other quotes on the page (sans-serif, dark grey body,
    bold attribution centered)."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img, "RGBA")

    # Quote box at bottom of page, white BG to match existing white quote frame
    box_x0 = round(0.6 * DPI)
    box_x1 = w - round(0.6 * DPI)
    box_y0 = h - round(2.0 * DPI)
    box_y1 = h - round(0.55 * DPI)
    draw.rounded_rectangle((box_x0, box_y0, box_x1, box_y1),
                           radius=14, fill=(255, 255, 255, 252))

    # Match style of existing quotes: sans-serif, dark grey body, bold centered attr
    qfont = ImageFont.truetype(DEJAVU, 30)
    afont = ImageFont.truetype(DEJAVU_BOLD, 28)
    text_color = (35, 35, 38, 255)
    inner_w = (box_x1 - box_x0) - 80
    qx = box_x0 + 40
    qy = box_y0 + 30
    quote = ('"Mycelial networks are the foundation from which natural systems thrive. '
             'Obligation networks are the foundation from which social systems thrive. '
             'MycoFi is a beautiful recognition of the confluence of the natural and '
             'social worlds, of our mutual interdependence, of our obligations to take '
             'care of the planet and each other, and of how much more we still have to '
             'learn from the humble mushroom."')
    attr = "Ethan Buchman, co-founder of Cosmos and CEO of Informal Systems"
    qlead = int(30 * 1.30)
    for line in text_lines_wrap(quote, qfont, inner_w):
        draw.text((qx, qy), line, fill=text_color, font=qfont)
        qy += qlead
    qy += 10
    # Attribution centered horizontally within the box
    ab = afont.getbbox(attr)
    aw = ab[2] - ab[0]
    draw.text((box_x0 + (box_x1 - box_x0 - aw) // 2, qy),
              attr, fill=text_color, font=afont)
    return img


def rebuild_toc_p9(img: Image.Image) -> Image.Image:
    """Rebuild the table of contents page: larger font, centered on page,
    updated page numbers (incremented by 1 to reflect Praise page insertion)."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    # Erase the entire content area (white BG anyway)
    safe_top = round(0.5 * DPI)
    safe_bot = h - round(0.5 * DPI)
    arr[safe_top:safe_bot, round(0.4 * DPI):w - round(0.4 * DPI)] = (255, 255, 255)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Title CONTENTS in serif italic centered at top
    title_font = ImageFont.truetype(SERIOUSLY_FONT, 110)
    title = "Contents"
    tb = title_font.getbbox(title)
    title_y = round(0.95 * DPI)
    draw.text(((w - (tb[2] - tb[0])) // 2, title_y),
              title, fill=(60, 50, 50), font=title_font)

    # TOC entries (original page numbers — no insertion shift)
    entries = [
        ("A Note from the Creators", 12, False),
        ("Foreword", 16, False),
        ("Uncovering Nature's Economic Blueprints", 20, False),
        ("Mycelial Design Patterns", 24, False),
        ("Design Pattern 1: Network Infrastructure", 26, True),
        ("Design Pattern 2: Fractal Nature", 34, True),
        ("Design Pattern 3: Emergent Coordination", 44, True),
        ("Design Pattern 4: Dynamic Flow", 52, True),
        ("Design Pattern 5: Mutual Reciprocity", 60, True),
        ("Design Pattern 6: Polycentric Pluralism", 68, True),
        ("Join the Mycelial Revolution", 74, False),
        ("Gratitude & Acknowledgments", 80, False),
        ("Appendix", 82, False),
    ]

    entry_font = ImageFont.truetype(DEJAVU_BOLD, 38)
    sub_font = ImageFont.truetype(DEJAVU, 36)
    pn_font = ImageFont.truetype(DEJAVU, 36)

    # Layout: centered column. Width chosen so the longest entry + page number
    # comfortably fits, with margin between text and pn column.
    col_w = round(4.6 * DPI)
    col_x = (w - col_w) // 2
    pn_col_x = col_x + col_w  # right edge for page-number alignment

    y = title_y + (tb[3] - tb[1]) + 100
    line_gap = 72

    for label, pn, indent in entries:
        f = sub_font if indent else entry_font
        x = col_x + (50 if indent else 0)
        draw.text((x, y), label, fill=(40, 40, 40), font=f)
        s = str(pn)
        bb = pn_font.getbbox(s)
        draw.text((pn_col_x - (bb[2] - bb[0]), y), s, fill=(70, 70, 70), font=pn_font)
        y += line_gap

    # (Original page number "9" is outside our erase area and remains.)
    return img


# ============================================================
# 7) Insert "Praise for" page with full Stamets + Buchman
# Build a new full page from scratch.
# ============================================================

def build_praise_insert_page() -> Image.Image:
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), (250, 244, 232))  # warm cream
    draw = ImageDraw.Draw(img)

    # Decorative top band
    draw.rectangle((0, 0, PAGE_W_PX, 36), fill=(120, 60, 80))

    title_font = ImageFont.truetype(SERIOUSLY_FONT, 110)
    title = "Praise for Exploring MycoFi"
    tb = title_font.getbbox(title)
    draw.text(((PAGE_W_PX - (tb[2] - tb[0])) // 2, 200),
              title, fill=(70, 40, 60), font=title_font)

    quotes = [
        ('"MycoFi beautifully illustrates and underscores that mycelium\'s '
         'design is borne from the universe. The organization of mycelium is '
         'a previously proven evolutionarily successful structure at scales '
         'found throughout nature. Its inherent wisdom of sharing resources, '
         "building guilds - and thus - communities is an economic and "
         'cosmological model for us to depend upon and learn from. From these '
         'mycelial-like structures, we have a launching pad for our continued '
         'evolution based on cooperation, resilience, and discovery. The very '
         'nature of mycelium allows it to evolve and not only respond to '
         'catastrophia but to build systems that are highly adaptive and '
         'ever-lasting. By learning from mycelium, our species can achieve '
         'the next quantum level in our evolution."',
         "Paul Stamets, renowned mycologist and author of Mycelium Running"),
        ('"Mycelial networks are the foundation from which natural systems '
         'thrive. Obligation networks are the foundation from which social '
         'systems thrive. MycoFi is a beautiful recognition of the confluence '
         'of the natural and social worlds, of our mutual interdependence, of '
         'our obligations to take care of the planet and each other, and of '
         'how much more we still have to learn from the humble mushroom."',
         "Ethan Buchman, co-founder of Cosmos and CEO of Informal Systems"),
    ]

    qfont = ImageFont.truetype(DEJAVU_SERIF_ITAL, 36)
    afont = ImageFont.truetype(DEJAVU_SERIF_BOLD, 32)
    inner_w = PAGE_W_PX - 2 * round(0.85 * DPI)
    x = round(0.85 * DPI)
    y = 430
    qlead = int(36 * 1.40)
    alead = int(32 * 1.30)

    for q, attr in quotes:
        for line in text_lines_wrap(q, qfont, inner_w):
            draw.text((x, y), line, fill=(40, 30, 30), font=qfont)
            y += qlead
        y += 12
        # right-aligned attribution
        ab = afont.getbbox(attr)
        aw = ab[2] - ab[0]
        draw.text((x + inner_w - aw, y), attr, fill=(110, 60, 60), font=afont)
        y += alead + 60

    # Decorative bottom band
    draw.rectangle((0, PAGE_H_PX - 36, PAGE_W_PX, PAGE_H_PX), fill=(120, 60, 80))
    return img


# ============================================================
# 8) p82 — bigger appendix title; swap citations 11 & 12
# ============================================================

def rebuild_p82_p83(orig82: Image.Image, orig83: Image.Image):
    """Re-typeset the appendix on two clean pages with larger title and
    citations 11 and 12 swapped (per user)."""
    # Real citations from book (verified via pdftotext on original).
    # Citations 11 and 12 SWAPPED per user (originals were backwards).
    citations = [
        ("1", "Mycelium Running, Paul Stamets: https://fungi.com/products/mycelium-running"),
        ("2", "Entangled Life, Merlin Sheldrake: https://www.merlinsheldrake.com/entangled-life"),
        ("3", "From Monoculture to Permaculture Currencies: A Glimpse of the Myco-Economic Future, Jeff Emmett: https://allthingsdecent.substack.com/p/mycoeconomics-and-permaculture-currencies"),
        ("4", "Toward an Ecological Monetary Theory, Joe Ament: https://www.mdpi.com/2071-1050/11/3/923"),
        ("5", "Bitcoin is a Decentralized Organism (Mycelium), Brandon Quittem: https://medium.com/@BrandonQuittem/bitcoin-is-a-decentralized-organism-mycelium-part-1-3-6ec58cdcfaa6"),
        ("6", "The Dawn of the Regenaissance, Jessica Zartler: https://jessicazartler.medium.com/the-dawn-of-the-regenaissance-a3be40da5331"),
        ("7", "Hyphal and Mycelial consciousness: the Concept of the Fungal Mind, Nicholas P. Money: https://pubmed.ncbi.nlm.nih.gov/33766303/"),
        ("8", 'The Computational Boundary of a "Self": Developmental Bioelectricity Drives Multicellularity and Scale-Free Cognition, Michael Levin: https://www.frontiersin.org/articles/10.3389/fpsyg.2019.02688/full'),
        ("9", "Disambiguating Autonomy: Ceding Control in Favor of Coordination, Michael Zargham et al: https://blog.block.science/disambiguating-autonomy/"),
        ("10", "Quorum Sensing: its Role in Microbial Social Networking, Angkita Sharma et al: https://www.sciencedirect.com/science/article/pii/S0923250820300577"),
        # SWAPPED (originals were 11=Physarum, 12=Ecological Memory):
        ("11", "Ecological Memory and Relocation Decisions in Fungal Mycelial Networks, Yu Fukasawa, et al: https://www.nature.com/articles/s41396-019-0536-3"),
        ("12", "Physarum on the faculty: https://www.hampshire.edu/academics/faculty/physarum-mold"),
        ("13", "Gitcoin Grants: https://grants.gitcoin.co/"),
        ("14", "Quadratic Funding: https://www.wtfisqf.com/"),
        ("15", "Stellar Development Foundation: https://stellar.org/foundation"),
        ("16", "BlockScience: https://block.science/"),
        ("17", "Introducing Neural Quorum Governance, Danilo Bernardineli and Jakob Hackel: https://blog.block.science/introducing-neural-quorum-governance/"),
        ("18", "Exploring Bonding Curves: Differentiating Primary and Secondary Automated Market Makers, Jeff Emmett et al: https://mirror.xyz/0x8fF6Fe58b468B1F18d2C54e2B0870b4e847C730d/1Pxl_fbIPifIQ4_y0xoJGZGEk70qfOM3Gi9nWycm-8k"),
        ("19", "Mycorrhizal Markets, Firms, and Co-Ops, Ronald Noë and E. Toby Kiers: https://tobykiers.com/wp-content/uploads/2018/10/Noe-Kiers-2018-Mycorrhizal-markets-TREE.pdf"),
        ("20", "Mycorrhizal Mycelium as a Global Carbon Pool, Heidi-Jayne Hawkins: https://pubmed.ncbi.nlm.nih.gov/37279689/"),
        ("21", "Fantastic Fungi, Paul Stamets et al: https://fungi.com/products/fantastic-fungi"),
        ("22", "Inverter Network: https://www.inverter.network/"),
        ("23", "Drips Network: https://www.drips.network/"),
        ("24", "Conviction Voting: A Novel Continuous Decision Making Alternative to Governance, Jeff Emmett: https://blog.giveth.io/conviction-voting-a-novel-continuous-decision-making-alternative-to-governance-aa746cfb9475"),
        ("25", "Commons Stack: https://www.commonsstack.org/"),
        ("26", "1Hive: https://1hive.org/"),
        ("27", "Token Engineering Commons: https://tecommons.org/"),
        ("28", "Reciprocal Rewards Stabilize Cooperation in the Mycorrhizal Symbiosis, E. Toby Kiers et al: https://pubmed.ncbi.nlm.nih.gov/21836016/"),
        ("29", "Finding the Mother Tree, Suzanne Simard: https://suzannesimard.com/finding-the-mother-tree-book/"),
        ("30", "Mycorrhizal Fungi Respond to Resource Inequality by Moving Phosphorus from Rich to Poor Patches Across Networks, Matthew D. Whiteside et al: https://tobykiers.com/wp-content/uploads/2019/06/Current-Biology-Whiteside-2019.pdf"),
        ("31", "Indigenomics Institute: https://indigenomicsinstitute.com/"),
        ("32", "A brief history of the Hiawatha Belt by the Onondaga Nation: https://www.onondaganation.org/culture/wampum/hiawatha-belt/"),
        ("33", "Collaborative Finance: https://cofi.informal.systems/about"),
        ("34", "Liquidity-Saving through Obligation-Clearing and Mutual Credit: An Effective Monetary Innovation for SMEs in Times of Crisis, Tomaž Fleischman et al: https://www.mdpi.com/1911-8074/13/12/295"),
        ("35", "Giveth Galaxy: https://giveth.io/"),
        ("36", "What a Mushroom Lives For: Matsutake and the Worlds They Make, Michael Hathaway: https://www.michaeljhathaway.net/what-a-mushroom-lives-for"),
        ("37", "If Women Counted: A New Feminist Economics, Marilyn Waring: https://www.marilynwaring.com/publications/if-women-counted.asp"),
        ("38", "Mushrooms as Rainmakers: How Spores Act as Nuclei for Raindrops, Maribeth O. Hassett et al: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4624964/"),
        ("39", "Radical xChange: https://www.radicalxchange.org/"),
        ("40", "Plural Voting: https://www.radicalxchange.org/concepts/plural-voting/"),
        ("41", "Grassroots Economics: https://www.grassrootseconomics.org/"),
        ("42", "Circles Coop: https://joincircles.net/"),
        ("43", "Community Asset Vouchers: https://www.grassrootseconomics.org/pages/how-it-works"),
        ("44", "In Search of Mycotopia, Doug Bierend: https://www.chelseagreen.com/product/in-search-of-mycotopia-paperback/"),
        ("45", "The Mushroom at the End of the World, Anna Lowenhaupt-Tsing: https://press.princeton.edu/books/paperback/9780691220550/the-mushroom-at-the-end-of-the-world"),
        ("46", "Altered States of Monetary Consciousness, Brett Scott: https://alteredstatesof.money/"),
        ("47", "Braiding Sweetgrass, Robin Wall Kimmerer: https://www.robinwallkimmerer.com/books"),
    ]

    title_font = ImageFont.truetype(SERIOUSLY_FONT, 100)
    head_text = "APPENDIX"

    intro_font = ImageFont.truetype(DEJAVU, 36)
    intro = (
        "References to sources cited within the text of this book can be "
        "found below. A digital version of these references can also be "
        "found at bit.ly/mycofi-appendix, or via this QR code:"
    )

    cite_font = ImageFont.truetype(DEJAVU, 30)
    leading = int(30 * 1.45)

    pages = []
    # Page 1 (index → 82): title + intro + first half of citations
    img = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Title
    tb = title_font.getbbox(head_text)
    draw.text((round(0.6 * DPI), round(0.8 * DPI)), head_text,
              fill=(50, 70, 50), font=title_font)
    # Intro
    intro_x = round(0.6 * DPI)
    intro_y = round(0.8 * DPI) + (tb[3] - tb[1]) + 50
    intro_w = PAGE_W_PX - 2 * intro_x
    intro_y = draw_paragraph(draw, intro_x, intro_y, intro, intro_font,
                             (40, 40, 40), intro_w, leading_ratio=1.40)

    # Compute split point: target ~half of citations on each page
    cites_y = intro_y + 30
    max_cite_y = PAGE_H_PX - round(1.0 * DPI)
    # Render citations until max_y, then continue on next page
    avail_w = PAGE_W_PX - 2 * round(0.6 * DPI)
    num_col_w = 70

    def draw_citation(d, x, y, num, txt, max_w):
        d.text((x, y), num + ".", fill=(80, 80, 80), font=cite_font)
        body_x = x + num_col_w
        body_w = max_w - num_col_w
        for line in text_lines_wrap(txt, cite_font, body_w):
            d.text((body_x, y), line, fill=(30, 30, 30), font=cite_font)
            y += leading
        return y + int(leading * 0.25)

    cy = cites_y
    idx = 0
    for i, (n, t) in enumerate(citations):
        # Estimate height
        lines = text_lines_wrap(t, cite_font, avail_w - num_col_w)
        h_est = len(lines) * leading + int(leading * 0.25)
        if cy + h_est > max_cite_y:
            idx = i
            break
        cy = draw_citation(draw, intro_x, cy, n, t, avail_w)
    else:
        idx = len(citations)
    img = draw_page_number_only(img, 82)
    pages.append(img)

    # Page 2 (index → 83): remaining citations
    img2 = Image.new("RGB", (PAGE_W_PX, PAGE_H_PX), (255, 255, 255))
    d2 = ImageDraw.Draw(img2)
    cy2 = round(0.6 * DPI)
    for i in range(idx, len(citations)):
        n, t = citations[i]
        lines = text_lines_wrap(t, cite_font, avail_w - num_col_w)
        h_est = len(lines) * leading + int(leading * 0.25)
        if cy2 + h_est > PAGE_H_PX - round(0.6 * DPI):
            break
        cy2 = draw_citation(d2, intro_x, cy2, n, t, avail_w)

    img2 = draw_page_number_only(img2, 83)
    pages.append(img2)
    return pages


# ============================================================
# 9) p78 — Gitcoin sticker -> "FunG what matters?", larger QR
# ============================================================

def patch_p78(img: Image.Image) -> Image.Image:
    """No-op: FunG sticker reverted per user feedback."""
    return img


# ============================================================
# Driver
# ============================================================

def process_all():
    pages_in = sorted(os.listdir(PAGES_DIR))
    out_pages = []
    for fname in pages_in:
        m = re.match(r"p-(\d+)\.png", fname)
        if not m:
            continue
        page_num = int(m.group(1))
        img = Image.open(os.path.join(PAGES_DIR, fname)).convert("RGB")

        # Fix soft-hyphen rendering on all affected pages first (so it gets
        # caught even on pages we otherwise leave alone)
        img = fix_soft_hyphens(img, page_num)

        # Per-page edits
        if page_num in FUNGAL_PAGES:
            img = remove_white_frame(img)

        if page_num == 9:
            img = rebuild_toc_p9(img)
        if page_num == 11:
            img = add_buchman_to_p11(img)
        if page_num == 13:
            img = patch_p13(img)
        if page_num == 25:
            img = patch_p25(img)
        if page_num == 46:
            img = patch_p46(img)
        if page_num == 77:
            img = rebuild_p77(img)
        if page_num == 78:
            img = patch_p78(img)

        img = reposition_page_number(img, page_num)
        out_pages.append(img)

    # Replace last 2 pages with rebuilt appendix.
    new_appendix = rebuild_p82_p83(out_pages[-2], out_pages[-1])
    new_appendix[0] = reposition_page_number(new_appendix[0], len(out_pages) - 1)
    new_appendix[1] = reposition_page_number(new_appendix[1], len(out_pages))
    out_pages[-2] = new_appendix[0]
    out_pages[-1] = new_appendix[1]

    print(f"Total pages: {len(out_pages)}")
    # Save individual pages for inspection
    for i, p in enumerate(out_pages, start=1):
        p.save(os.path.join(OUT_DIR, f"p-{i:02d}.png"))

    # Combine into PDF
    first, *rest = out_pages
    first.save(OUT_PDF, "PDF", resolution=DPI, save_all=True, append_images=rest)
    print(f"Wrote {OUT_PDF}")


if __name__ == "__main__":
    process_all()
