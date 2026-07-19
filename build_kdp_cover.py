"""Rebuild Exploring MycoFi cover for KDP 6x9 (83-page).

- Correct KDP dimensions (12.4575" x 9.25") with full bleed
- Mixed-case "Exploring MycoFi" title (front + spine), SeriouslyNostalgic
- Authors stacked bottom-right of front cover
- Back cover fully re-typeset with larger body font
- Back endorsements: Rushkoff, Case, summarized Stamets (Buchman moved to interior)
- QR code + "mycofi.earth/buy-it-forward" caption and ISBN barcode at back-cover bottom
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import numpy as np
import textwrap

SRC_PNG = "/tmp/cover_spread_600-1.png"
COVER_DIR = "/mnt/c/Users/jeffe/Downloads/COVER_Exploring Mycofi_ Mycelial Design Patterns for Web3 and Beyond"
SERIOUSLY_FONT = os.path.join(COVER_DIR, "Document fonts/SeriouslyNostalgic-Regular.otf")
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_ITAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"

QR_PNG = "/home/jeffe/Github/mycofi-earth-website/public/buy-it-forward-qr.png"
BARCODE_PNG = "/mnt/c/Users/jeffe/Downloads/Screenshot 2026-05-03 191420.png"

OUT_PDF = "/home/jeffe/Github/Exploring-MycoFi-Book/cover_kdp_6x9.pdf"

# KDP target geometry (83-page 6x9 cream paperback)
DPI = 300
TRIM_W = 6.0
TRIM_H = 9.0
BLEED = 0.125
SPINE_W = 0.2075
SPREAD_W = 2 * TRIM_W + SPINE_W + 2 * BLEED  # 12.4575"
SPREAD_H = TRIM_H + 2 * BLEED                # 9.25"

each_cover_w = TRIM_W + BLEED                # 6.125"

px_w = round(SPREAD_W * DPI)
px_h = round(SPREAD_H * DPI)
each_cover_w_px = round(each_cover_w * DPI)
spine_w_px = px_w - 2 * each_cover_w_px

print(f"Spread: {SPREAD_W}\" x {SPREAD_H}\" -> {px_w} x {px_h} px @ {DPI} DPI")
print(f"Each cover: {each_cover_w_px}px, spine: {spine_w_px}px")

src = Image.open(SRC_PNG).convert("RGB")
sw, sh = src.size
print(f"Source: {sw} x {sh}")

# --- Split source spread at 50% ---
sx_split = sw // 2
back_src = src.crop((0, 0, sx_split, sh))
front_src = src.crop((sx_split, 0, sw, sh))

back = back_src.resize((each_cover_w_px, px_h), Image.LANCZOS)
front = front_src.resize((each_cover_w_px, px_h), Image.LANCZOS)

# ============================================================
# BACK COVER: erase boxes, redraw description + endorsements + QR + barcode
# ============================================================

# Sample dark neuron texture from areas ABOVE the boxes (top safe band)
back_arr = np.array(back)
# Texture donor: top band rows 0-130 (above yellow box) is mostly neuron texture
neuron_band = back_arr[0:120].copy()

# Erase a generous region covering the existing yellow + white boxes.
# Yellow box bounds were ~rows 150-1180, cols 100-1740.
# White box ~rows 1219-2025.
ERASE_X0, ERASE_X1 = 80, 1760
ERASE_Y0, ERASE_Y1 = 130, 2680  # to bottom (covers also where barcode goes)
band_h = neuron_band.shape[0]
flip = False
y = ERASE_Y0
while y < ERASE_Y1:
    take = min(band_h, ERASE_Y1 - y)
    src_band = neuron_band[:take, ERASE_X0:ERASE_X1]
    if flip:
        src_band = src_band[::-1]
    back_arr[y:y + take, ERASE_X0:ERASE_X1] = src_band
    y += take
    flip = not flip
back = Image.fromarray(back_arr)

# Draw new content on back
bd = ImageDraw.Draw(back, "RGBA")

# --- Back cover safe area ---
B_LEFT = 113   # 0.375"
B_RIGHT = 1700 # ~5.67"
B_TOP = 113
B_BOTTOM = 2675

# Body font matches book interior body text (~10pt -> ~38 px @ 300 DPI)
BODY_PX = 38          # ~10pt — matches book interior
BODY_BOLD_PX = 38
ITALIC_PX = 36
HEADING_PX = 46
LEAD_RATIO = 1.40     # generous leading like the book interior

font_body = ImageFont.truetype(DEJAVU, BODY_PX)
font_body_b = ImageFont.truetype(DEJAVU_BOLD, BODY_BOLD_PX)
font_body_i = ImageFont.truetype(DEJAVU_ITAL, ITALIC_PX)
font_head = ImageFont.truetype(DEJAVU_BOLD, HEADING_PX)

YELLOW = (245, 220, 75, 255)
DARK_TEXT = (24, 24, 26, 255)


def text_lines_wrap(text, font, max_w):
    """Word-wrap text to fit max_w pixels, returning list of lines."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        bbox = font.getbbox(trial)
        if bbox[2] - bbox[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_paragraph(draw, x, y, text, font, color, max_w, leading=None):
    """Draw a wrapped paragraph; return new y after the paragraph."""
    if leading is None:
        leading = int(font.size * LEAD_RATIO)
    for line in text_lines_wrap(text, font, max_w):
        draw.text((x, y), line, fill=color, font=font)
        y += leading
    return y


# --- Yellow box (top) — first measure content, then size box to fit ---
YELLOW_X0, YELLOW_X1 = B_LEFT, B_RIGHT
YELLOW_Y0 = 150
PADDING = 50

inner_w = (YELLOW_X1 - YELLOW_X0) - 2 * PADDING
ix = YELLOW_X0 + PADDING
iy_start = YELLOW_Y0 + PADDING

# Para 1: title-bold lead
para1_lead = "Exploring MycoFi: Mycelial Design Patterns for Web3 and Beyond "
para1_rest = (
    "guides readers on an underground exploration into the world wise web of "
    "mycelial networks, the most prolific producers of public goods on Earth. "
    "This book examines how the evolutionary adaptability of fungi could help "
    "us imagine biomimetic alternatives to status-quo economic systems that "
    "demand infinite growth on a finite planet."
)

# Render bold lead inline with regular body. Easiest: build a single string and
# render with two fonts on the same line by splitting at the first sentence.
# Simpler approach: render lead in bold paragraph, then continue regular.
# But we want them on the same paragraph flow. Hand-roll wrapping.
def wrap_mixed(parts, max_w):
    """parts = list of (text, font, color). Returns list of [(x_off, text, font, color)] per line."""
    lines = []
    cur_line = []
    cur_w = 0
    space_w_per_font = {id(f): f.getbbox(" ")[2] - f.getbbox(" ")[0] for _, f, _ in parts}
    for text, font, color in parts:
        for word in text.split(" "):
            if not word:
                continue
            wb = font.getbbox(word)
            ww = wb[2] - wb[0]
            sep = space_w_per_font[id(font)] if cur_line else 0
            if cur_w + sep + ww > max_w and cur_line:
                lines.append(cur_line)
                cur_line = []
                cur_w = 0
                sep = 0
            x_off = cur_w + sep
            cur_line.append((x_off, word, font, color))
            cur_w = x_off + ww
    if cur_line:
        lines.append(cur_line)
    return lines


# --- Pre-measure yellow box content height ---
leading = int(BODY_PX * LEAD_RATIO)
intro = "MycoFi translates six design patterns of mycelial ecologies to Web3 economies:"
bullets = (
    "Network Infrastructure  •  Fractal Nature  •  Emergent Coordination\n"
    "Dynamic Flow  •  Mutual Reciprocity  •  Polycentric Pluralism"
)
para3 = (
    "If there is any hope for a transition away from extraction, domination, "
    "and planetary overshoot, towards regeneration, equity, and planetary "
    "healing, our economies must be realigned with nature's ecologies - and "
    "for that, we can't afford to ignore what mushrooms have to teach us."
)

lead_lines = wrap_mixed(
    [(para1_lead, font_body_b, DARK_TEXT), (para1_rest, font_body, DARK_TEXT)],
    inner_w,
)
intro_lines = text_lines_wrap(intro, font_body_b, inner_w)
para3_lines = text_lines_wrap(para3, font_body, inner_w)
bullets_lines = bullets.split("\n")

content_h = (
    len(lead_lines) * leading
    + int(leading * 0.4)
    + len(intro_lines) * leading
    + int(leading * 0.2)
    + len(bullets_lines) * int(ITALIC_PX * LEAD_RATIO)
    + int(leading * 0.4)
    + len(para3_lines) * leading
)
YELLOW_Y1 = YELLOW_Y0 + content_h + 2 * PADDING

# Now draw the box, then the text.
bd.rounded_rectangle(
    (YELLOW_X0, YELLOW_Y0, YELLOW_X1, YELLOW_Y1),
    radius=24,
    fill=YELLOW,
)

iy = iy_start
for line in lead_lines:
    for x_off, word, font, color in line:
        bd.text((ix + x_off, iy), word, fill=color, font=font)
    iy += leading

iy += int(leading * 0.4)

for line in intro_lines:
    bd.text((ix, iy), line, fill=DARK_TEXT, font=font_body_b)
    iy += leading
iy += int(leading * 0.2)

for bline in bullets_lines:
    bbox = font_body_i.getbbox(bline)
    bw = bbox[2] - bbox[0]
    bd.text((ix + (inner_w - bw) // 2, iy), bline, fill=DARK_TEXT, font=font_body_i)
    iy += int(ITALIC_PX * LEAD_RATIO)
iy += int(leading * 0.4)

for line in para3_lines:
    bd.text((ix, iy), line, fill=DARK_TEXT, font=font_body)
    iy += leading

# --- White box (endorsements), positioned right below yellow box ---
WHITE_X0, WHITE_X1 = B_LEFT, B_RIGHT
WHITE_Y0 = YELLOW_Y1 + 60
WHITE = (255, 255, 255, 255)

QUOTE_PX = 32
ATTR_PX = 28
font_quote = ImageFont.truetype(DEJAVU_ITAL, QUOTE_PX)
font_attr = ImageFont.truetype(DEJAVU_BOLD, ATTR_PX)
inner_w_w = (WHITE_X1 - WHITE_X0) - 2 * PADDING

quotes = [
    ('"Fungi invite us to participate in a commons-based economy where '
     'resources are metabolized, shared, and regenerated simultaneously '
     'through the very same process. MycoFi is less about how to imitate '
     'them than how to join in the dance."',
     "Douglas Rushkoff, author and host of Team Human"),
    ('"Nature is a magical long-term, stable code base, with time for revisions '
     'and optimization. Hopefully, this work will provide another reminder that '
     "the answers have always been there. Let's listen together.\"",
     "Amber Case, author of Calm Technology"),
    ('"By learning from mycelium, our species can achieve the next quantum '
     'level in our evolution."',
     "Paul Stamets, renowned mycologist and author of Mycelium Running"),
]

q_lead = int(QUOTE_PX * 1.30)
a_lead = int(ATTR_PX * 1.30)

# Pre-measure white box height
white_content_h = 0
for quote, attr in quotes:
    qlines = text_lines_wrap(quote, font_quote, inner_w_w)
    white_content_h += len(qlines) * q_lead
    white_content_h += a_lead + int(QUOTE_PX * 0.5)
WHITE_Y1 = WHITE_Y0 + white_content_h + 2 * PADDING - int(QUOTE_PX * 0.5)
bd.rounded_rectangle(
    (WHITE_X0, WHITE_Y0, WHITE_X1, WHITE_Y1),
    radius=24,
    fill=WHITE,
)

qx = WHITE_X0 + PADDING
qy = WHITE_Y0 + PADDING
for quote, attr in quotes:
    for line in text_lines_wrap(quote, font_quote, inner_w_w):
        bd.text((qx, qy), line, fill=DARK_TEXT, font=font_quote)
        qy += q_lead
    a_bbox = font_attr.getbbox(attr)
    aw = a_bbox[2] - a_bbox[0]
    bd.text((qx + inner_w_w - aw, qy), attr, fill=DARK_TEXT, font=font_attr)
    qy += a_lead + int(QUOTE_PX * 0.5)

# --- QR + caption + ISBN barcode below white box ---
QR_AREA_TOP = WHITE_Y1 + 80
QR_AREA_BOTTOM = 2700  # ~9" mark, well above bleed

# QR: prominent ~1.4" square on left; caption centered below
qr_size_px = round(1.5 * DPI)  # 1.5" = 450px
qr_img = Image.open(QR_PNG).convert("RGB").resize((qr_size_px, qr_size_px), Image.LANCZOS)
QR_X = B_LEFT
QR_Y = QR_AREA_TOP - 50  # nudge up so it fits with caption

# White rounded background behind QR for KDP scan reliability
qr_pad = 20
qr_bg_box = (QR_X - qr_pad, QR_Y - qr_pad,
             QR_X + qr_size_px + qr_pad, QR_Y + qr_size_px + qr_pad + 70)  # extra for caption
bd.rounded_rectangle(qr_bg_box, radius=20, fill=WHITE)
back.paste(qr_img, (QR_X, QR_Y))

# Caption under QR
cap_font = ImageFont.truetype(DEJAVU_BOLD, 32)
cap_text = "mycofi.earth/buy-it-forward"
cap_bbox = cap_font.getbbox(cap_text)
cap_w = cap_bbox[2] - cap_bbox[0]
cap_x = QR_X + (qr_size_px - cap_w) // 2
cap_y = QR_Y + qr_size_px + 12
bd.text((cap_x, cap_y), cap_text, fill=DARK_TEXT, font=cap_font)

# Barcode: bottom-right, 2" wide x 1.2" tall on white background
bar_w = round(2.0 * DPI)
bar_h = round(1.2 * DPI)
bar_img = Image.open(BARCODE_PNG).convert("RGB").resize((bar_w, bar_h), Image.LANCZOS)
BAR_X = B_RIGHT - bar_w
BAR_Y = QR_AREA_BOTTOM - bar_h - 20
# White rectangle behind barcode
bar_pad = 15
bd.rounded_rectangle(
    (BAR_X - bar_pad, BAR_Y - bar_pad, BAR_X + bar_w + bar_pad, BAR_Y + bar_h + bar_pad),
    radius=10, fill=WHITE,
)
back.paste(bar_img, (BAR_X, BAR_Y))

# ============================================================
# FRONT COVER: enlarge subtitle, redraw mixed-case title
# ============================================================
front_arr = np.array(front)

# --- 1) Erase + redraw title "Exploring MycoFi" (mixed case) ---
TITLE_X0, TITLE_Y0, TITLE_X1, TITLE_Y1 = 50, 220, 1340, 1010
title_h_px = TITLE_Y1 - TITLE_Y0
title_w_px = TITLE_X1 - TITLE_X0
donor_band = front_arr[0:TITLE_Y0, TITLE_X0:TITLE_X1]
band_h = donor_band.shape[0]
filled = np.zeros((title_h_px, title_w_px, 3), dtype=front_arr.dtype)
y = 0
flip = False
while y < title_h_px:
    take = min(band_h, title_h_px - y)
    s = donor_band[:take]
    if flip:
        s = s[::-1]
    filled[y:y + take] = s
    y += take
    flip = not flip
front_arr[TITLE_Y0:TITLE_Y1, TITLE_X0:TITLE_X1] = filled

# --- 2) Erase subtitle area ---
SUB_X0, SUB_Y0, SUB_X1, SUB_Y1 = 70, 1740, 800, 1920
# Donor: thin band just above subtitle (rows ~1500-1700, dark area)
sub_donor = front_arr[1500:1740, SUB_X0:SUB_X1]
sub_band_h = sub_donor.shape[0]
sub_h_px = SUB_Y1 - SUB_Y0
sub_filled = np.zeros((sub_h_px, SUB_X1 - SUB_X0, 3), dtype=front_arr.dtype)
y = 0
flip = False
while y < sub_h_px:
    take = min(sub_band_h, sub_h_px - y)
    s = sub_donor[:take]
    if flip:
        s = s[::-1]
    sub_filled[y:y + take] = s
    y += take
    flip = not flip
front_arr[SUB_Y0:SUB_Y1, SUB_X0:SUB_X1] = sub_filled

front = Image.fromarray(front_arr)
fd = ImageDraw.Draw(front)

# Render new title (mixed case)
TITLE_PT_PX = 360
font_title = ImageFont.truetype(SERIOUSLY_FONT, TITLE_PT_PX)
TITLE_COLOR = (245, 220, 75)
fd.text((80, 230), "Exploring", fill=TITLE_COLOR, font=font_title)
fd.text((80, 230 + int(TITLE_PT_PX * 0.95)), "MycoFi",
        fill=TITLE_COLOR, font=font_title)

# Render larger subtitle (bumped from ~36 px to ~58 px)
SUB_PX = 60  # was visually ~36 px before
font_sub = ImageFont.truetype(DEJAVU_BOLD, SUB_PX)
sub_lines = ["Mycelial Design Patterns", "for Web3 and Beyond"]
sub_y = SUB_Y0 + 0
for line in sub_lines:
    fd.text((90, sub_y), line, fill=(255, 255, 255), font=font_sub)
    sub_y += int(SUB_PX * 1.15)

# ============================================================
# Spine strip
# ============================================================
edge_w = max(20, round(0.05 * DPI))
back_edge = back.crop((each_cover_w_px - edge_w, 0, each_cover_w_px, px_h))
front_edge = front.crop((0, 0, edge_w, px_h))
edge_avg = Image.blend(back_edge, front_edge, 0.5)
edge_strip = edge_avg.resize((1, px_h), Image.LANCZOS).resize(
    (spine_w_px, px_h), Image.NEAREST
)
spine_strip = edge_strip.filter(ImageFilter.GaussianBlur(radius=2))

# ============================================================
# Compose final canvas
# ============================================================
canvas = Image.new("RGB", (px_w, px_h), (10, 10, 14))
canvas.paste(back, (0, 0))
canvas.paste(spine_strip, (each_cover_w_px, 0))
canvas.paste(front, (each_cover_w_px + spine_w_px, 0))

# --- Authors on front cover (bottom-right, stacked) ---
draw = ImageDraw.Draw(canvas)
front_x0 = each_cover_w_px + spine_w_px
front_x1 = px_w
right_trim_x = front_x1 - round(BLEED * DPI)
bottom_trim_y = px_h - round(BLEED * DPI)

author_size_px = 70
font_author = ImageFont.truetype(SERIOUSLY_FONT, author_size_px)
names = ["Jeff Emmett", "Jessica Zartler"]
line_h = font_author.getbbox("Mg")[3] - font_author.getbbox("Mg")[1]
line_gap = round(line_h * 1.25)
right_margin_px = round(0.5 * DPI)
bottom_margin_px = round(0.5 * DPI)
right_x = right_trim_x - right_margin_px
y_bottom_line = bottom_trim_y - bottom_margin_px
ys = [y_bottom_line - (len(names) - 1 - i) * line_gap - line_h for i in range(len(names))]
for line, y in zip(names, ys):
    bbox = font_author.getbbox(line)
    tw = bbox[2] - bbox[0]
    x = right_x - tw - bbox[0]
    draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=font_author)
    draw.text((x, y), line, fill=(245, 220, 75), font=font_author)

# --- Spine text overlay ---
TITLE_YELLOW = (245, 220, 75)
spine_avail_px = spine_w_px - round(0.04 * DPI)


def fit_font(font_path, text, max_h_px):
    size = 10
    while size < 200:
        f = ImageFont.truetype(font_path, size)
        bbox = f.getbbox(text)
        h = bbox[3] - bbox[1]
        if h > max_h_px:
            return ImageFont.truetype(font_path, size - 1)
        size += 1
    return ImageFont.truetype(font_path, size)


title_text = "Exploring MycoFi"
author_text = "Jeff Emmett & Jessica Zartler"
title_font_spine = fit_font(SERIOUSLY_FONT, title_text, spine_avail_px)
author_font_spine = fit_font(DEJAVU_BOLD, author_text, round(spine_avail_px * 0.75))

spine_canvas = Image.new("RGBA", (px_h, spine_w_px), (0, 0, 0, 0))
sd = ImageDraw.Draw(spine_canvas)
t_bbox = title_font_spine.getbbox(title_text)
a_bbox = author_font_spine.getbbox(author_text)
t_w = t_bbox[2] - t_bbox[0]
a_w = a_bbox[2] - a_bbox[0]
top_safety_px = round(1.6 * DPI)
bottom_safety_px = round(0.5 * DPI)
title_x = top_safety_px
author_x_h = px_h - bottom_safety_px - a_w
title_y = (spine_w_px - (t_bbox[3] - t_bbox[1])) // 2 - t_bbox[1]
author_y_h = (spine_w_px - (a_bbox[3] - a_bbox[1])) // 2 - a_bbox[1]
sd.text((title_x, title_y), title_text, fill=TITLE_YELLOW + (255,), font=title_font_spine)
sd.text((author_x_h, author_y_h), author_text, fill=(255, 255, 255, 255), font=author_font_spine)
spine_text_layer = spine_canvas.rotate(-90, expand=True)
canvas_rgba = canvas.convert("RGBA")
canvas_rgba.alpha_composite(spine_text_layer, (each_cover_w_px, 0))
canvas = canvas_rgba.convert("RGB")

# Save
out_png = "/tmp/cover_kdp_6x9.png"
canvas.save(out_png, dpi=(DPI, DPI))
print(f"Wrote {out_png}")
canvas.save(OUT_PDF, "PDF", resolution=DPI)
print(f"Wrote {OUT_PDF}")
print(f"PDF page size: {SPREAD_W * 72:.2f} x {SPREAD_H * 72:.2f} pt")
