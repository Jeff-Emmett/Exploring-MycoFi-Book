"""Page-level edits from "MycoFi Book Design Edits" (Google Doc, 2026) + print fixes.

Page numbers in function names are the designer PDF's (``ORIG``) numbering, which
is also the numbering the edit list uses. Pages 1-2 (blank + grey blank) are
dropped at the end, so the printed book is numbered ``ORIG - DROPPED``.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import os

import fitz
import segno
from PIL import Image

from .fonts import Fonts, sup
from .geometry import PAGE_H, PAGE_W, TRIM_RECT
from .layout import (BODY_LEADING, BODY_SIZE, HEAD_SIZE, LINK_GREEN, TITLE_SIZE, Run,
                     draw_lines, draw_qr, fill_rect, remove_images, remove_text, rounded_rect,
                     text, wrap)

DROPPED = 2                       # orig pages 1-2 are removed
FIRST_FOLIO_ORIG = 9              # no folios on front matter before CONTENTS
# InDesign Links folder (not in the repo, 591 MB): see SOURCES.md.
LINKS = Path(os.environ.get("MYCOFI_LINKS",
                            "/mnt/c/Users/jeffe/Downloads/BOOK_Mycofi Pages_Full_Draft/Links"))
LIG = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}

TEAL = (0.0800640881061554, 0.424826443195343, 0.46405738592147827)
SPORE_YELLOW = (0.992, 0.906, 0.627)


def phys(orig: int) -> int:
    return orig - DROPPED


def recto(orig: int) -> bool:
    return orig % 2 == 1


def clean(s: str) -> str:
    """Expand ligatures. Extraction puts a phantom space after a ligature inside
    a word ("ﬁ rst"); a real word space follows it before a capital ("Jeﬀ Emmett")."""
    for k, v in LIG.items():
        s = re.sub(re.escape(k) + r" (?=[a-z])", v, s).replace(k, v)
    return s


# ---- folios ------------------------------------------------------------------

FOLIO_SIZE = 7.81
FOLIO_INSET = 46.0        # pill centre, pt from the outside and bottom trim (0.64"),
                          # clear of the 0.42" coloured frame
FOLIO_LOW = 23.0          # fallback when body text reaches the corner: on the frame
                          # band, still 0.28" inside the trim (KDP needs 0.25")


def folios(doc: fitz.Document, fonts: Fonts) -> None:
    """Replace every folio: renumber to the printed page, lift it clear of the
    trim (KDP wants text >= 0.25" inside the trim; the old folios sat at 0.21")
    and sit it on a light pill so it reads on any background colour."""
    for i, page in enumerate(doc):
        orig = i + 1
        rects = []
        for b in page.get_text("dict", clip=fitz.Rect(0, 620, PAGE_W, PAGE_H))["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    if "ConnectMono" in s["font"] and s["text"].strip().isdigit():
                        rects.append(fitz.Rect(s["bbox"]))
        if rects:
            remove_text(page, *rects)
        if orig < FIRST_FOLIO_ORIG:
            continue
        label = str(phys(orig))
        w = fonts["mono"].text_length(label, FOLIO_SIZE)
        cx = TRIM_RECT.x1 - FOLIO_INSET if recto(orig) else TRIM_RECT.x0 + FOLIO_INSET
        words = [fitz.Rect(b[:4]) for b in page.get_text("words")]
        for cy in (TRIM_RECT.y1 - FOLIO_INSET, TRIM_RECT.y1 - FOLIO_LOW):
            pill = fitz.Rect(cx - w / 2 - 5, cy - 6, cx + w / 2 + 5, cy + 6)
            if not any(pill.intersects(r) for r in words):
                break
        else:
            raise SystemExit(f"orig p{orig}: no clear spot for the folio")
        rounded_rect(page, pill, 6, fill=(1, 1, 1), opacity=0.85)
        text(page, fonts, (cx, cy + 2.6), label, font="mono", size=FOLIO_SIZE, align="center")


# ---- p6: copyright / edition -------------------------------------------------

def p6_edition(page: fitz.Page, fonts: Fonts, isbn: str | None) -> None:
    lines = ["Second edition, 2026. First published in 2025."]
    if isbn:
        lines.append(f"ISBN {isbn}")
    y = 536.0
    for s in lines:
        text(page, fonts, (101.0, y), s, size=7.81)
        y += 12.0


# ---- p9: contents --------------------------------------------------------------

def p9_contents(page: fitz.Page, fonts: Fonts, glossary_first_orig: int) -> None:
    remove_text(page, fitz.Rect(20, 150, 440, 600))
    rows = [
        ("A Note from the Creators", 12, 0), ("Foreword", 16, 0),
        ("Uncovering Nature’s Economic Blueprints", 20, 0),
        ("Mycelial Design Patterns", 24, 0),
        ("Design Pattern 1: Network Infrastructure", 26, 1),
        ("Design Pattern 2: Fractal Nature", 34, 1),
        ("Design Pattern 3: Emergent Coordination", 44, 1),
        ("Design Pattern 4: Dynamic Flow", 52, 1),
        ("Design Pattern 5: Mutual Reciprocity", 60, 1),
        ("Design Pattern 6: Polycentric Pluralism", 68, 1),
        ("Join the Mycelial Revolution", 74, 0),
        ("Gratitude & Acknowledgments", 80, 0), ("Appendix", 82, 0),
        ("Glossary", glossary_first_orig, 0),
    ]
    size, step, indent = 10.25, 22.0, 14.0
    widest = max(fonts["medium"].text_length(t, size) + indent * lvl for t, _p, lvl in rows)
    block_w = widest + 40
    area = fitz.Rect(9, 39, 411, 627)           # inner panel, trim to frame; recto
    x0 = area.x0 + (area.width - block_w) / 2
    head_y = area.y0 + (area.height - (len(rows) * step + 48)) / 2 + 14
    text(page, fonts, (x0 + block_w / 2, head_y), "CONTENTS", font="display_italic",
         size=16.0, align="center", tracking=4.2)
    y = head_y + 48
    for title, orig_page, lvl in rows:
        text(page, fonts, (x0 + indent * lvl, y), title, font="medium", size=size)
        text(page, fonts, (x0 + block_w, y), str(phys(orig_page)), size=size, align="right")
        y += step


# ---- p10-11: praise, balanced and set at body size -----------------------------

PRAISE = [
    ("“MycoFi beautifully illustrates and underscores that mycelium’s design is borne from "
     "the universe. The organization of mycelium is a previously proven evolutionarily "
     "successful structure at scales found throughout nature. Its inherent wisdom of sharing "
     "resources, building guilds - and thus - communities is an economic and cosmological "
     "model for us to depend upon and learn from. From these mycelial-like structures, we "
     "have a launching pad for our continued evolution based on cooperation, resilience, and "
     "discovery. The very nature of mycelium allows it to evolve and not only respond to "
     "catastrophia but to build systems that are highly adaptive and ever-lasting. By "
     "learning from mycelium, our species can achieve the next quantum level in our "
     "evolution.”",
     "Paul Stamets, renowned mycologist and author of Mycelium Running"),
    ("“Metaphor is a powerful tool for the imagination, giving us the scaffolding to create "
     "new structures in our minds. This book lays out a powerful mycelial metaphor to help us "
     "reimagine our financial and economic life.”",
     "Brett Scott, author of CloudMoney and Altered States of Monetary Consciousness"),
    ("“This is economics on mushrooms. The fungi kingdom is the banner bearer for "
     "regeneration. This book invites us to observe the patterns of deep fungal regeneration "
     "as we endeavor to redesign our economic relationships with mutuality, collaboration "
     "and regeneration in mind.”",
     "Greg Landua, co-founder and CEO of Regen Network"),
    ("“So glad to see how Mutualist thinking and design are being located from the roots to "
     "the emergent horizons. We can be neither pessimists nor optimists - rather be those who "
     "toil in the matter at hand committed to that which repairs the world.”",
     "Sara Horowitz, author of Mutualism: Building the Next Economy from the Ground Up"),
    ("“This book takes you on a journey to explore nature’s public goods infrastructure, and "
     "what we can learn for building the socio-technical systems of the future.\n"
     "Maybe we’ll find out we’ve been Mycopunks all along!”",
     "Angela Kreitenweis, founder of Token Engineering Academy"),
    ("“MycoFi helps us move beyond the representational thinking hindering crypto by drawing "
     "on the lessons we can learn from the ancient economic mycelial networks that have run "
     "nature for millennia. Mushrooms show us that we are and always have been the "
     "inter-connected parts of one organism that must create symbiotic ways of co-existence "
     "with ourselves and the rest of the natural world to continue surviving on a planet "
     "wrought with man-made degeneration.”",
     "Josh Davila, author of Blockchain Radicals: How Capitalism Ruined Crypto and How to Fix It"),
    ("“This book (and the community it emerges from) is a fun and playful way into the tools "
     "and mindsets of this practice, recommended especially if you are, perhaps, coming to "
     "see yourself as a confluencer, sovereignty guardian, rhizome of diplomatic gardens, "
     "steward for Mother Earth and all her children; giver of care, compassion, and "
     "integrities; practitioner of trust, choreographer of commoning; or caller of ancient, "
     "renewed and emergent memes.”",
     "Tony (OpenTony) Lai, researcher & editor, Stanford Journal of Blockchain Law & Policy"),
    ("“Great intro to how Web3 networks and other human-made systems can benefit from "
     "biomimicry and system thinking.”",
     "Shermin Voshmgir, author of Token Economy"),
    ("“MycoFi takes the reader below the surface of Web3 to explore diverse and intricate "
     "economic networks. Ecological Economics (generally) and mycelial networks "
     "(specifically) share a pluralistic view on value. The same nutrient can be both a waste "
     "product when and where it’s in excess, and a resource when and where it’s necessary for "
     "a biochemical process. Moving away from a single notion of value (money) and towards "
     "nutrients flowing over physically distributed and biologically diverse networks is a "
     "key conceptual shift from neoclassical to ecological economics.”",
     "Michael Zargham, Chief Engineer at BlockScience"),
]

PRAISE_SIZE = BODY_SIZE
PRAISE_LEADING = 11.4
PRAISE_GAP = 12.5


def _praise_block(fonts: Fonts, width: float, quote: str, who: str):
    lines = []
    for para in quote.split("\n"):
        lines += wrap([Run(para)], fonts, PRAISE_SIZE, width)
    who_lines = wrap([Run(who, "medium")], fonts, PRAISE_SIZE, width)
    height = (len(lines) + len(who_lines)) * PRAISE_LEADING + 3
    return lines, who_lines, height


def p10_p11_praise(p10: fitz.Page, p11: fitz.Page, fonts: Fonts) -> None:
    cols = {10: (p10, 56.0, 347.0), 11: (p11, 47.2, 347.0)}
    top, bottom = 194.0, 616.0
    for page, *_ in cols.values():
        remove_text(page, fitz.Rect(20, 185, 440, 600))
    blocks = [_praise_block(fonts, 347.0, q, w) for q, w in PRAISE]
    heights = [b[2] for b in blocks]
    # balance: the split that minimises the taller page
    best = min(range(1, len(blocks)),
               key=lambda k: max(sum(heights[:k]) + PRAISE_GAP * (k - 1),
                                 sum(heights[k:]) + PRAISE_GAP * (len(blocks) - k - 1)))
    for pno, chunk in ((10, blocks[:best]), (11, blocks[best:])):
        page, x, w = cols[pno]
        total = sum(b[2] for b in chunk) + PRAISE_GAP * (len(chunk) - 1)
        if total > bottom - top:
            raise SystemExit(f"praise does not fit on p{pno}: {total:.0f} > {bottom - top:.0f}")
        y = top + (bottom - top - total) / 2 + PRAISE_SIZE
        for lines, who, h in chunk:
            y = draw_lines(page, lines, fonts, PRAISE_SIZE, x, y, PRAISE_LEADING) + PRAISE_LEADING
            y = draw_lines(page, who, fonts, PRAISE_SIZE, x, y + 3, PRAISE_LEADING, width=w,
                           align="right") + PRAISE_LEADING + PRAISE_GAP


# ---- p13: note from the creators (+ AI disclosure) ------------------------------

NOTE = [
    "This book is a creative excursion into the nexus between mushrooms, economics, and "
    "technology. It explores six mycelial design patterns and their potential applications "
    "to address modern challenges in political economics, using Web3 tools as emancipatory "
    "technologies.",
    "Many of the ideas expressed in this book were inspired by countless authors, "
    "researchers, and developers, drawing from extensive bodies of research on the "
    "fascinating capabilities of mycelium and distributed ledger technologies. This book "
    "presents a fungal remix of some of those concepts, oriented toward a Web3 audience. "
    "ChatGPT prompts were used only to generate the ‘voice of the mushrooms’ at the "
    "beginning and end of the book. For those interested in further reading, you can find a "
    "series of links and references in the appendix.",
    "While we take an optimistic outlook in these pages, we aim to avoid the “appeal to "
    "nature” fallacy – the oversimplified perspective that everything natural is good for "
    "us. Instead, we seek to identify and unpack useful, pro-social patterns that could be "
    "applied in contexts where they increase collective flourishing.",
    "MycoFi is fundamentally a pluralistic and emergent meme, requiring many voices to "
    "interweave a polyphonic chorus – including those who came before, as well as those yet "
    "to come. If you feel the call to contribute to the growing folklore of mycelial "
    "solutions, we have included information on connecting with communities of change-makers "
    "in the last chapter. We offer this book as one step to an ecology of mind nurtured in "
    "the world of mycelial intelligence and all it has to teach us. There is so much more to "
    "be written, experienced, and embodied, and we warmly invite you to join in the "
    "exploration.",
]


def p13_note(page: fitz.Page, fonts: Fonts) -> None:
    remove_text(page, fitz.Rect(70, 135, 360, 600))
    y = 151.0
    for para in NOTE:
        lines = wrap([Run(para)], fonts, BODY_SIZE, 268.0)
        y = draw_lines(page, lines, fonts, BODY_SIZE, 79.5, y, BODY_LEADING) + 24.3
    if y > 600:
        raise SystemExit(f"p13 note overflows its panel (last baseline {y - 24.3:.0f})")


# ---- p25: the three perspectives, as a list ------------------------------------

def p25_perspectives(page: fitz.Page, fonts: Fonts) -> None:
    remove_text(page, fitz.Rect(40, 45, 400, 122))
    x, w, lead = 47.2, 362.0, 12.1
    y = draw_lines(page, wrap([Run("This book will cover each of these patterns in turn:")],
                              fonts, BODY_SIZE, w), fonts, BODY_SIZE, x, 57.5, lead)
    items = [
        [Run("from a "), Run("mycelial mindset", "medium"),
         Run(" to understand how mushrooms demonstrate them")],
        [Run("looking at a few "), Run("myco-mimetic examples", "medium"),
         Run(" of that pattern at work in the Web3 space")],
        [Run("ending with some "), Run("imaginative provocations", "medium"),
         Run(" of what a more fungal future could look like in Web3 and beyond.")],
    ]
    hang = 13.0
    for n, runs in enumerate(items, 1):
        y += lead
        text(page, fonts, (x, y), f"{n}.", font="medium")
        y = draw_lines(page, wrap(runs, fonts, BODY_SIZE, w - hang), fonts, BODY_SIZE,
                       x + hang, y, lead)
    if y > 121:
        raise SystemExit(f"p25 list runs into the Moloch panel (baseline {y:.0f})")


# ---- p46: quadratic funding paragraph re-wrapped -------------------------------

QF = ("The Gitcoin Grants" + sup(13) + " platform leverages edge-based intelligence to "
      "distribute a large pool of matching funds via Quadratic Funding." + sup(14) + " The "
      "Grants protocol elicits the “wisdom of the crowd” via individual donations to donor’s "
      "favorite projects, donations which are then quadratically matched from a central donor "
      "pool. With hundreds of thousands of “sensors” (donors), the Grants protocol not only "
      "takes in signals from the edges of the network to assess worthy projects, but it also "
      "quadratically amplifies that signal with matching funds from sponsor organizations – "
      "the broader the support, the bigger the match.")


def p46_quadratic_funding(page: fitz.Page, fonts: Fonts) -> None:
    remove_text(page, fitz.Rect(50, 250, 395, 392))
    narrow, wide, around_logo = 230.0, 325.0, 9    # lines beside the Gitcoin logo
    lines = wrap([Run(QF)], fonts, BODY_SIZE, narrow)
    head = lines[:around_logo]
    rest_text = " ".join("".join(t for t, *_ in ln.runs).strip() for ln in lines[around_logo:])
    rest = wrap([Run(rest_text)], fonts, BODY_SIZE, wide) if rest_text else []
    y = draw_lines(page, head, fonts, BODY_SIZE, 56.0, 260.5, BODY_LEADING)
    if rest:
        y = draw_lines(page, rest, fonts, BODY_SIZE, 56.0, y + BODY_LEADING, BODY_LEADING)
    if y > 392:
        raise SystemExit(f"p46 paragraph overruns the next one (baseline {y:.0f})")


# ---- p77: a parting thought, centred ----------------------------------------------

PARTING = ("Root into your body, and feel the coherence of the billions of microscopic "
           "organisms that comprise you. Root into your community, and dream of new ways we "
           "can merge our voices in collective wisdom. Root into the land, and tread lightly on "
           "this precious planet, for she is our great mother and our only home.")


def _heal_strip(page: fitz.Page, r: fitz.Rect, dpi: int = 300) -> None:
    """Paint over ``r`` with a vertical blend of the rows just above and below it.

    The designer's export flattened the last line of p77 into an image tile; the
    background behind it is a soft gradient, so interpolating across is invisible.
    """
    import numpy as np

    pad = fitz.Rect(r.x0, r.y0 - 1.5, r.x1, r.y1 + 1.5)
    pm = page.get_pixmap(dpi=dpi, clip=pad)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., :3]
    a = a.astype(float)
    top, bot = a[:3].mean(0), a[-3:].mean(0)
    t = np.linspace(0, 1, a.shape[0])[:, None, None]
    out = (top[None] * (1 - t) + bot[None] * t).clip(0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, "PNG")
    page.insert_image(pad, stream=buf.getvalue())


def p77_parting(page: fitz.Page, fonts: Fonts) -> None:
    remove_text(page, fitz.Rect(30, 140, 420, 270))
    _heal_strip(page, fitz.Rect(46, 243, 377, 256.5))
    _heal_strip(page, fitz.Rect(9, 230.0, 412, 235.0))     # tile seam, now in open sky
    area = fitz.Rect(9, 39, 411, 627)               # inner art panel, trim to frame; recto
    size, lead = HEAD_SIZE, 23.35
    lines = wrap([Run(PARTING, "italic")], fonts, size, 318.0)
    title = "A parting thought from the mushrooms:"
    title_size = 17.0
    gap = 30.0
    block_h = title_size + gap + (len(lines) - 1) * lead
    y = area.y0 + (area.height - block_h) / 2 + title_size * 0.75
    text(page, fonts, (area.x0 + area.width / 2, y), title, font="display", size=title_size,
         align="center", word_space=2.5)
    draw_lines(page, lines, fonts, size, area.x0, y + gap + 4, lead, width=area.width,
               align="center")


# ---- p78: bigger QR inside the call-to-action box; FUNG what matters ---------------

def _fung_sticker(page: fitz.Page) -> None:
    """Swap the vector "D" in the FUND WHAT MATTERS sticker for a "G"."""
    d_box = fitz.Rect(229.5, 280.5, 264.5, 320.5)
    fill_rect(page, d_box, TEAL)
    from .fonts import DISPLAY
    g = fitz.Font(fontfile=str(DISPLAY))
    size = 57.0
    gw = g.text_length("G", size)
    # Condense the wide Seriously Nostalgic G to the sticker's narrow letterforms.
    sx = (d_box.width - 1.5) / gw
    origin = fitz.Point(d_box.x0 + 0.5, d_box.y1 - 0.4)
    tw = fitz.TextWriter(page.rect)
    tw.append(origin, "G", font=g, fontsize=size)
    tw.write_text(page, color=(1, 1, 1), morph=(origin, fitz.Matrix(sx, 0, 0, 0.98, 0, 0)))


def p78_rooted(doc: fitz.Document, orig_index: int, fonts: Fonts) -> None:
    src = fitz.open()
    src.insert_pdf(doc, from_page=orig_index, to_page=orig_index)
    _fung_sticker(src[0])
    sticker_src = fitz.Rect(60, 209, 275, 395)
    cat_src = fitz.Rect(297, 270, 416, 380)

    page = doc[orig_index]
    # Clear everything under the intro paragraph back to the white panel.
    remove_text(page, fitz.Rect(50, 165, 420, 260))
    fill_rect(page, fitz.Rect(40, 155, 440, 626), (1, 1, 1))

    # Call to action + QR in one yellow box.
    box = fitz.Rect(56, 160, 394, 262)
    rounded_rect(page, box, 14, fill=SPORE_YELLOW)
    qr_side = 86.0
    qr = fitz.Rect(box.x1 - 8 - qr_side, box.y0 + 8, box.x1 - 8, box.y0 + 8 + qr_side)
    page.insert_image(qr, filename=str(LINKS / "MycoFi Linktree QR.png"))
    cta = wrap([Run("Join the community and contribute your two spores:", "medium")],
               fonts, 12.0, qr.x0 - box.x0 - 30)
    y = draw_lines(page, cta, fonts, 12.0, box.x0 + 16, box.y0 + 36, 16.0)
    text(page, fonts, (box.x0 + 16, y + 22), "linktr.ee/MycoFi", font="medium", size=9.5,
         color=LINK_GREEN)
    text(page, fonts, (box.x0 + 16, y + 34), "scan to find us →", size=7.81)

    # Sticker and the mushroom friend, side by side, tighter.
    s_w = 176.0
    s_h = s_w * sticker_src.height / sticker_src.width
    sticker_dst = fitz.Rect(64, 274, 64 + s_w, 274 + s_h)
    page.show_pdf_page(sticker_dst, src, 0, clip=sticker_src)
    c_w = 104.0
    c_h = c_w * cat_src.height / cat_src.width
    cat_dst = fitz.Rect(268, 274 + (s_h - c_h) / 2, 268 + c_w, 274 + (s_h - c_h) / 2 + c_h)
    page.show_pdf_page(cat_dst, src, 0, clip=cat_src)

    # Meme, from the high-res original, resampled to 400 ppi at its placed size.
    meme = Image.open(LINKS / "always has been - high res.png").convert("RGB")
    top = sticker_dst.y1 + 14
    h = 602 - top
    w = min(338.0, h * meme.width / meme.height)
    h = w * meme.height / meme.width
    x0 = 56 + (338 - w) / 2
    px = round(w / 72 * 400)
    meme = meme.resize((px, round(px * meme.height / meme.width)), Image.LANCZOS)
    buf = io.BytesIO()
    meme.save(buf, "JPEG", quality=92)
    page.insert_image(fitz.Rect(x0, top, x0 + w, top + h), stream=buf.getvalue())


# ---- p82-83: appendix -------------------------------------------------------------

def extract_references(doc: fitz.Document) -> list[str]:
    refs: list[list] = []
    for pno in (81, 82):
        page = doc[pno]
        spans = []
        raw = page.get_text("rawdict", clip=fitz.Rect(40, 145, 420, 630))
        for b in raw["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    # InDesign kerns some word gaps instead of setting a space:
                    # rebuild the text from glyph positions.
                    t, prev_x1 = "", None
                    for c in s["chars"]:
                        if prev_x1 is not None and c["bbox"][0] - prev_x1 > 0.2 * s["size"] \
                                and not t.endswith(" ") and c["c"] != " ":
                            t += " "
                        t += c["c"]
                        prev_x1 = c["bbox"][2]
                    spans.append((round(s["origin"][1], 1), s["bbox"][0], s["bbox"][2], t))
        spans.sort()
        last_y, last_x1 = None, 0.0
        for y, x, x1, t in spans:
            same_line_gap = y == last_y and x - last_x1 > 0.8
            last_y, last_x1 = y, x1
            m = re.fullmatch(r"\s*(\d+)\.\s*", t)
            if m:
                refs.append([int(m.group(1)), ""])
            elif refs:
                cur = refs[-1][1]
                refs[-1][1] = cur + (" " if same_line_gap and not cur.endswith(" ") else "") + t
    if [n for n, _ in refs] != list(range(1, 48)):
        raise SystemExit(f"reference numbering parsed as {[n for n, _ in refs]}")
    out = [clean(re.sub(r"\s+", " ", body)).strip() for _n, body in refs]
    # The text cites spatial memory (p46) before the slime-mould faculty (p47):
    # the designer's list had 11 and 12 the other way round.
    if out[10].startswith("Physarum") and out[11].startswith("Ecological Memory"):
        out[10], out[11] = out[11], out[10]
    elif not out[10].startswith("Ecological Memory"):
        raise SystemExit(f"references 11/12 are not what the swap expects: {out[10][:40]!r}")
    return out


def appendix(p82: fitz.Page, p83: fitz.Page, refs: list[str], fonts: Fonts) -> None:
    for page in (p82, p83):
        remove_text(page, fitz.Rect(20, 30, 440, 630))
    remove_images(p82, fitz.Rect(320, 65, 380, 120))

    x82, x83, width = 56.0, 47.2, 347.0
    text(p82, fonts, (x82, 82.0), "Appendix", font="display", size=TITLE_SIZE)
    intro = [Run("References to sources cited within the text of this book can be found "
                 "below. A digital version of these references can also be found at "),
             Run("bit.ly/mycofi-appendix", color=LINK_GREEN), Run(", or via this QR code.")]
    qr_side = 58.0
    lines = wrap(intro, fonts, BODY_SIZE, width - qr_side - 18)
    y = draw_lines(p82, lines, fonts, BODY_SIZE, x82, 108.0, BODY_LEADING)
    qr = segno.make("https://bit.ly/mycofi-appendix?r=qr", error="m")
    qr_rect = fitz.Rect(x82 + width - qr_side, 96, x82 + width, 96 + qr_side)
    draw_qr(p82, qr, qr_rect)

    tops = {82: max(y, qr_rect.y1 - 6) + 24.0, 83: 62.0}
    bottom = 606.0
    num_w = 16.0

    def layout(size):
        lead = size * 1.32
        gap = size * 0.55
        placed, page, y = [], 82, tops[82]
        for i, r in enumerate(refs, 1):
            lines = wrap([Run(r)], fonts, size, width - num_w)
            h = len(lines) * lead
            if y + h - lead > bottom:
                if page == 83:
                    return None
                page, y = 83, tops[83]
            placed.append((page, y, i, lines))
            y += h + gap
        return placed, lead

    size = BODY_SIZE
    while (res := layout(size)) is None:
        size -= 0.1
        if size < 6.0:
            raise SystemExit("appendix references no longer fit two pages at 6pt")
    placed, lead = res
    for pno, y, i, lines in placed:
        page, x = (p82, x82) if pno == 82 else (p83, x83)
        text(page, fonts, (x + num_w - 4, y), f"{i}.", size=size, align="right")
        draw_lines(page, lines, fonts, size, x + num_w, y, lead)
    print(f"  appendix: 47 references at {size:.2f}pt")
