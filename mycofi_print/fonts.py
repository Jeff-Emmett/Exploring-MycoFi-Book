"""Fonts for print edits.

The designer's PDF embeds the *complete* Neue Haas Grotesk Text Pro and Seriously
Nostalgic CFF programs (InDesign wrote full fonts, not subsets). Anything we
typeset onto those pages is set in the same faces, rebuilt from the embedded
programs into OpenType files under ``build/fonts/`` so fitz and PIL can load them.

Those files are licensed fonts: ``build/`` is gitignored and they are only ever
re-embedded into this same book. Never commit them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import fitz
from fontTools.agl import toUnicode
from fontTools.cffLib import CFFFontSet
from fontTools.misc.psCharStrings import T2WidthExtractor
from fontTools.ttLib import TTFont, newTable

REPO = Path(__file__).resolve().parent.parent
BASE_PDF = REPO / "source" / "pdf" / "ExploringMycoFiBook_6x9_base.pdf"
FONT_DIR = REPO / "build" / "fonts"
MYCOFI_FONTS = Path.home() / ".local/share/fonts/Mycofi"

# Embedded PostScript name (subset tag stripped) -> output file stem.
EMBEDDED = {
    "NHaasGroteskTXPro-55Rg": "NHaasGroteskTXPro-55Rg",
    "NHaasGroteskTXPro-56It": "NHaasGroteskTXPro-56It",
    "NHaasGroteskTXPro-65Md": "NHaasGroteskTXPro-65Md",
    "NHaasGroteskTXPro-66MdIt": "NHaasGroteskTXPro-66MdIt",
}

LICENSED_MONO = MYCOFI_FONTS / "ABCConnectMono-Nail.otf"
DISPLAY = MYCOFI_FONTS / "SeriouslyNostalgic-Regular.otf"
DISPLAY_ITALIC = MYCOFI_FONTS / "SeriouslyNostalgicItal-Reg.otf"


# The face ships zero/four..nine superiors under non-AGL names; map them to the
# Unicode superscript digits so footnote markers can be typed as ¹²³⁴.
SUPERIOR_DIGITS = {n: 0x2070 + i for i, n in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"])
    if i not in (1, 2, 3)}


def sup(n: int | str) -> str:
    """Footnote marker in superscript digits (¹ ² ³ are U+00B9/B2/B3)."""
    table = {"1": "\u00b9", "2": "\u00b2", "3": "\u00b3"}
    return "".join(table.get(c, chr(0x2070 + int(c))) for c in str(n))


def cff_to_otf(cff_bytes: bytes, out: Path) -> None:
    """Wrap a bare CFF (Type1C) program in the minimum OpenType tables."""
    import io

    cff = CFFFontSet()
    cff.decompile(io.BytesIO(cff_bytes), None)
    ps_name = cff.fontNames[0]
    top = cff[ps_name]
    priv = top.Private
    glyphs = list(top.charset)

    metrics = {}
    for g in glyphs:
        cs = top.CharStrings[g]
        ex = T2WidthExtractor(cs.private.Subrs if hasattr(cs.private, "Subrs") else [],
                              cs.globalSubrs, priv.nominalWidthX, priv.defaultWidthX)
        ex.execute(cs)
        bounds = cs.calcBounds(top.CharStrings) or (0, 0, 0, 0)
        metrics[g] = (int(round(ex.width)), int(bounds[0]))

    font = TTFont(sfntVersion="OTTO")
    font.setGlyphOrder(glyphs)
    t = newTable("CFF ")
    t.cff = cff
    font["CFF "] = t

    upm = int(round(1 / top.FontMatrix[0]))
    bbox = [int(v) for v in top.FontBBox]
    head = font["head"] = newTable("head")
    head.tableVersion = 1.0
    head.fontRevision = 1.0
    head.checkSumAdjustment = 0
    head.magicNumber = 0x5F0F3CF5
    head.flags = 3
    head.unitsPerEm = upm
    head.created = head.modified = 0
    head.xMin, head.yMin, head.xMax, head.yMax = bbox
    head.macStyle = 0
    head.lowestRecPPEM = 8
    head.fontDirectionHint = 2
    head.indexToLocFormat = 0
    head.glyphDataFormat = 0

    hhea = font["hhea"] = newTable("hhea")
    hhea.tableVersion = 0x00010000
    hhea.ascent, hhea.descent, hhea.lineGap = bbox[3], bbox[1], 0
    hhea.advanceWidthMax = max(w for w, _ in metrics.values())
    hhea.minLeftSideBearing = min(l for _, l in metrics.values())
    hhea.minRightSideBearing = 0
    hhea.xMaxExtent = bbox[2]
    hhea.caretSlopeRise, hhea.caretSlopeRun, hhea.caretOffset = 1, 0, 0
    for k in ("reserved0", "reserved1", "reserved2", "reserved3"):
        setattr(hhea, k, 0)
    hhea.metricDataFormat = 0
    hhea.numberOfHMetrics = len(glyphs)

    font["hmtx"] = newTable("hmtx")
    font["hmtx"].metrics = metrics

    maxp = font["maxp"] = newTable("maxp")
    maxp.tableVersion = 0x00005000
    maxp.numGlyphs = len(glyphs)

    cmap = {}
    for g in glyphs:
        if g.endswith(".superior") and g.split(".")[0] in SUPERIOR_DIGITS:
            cmap[SUPERIOR_DIGITS[g.split(".")[0]]] = g
            continue
        u = toUnicode(g)
        if len(u) == 1 and ord(u) not in cmap:
            cmap[ord(u)] = g
    from fontTools.ttLib.tables._c_m_a_p import cmap_format_4
    sub = cmap_format_4(4)
    sub.platformID, sub.platEncID, sub.language = 3, 1, 0
    sub.cmap = cmap
    font["cmap"] = newTable("cmap")
    font["cmap"].tableVersion = 0
    font["cmap"].tables = [sub]

    os2 = font["OS/2"] = newTable("OS/2")
    os2.version = 4
    os2.xAvgCharWidth = int(sum(w for w, _ in metrics.values()) / len(metrics))
    os2.usWeightClass = 500 if "Md" in ps_name else 400
    os2.usWidthClass = 5
    os2.fsType = 0
    for k in ("ySubscriptXSize", "ySubscriptYSize", "ySubscriptXOffset", "ySubscriptYOffset",
              "ySuperscriptXSize", "ySuperscriptYSize", "ySuperscriptXOffset",
              "ySuperscriptYOffset", "yStrikeoutSize", "yStrikeoutPosition", "sFamilyClass"):
        setattr(os2, k, 0)
    from fontTools.ttLib.tables.O_S_2f_2 import Panose
    os2.panose = Panose()
    os2.ulUnicodeRange1 = os2.ulUnicodeRange2 = os2.ulUnicodeRange3 = os2.ulUnicodeRange4 = 0
    os2.achVendID = "NONE"
    os2.fsSelection = 0x40
    os2.usFirstCharIndex, os2.usLastCharIndex = min(cmap), min(max(cmap), 0xFFFF)
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = bbox[3], bbox[1], 0
    os2.usWinAscent, os2.usWinDescent = bbox[3], -bbox[1]
    os2.ulCodePageRange1, os2.ulCodePageRange2 = 1, 0
    os2.sxHeight = os2.sCapHeight = 0
    os2.usDefaultChar, os2.usBreakChar, os2.usMaxContext = 0, 32, 2

    post = font["post"] = newTable("post")
    post.formatType = 3.0
    post.italicAngle = float(getattr(top, "ItalicAngle", 0))
    post.underlinePosition = int(getattr(top, "UnderlinePosition", -100))
    post.underlineThickness = int(getattr(top, "UnderlineThickness", 50))
    post.isFixedPitch = 0
    post.minMemType42 = post.maxMemType42 = post.minMemType1 = post.maxMemType1 = 0

    name = font["name"] = newTable("name")
    name.names = []
    family, _, style = ps_name.partition("-")
    for nid, val in ((1, family), (2, style or "Regular"), (4, ps_name), (6, ps_name)):
        name.setName(val, nid, 3, 1, 0x409)

    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)


def extract_embedded(pdf_path: Path = BASE_PDF) -> dict[str, Path]:
    """Rebuild every EMBEDDED font from ``pdf_path`` into FONT_DIR (cached)."""
    paths = {k: FONT_DIR / f"{v}.otf" for k, v in EMBEDDED.items()}
    missing = [k for k, p in paths.items() if not p.exists()]
    if missing:
        doc = fitz.open(pdf_path)
        done: set[str] = set()
        for page in doc:
            for xref, *_rest in page.get_fonts(full=True):
                name = page.parent.xref_get_key(xref, "BaseFont")[1].lstrip("/")
                ps = name.split("+")[-1]
                if ps in missing and ps not in done:
                    _n, ext, _t, buf = doc.extract_font(xref)
                    if ext == "cff" and buf:
                        cff_to_otf(buf, paths[ps])
                        done.add(ps)
        doc.close()
        still = [k for k in missing if not paths[k].exists()]
        if still:
            raise SystemExit(f"could not extract embedded fonts: {still}")
    return paths


class Fonts:
    """fitz.Font handles plus file paths for every face the edits use."""

    def __init__(self) -> None:
        emb = extract_embedded()
        self.paths = {
            "body": emb["NHaasGroteskTXPro-55Rg"],
            "italic": emb["NHaasGroteskTXPro-56It"],
            "medium": emb["NHaasGroteskTXPro-65Md"],
            "medium_italic": emb["NHaasGroteskTXPro-66MdIt"],
            "display": DISPLAY,
            "display_italic": DISPLAY_ITALIC,
            "mono": LICENSED_MONO,
        }
        for k, p in self.paths.items():
            if not p.exists():
                raise SystemExit(f"missing font ({k}): {p}")

    @lru_cache(maxsize=None)
    def __getitem__(self, key: str) -> fitz.Font:
        return fitz.Font(fontfile=str(self.paths[key]))
