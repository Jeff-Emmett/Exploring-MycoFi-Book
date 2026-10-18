"""Whole-document repairs to the designer's InDesign export.

1. ``normalize_boxes`` — every page gets the same 450x666 MediaBox (0.125" bleed on
   all four sides, Lulu-style) with the 6x9 TrimBox inset by 9pt. The InDesign art
   already runs past the gutter edge, so this only uncovers it. Per-platform
   outputs crop back from here (see ``crop_for``).
2. ``fix_encoding`` — InDesign wrote Windows-1252 byte codes into fonts whose
   encoding is MacRoman, so ’ “ ” rendered as í ì î and every non-ASCII dash as
   ≠ (a box in ABC Connect Mono). The broken codes all carry a zero /Widths entry,
   with the real advance supplied by the following TJ kern; we swap in the
   correct MacRoman code and cancel its width with an inserted kern, so nothing
   else on the line moves.
3. ``swap_trial_font`` — the labels were set in "ABC Connect Mono Unlicensed
   Trial". Its outlines and metrics are identical to the licensed
   ABCConnectMono-Nail, so the embedded program is replaced and renamed.
"""
from __future__ import annotations

import pikepdf
from fontTools.ttLib import TTFont
from pikepdf import Array, Name, Operator, String

from .fonts import LICENSED_MONO
from .geometry import FULL_BLEED_PDF as FULL_BLEED, TRIM_PDF as TRIM, TRIM_W

# MacRoman codes for the characters InDesign meant.
QUOTERIGHT, QUOTELEFT, QUOTEDBLLEFT, QUOTEDBLRIGHT = 0xD5, 0xD4, 0xD2, 0xD3
ENDASH, EMDASH, ELLIPSIS, HYPHEN = 0xD0, 0xD1, 0xC9, 0x2D
# Windows-1252 code -> MacRoman code. 0xAD (soft hyphen / ≠) is context-dependent.
REMAP = {0x92: QUOTERIGHT, 0x91: QUOTELEFT, 0x93: QUOTEDBLLEFT, 0x94: QUOTEDBLRIGHT,
         0x96: ENDASH, 0x97: EMDASH, 0x85: ELLIPSIS}
DASH = 0xAD


def _set_boxes(page, box) -> None:
    page.MediaBox = Array(box)
    page.BleedBox = Array(box)
    page.TrimBox = Array(TRIM)


def normalize_boxes(pdf: pikepdf.Pdf) -> None:
    for i, page in enumerate(pdf.pages):
        trim = [float(v) for v in page.obj.get("/TrimBox", page.MediaBox)]
        if trim != list(TRIM):
            raise SystemExit(f"page {i + 1}: unexpected TrimBox {trim}")
        _set_boxes(page, FULL_BLEED)
        for key in ("/CropBox", "/ArtBox"):
            if key in page.obj:
                del page.obj[key]


def crop_for(pdf: pikepdf.Pdf, platform: str) -> None:
    """Crop the normalized 450x666 pages for a platform.

    lulu: bleed on all sides (6.25x9.25"); kdp: bleed on the outside edge only
    (6.125x9.25"); web: trimmed 6x9.
    """
    x0, y0, x1, y1 = FULL_BLEED
    for i, page in enumerate(pdf.pages):
        recto = i % 2 == 0
        if platform == "lulu":
            box = FULL_BLEED
        elif platform == "kdp":
            box = (0.0, y0, x1, y1) if recto else (x0, y0, TRIM_W, y1)
        elif platform == "web":
            box = TRIM
        else:
            raise ValueError(platform)
        _set_boxes(page, box)


# ---- encoding repair ---------------------------------------------------------

def _simple_font_info(font: pikepdf.Dictionary):
    """(first_char, widths) for a MacRoman-based simple font, else None."""
    if font.get("/Subtype") not in (Name.Type1, Name.TrueType):
        return None
    enc = font.get("/Encoding")
    base = enc.get("/BaseEncoding") if isinstance(enc, pikepdf.Dictionary) else enc
    if base != Name.MacRomanEncoding:
        return None
    return int(font.get("/FirstChar", 0)), [float(w) for w in font.get("/Widths", [])]


def _width(info, code: int) -> float:
    first, widths = info
    i = code - first
    return widths[i] if 0 <= i < len(widths) else 0.0


