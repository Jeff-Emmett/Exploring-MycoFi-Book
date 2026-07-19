"""
Re-export Mycofi Pages_Full_Draft.idml as KDP 6x9" interior with bleed.

KDP 6x9" with bleed:
- Trim: 6 x 9 inches (432 x 648 pt)
- Bleed: 0.125" on top, bottom, outside (gutter side: no bleed)
- MediaBox effectively becomes 6.125 x 9.25" (441 x 666 pt) per page
- Inside (gutter) margin: 0.375" for 24-150 pages
- Outside/top/bottom min margin: 0.25"

Drops first 2 pages (covers) and prepends a blank.
Run with: scribus -g -ns -py scribus_kdp_bleed.py
"""
import scribus
import os
import sys

IDML = "/home/jeffe/Github/Exploring-MycoFi-Book/source/Mycofi Pages_Full_Draft.idml"
SLA  = "/home/jeffe/Github/Exploring-MycoFi-Book/ExploringMycoFiBook_KDP_6x9_bleed.sla"
PDF  = "/home/jeffe/Github/Exploring-MycoFi-Book/ExploringMycoFiBook_KDP_6x9_bleed.pdf"

# NOTE: Scribus PDF bleed values are in the *document's current units*.
# This IDML opens with units = inches (page size reports as 6.0, 9.0).
# So bleed must be expressed in inches: 0.125".
BLEED_IN = 0.125

def log(msg):
    print(f"[kdp] {msg}", file=sys.stderr, flush=True)

# 1. open IDML
log(f"opening: {IDML}")
try:
    scribus.openDoc(IDML)
except Exception as e:
    log(f"openDoc failed: {e}")
    sys.exit(2)

n0 = scribus.pageCount()
log(f"opened, {n0} pages, page size: {scribus.getPageSize()}")

# 2. drop first 2 pages (covers)
for _ in range(2):
    scribus.deletePage(1)
log(f"after removing 2 covers: {scribus.pageCount()} pages")

# 3. prepend a blank page (matches current page size)
try:
    masters = scribus.masterPageNames()
    log(f"master pages: {masters}")
    # use the first available master, or "Normal" fallback
    master = masters[0] if masters else "Normal"
    scribus.newPage(1, master)  # insert before page 1
    log(f"after prepending blank: {scribus.pageCount()} pages")
except Exception as e:
    log(f"newPage failed: {e}")

# 4. save SLA
try:
    scribus.saveDocAs(SLA)
    log(f"saved SLA: {os.path.getsize(SLA)} bytes")
except Exception as e:
    log(f"saveDocAs failed: {e}")

# 5. export PDF with bleed (top, bottom, outside = 9 pt; inside = 0)
# Scribus PDFfile bleed is symmetric (top/left/right/bottom).
# We can't ask Scribus to alternate left/right per page — easiest is uniform 9 pt bleed
# on all 4 sides. KDP accepts this; the gutter side bleed is harmless white.
try:
    pdf = scribus.PDFfile()
    pdf.file = PDF
    pdf.pages = list(range(1, scribus.pageCount() + 1))
    pdf.compress = True
    pdf.quality = 0           # max quality
    pdf.resolution = 300
    pdf.bleedt = BLEED_IN
    pdf.bleedb = BLEED_IN
    pdf.bleedl = BLEED_IN
    pdf.bleedr = BLEED_IN
    pdf.cropMarks = False     # KDP does NOT want crop marks
    pdf.bleedMarks = False
    pdf.registrationMarks = False
    pdf.colorMarks = False
    pdf.docInfoMarks = False
    pdf.useDocBleeds = False
    pdf.version = 14          # PDF 1.4
    pdf.embedPDF = True
    try:
        pdf.fontEmbedding = 0  # 0 = embed all, 1 = outline, 2 = no embed
    except Exception:
        pass
    pdf.save()
    log(f"saved PDF: {os.path.getsize(PDF)} bytes")
except Exception as e:
    log(f"PDF export failed: {e}")
    sys.exit(3)

scribus.closeDoc()
log("done")
sys.exit(0)
