import scribus
import sys
import os

IDML = "/home/jeffe/Github/Exploring-MycoFi-Book/source/Mycofi Pages_Full_Draft.idml"
SLA  = "/home/jeffe/Github/Exploring-MycoFi-Book/scribus_test.sla"
PDF  = "/home/jeffe/Github/Exploring-MycoFi-Book/scribus_test.pdf"

print(f"[scribus] opening: {IDML}", file=sys.stderr)
try:
    scribus.openDoc(IDML)
except Exception as e:
    print(f"[scribus] openDoc failed: {e}", file=sys.stderr)
    sys.exit(2)

print(f"[scribus] page count: {scribus.pageCount()}", file=sys.stderr)
print(f"[scribus] page size: {scribus.getPageSize()}", file=sys.stderr)

try:
    scribus.saveDocAs(SLA)
    print(f"[scribus] saved SLA: {os.path.getsize(SLA)} bytes", file=sys.stderr)
except Exception as e:
    print(f"[scribus] saveDocAs failed: {e}", file=sys.stderr)

try:
    pdf = scribus.PDFfile()
    pdf.file = PDF
    pdf.pages = list(range(1, scribus.pageCount() + 1))
    pdf.compress = True
    pdf.quality = 0
    pdf.resolution = 300
    pdf.save()
    print(f"[scribus] saved PDF: {os.path.getsize(PDF)} bytes", file=sys.stderr)
except Exception as e:
    print(f"[scribus] PDF export failed: {e}", file=sys.stderr)

sys.exit(0)