def _fix_string(raw: bytes, info, prev: int, nxt: int):
    """Return (new TJ elements, changed?) for one shown string."""
    out: list = []
    buf = bytearray()
    changed = False
    for j, c in enumerate(raw):
        new = None
        if _width(info, c) == 0.0:
            if c in REMAP:
                new = REMAP[c]
            elif c == DASH:
                before = raw[j - 1] if j else prev
                after = raw[j + 1] if j + 1 < len(raw) else nxt
                # Spaced dash (" - ") -> en dash; inside a word -> hyphen.
                new = ENDASH if before == 0x20 or after == 0x20 and not j else HYPHEN
        if new is None:
            buf.append(c)
            continue
        buf.append(new)
        out.append(String(bytes(buf)))
        buf = bytearray()
        w = _width(info, new)
        if w:
            out.append(w)
        changed = True
    if buf:
        out.append(String(bytes(buf)))
    return out, changed


def _rewrite(stream_owner, resources, pdf: pikepdf.Pdf, seen: set, info=None) -> int:
    fonts = resources.get("/Font", {}) if resources is not None else {}
    xobjs = resources.get("/XObject", {}) if resources is not None else {}
    ops = pikepdf.parse_content_stream(stream_owner)
    saved = []                       # font state across q/Q
    fixes = 0
    prev = 0x20
    new_ops = []
    for idx, (operands, op) in enumerate(ops):
        if op == Operator("q"):
            saved.append(info)
        elif op == Operator("Q") and saved:
            info = saved.pop()
        elif op == Operator("Tf"):
            f = fonts.get(operands[0])
            info = _simple_font_info(f) if f is not None else None
        elif op == Operator("BT"):
            prev = 0x20
        elif op == Operator("Do"):
            x = xobjs.get(operands[0])
            if x is not None and x.get("/Subtype") == Name.Form and x.objgen not in seen:
                seen.add(x.objgen)
                fixes += _rewrite(x, x.get("/Resources", resources), pdf, seen, info)
        elif op in (Operator("Tj"), Operator("TJ"), Operator("'"), Operator('"')) and info:
            items = list(operands[-1]) if op == Operator("TJ") else [operands[-1]]
            strings = [bytes(s) for s in items if isinstance(s, String)]
            if any(_width(info, c) == 0.0 and (c in REMAP or c == DASH)
                   for s in strings for c in s):
                elems = []
                for k, it in enumerate(items):
                    if not isinstance(it, String):
                        elems.append(it)
                        continue
                    raw = bytes(it)
                    nxt = next((bytes(s)[0] for s in items[k + 1:]
                                if isinstance(s, String) and len(bytes(s))), 0x20)
                    part, ch = _fix_string(raw, info, prev, nxt)
                    fixes += ch
                    elems.extend(part)
                    if raw:
                        prev = raw[-1]
                if op == Operator("TJ"):
                    new_ops.append(([Array(elems)], op))
                else:
                    # ' and " also advance a line (and " sets spacing): keep that
                    # part with an empty show, then show the repaired runs.
                    if op == Operator("'"):
                        new_ops.append(([], Operator("T*")))
                    elif op == Operator('"'):
                        new_ops.append((list(operands[:-1]) + [String(b"")], op))
                    new_ops.append(([Array(elems)], Operator("TJ")))
                continue
            for s in strings:
                if s:
                    prev = s[-1]
        new_ops.append((operands, op))
    if fixes:
        data = pikepdf.unparse_content_stream(new_ops)
        if isinstance(stream_owner, pikepdf.Page):
            stream_owner.obj.Contents = pdf.make_stream(data)
        else:
            stream_owner.write(data)
    return fixes


def fix_encoding(pdf: pikepdf.Pdf) -> int:
    seen: set = set()
    total = 0
    for page in pdf.pages:
        total += _rewrite(page, page.obj.get("/Resources"), pdf, seen)
    return total


# ---- trial font ------------------------------------------------------------

def swap_trial_font(pdf: pikepdf.Pdf) -> int:
    cff = TTFont(LICENSED_MONO).reader["CFF "]
    licensed = None
    swapped = 0
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Type") != Name.Font:
            continue
        base = str(obj.get("/BaseFont", ""))
        if "UnlicensedTrial" not in base:
            continue
        if obj.get("/Subtype") != Name.Type1:
            raise SystemExit(f"trial font {base}: expected a Type1C simple font")
        new_name = Name(base.replace("ABCConnectMonoUnlicensedTrial", "ABCConnectMono"))
        obj.BaseFont = new_name
        desc = obj.get("/FontDescriptor")
        if desc is None:
            continue
        desc.FontName = new_name
        if "/FontFile3" in desc:
            if licensed is None:
                licensed = pdf.make_stream(cff, Subtype=Name.Type1C)
            desc.FontFile3 = licensed
        swapped += 1
    return swapped
