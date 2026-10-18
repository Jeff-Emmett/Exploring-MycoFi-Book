# Source assets — what's in the repo, what isn't

## In the repo

| Path | What it is |
|---|---|
| `source/pdf/ExploringMycoFiBook_6x9_base.pdf` | **Build input.** Designer's InDesign export at 6x9 (83 pp, pre-glossary) |
| `print-ready/ExploringMycoFi_interior_{kdp,lulu,web}.pdf` | 2nd-edition interiors built by `build_print.py` |
| `print-ready/ExploringMycoFi_cover_{kdp,lulu}.pdf` | Matching one-piece wrap covers (spine sized per printer) |
| `print-ready/ExploringMycoFiBook_KDP_6x9.pdf` | 6×9 interior exported for KDP upload |
| `ExploringMycoFiBook_KDP_6x9_bleed_final.pdf` | Scribus-built 6×9 interior with bleed |
| `cover_kdp_6x9.pdf` | Scribus-built full wrap cover (front + spine + back) |
| `source/indesign/Mycofi_Pages_Full_Draft.indd` | Master InDesign layout |
| `source/indesign/Mycofi_Pages_Full_Draft.idml` | Version-neutral IDML export of the same |
| `source/covers/mycofi_front_cover.pdf` | Front cover, standalone |
| `source/covers/mycofi_back_cover.pdf` | Back cover, standalone |
| `source/pdf/mycofi_book.pdf` | Full book, spreads |
| `source/pdf/mycofi_single_pages.pdf` | Full book, single pages (spreads split) |
| `source/pdf/ExploringMycoFiBook_ordered.pdf` | Page-order-corrected full book |
| `source/glossary.md` | Glossary copy (76 entries), typeset into pages 84–87 |

All binaries above are stored via Git LFS (see `.gitattributes`). Clone with
`git lfs install` configured or the PDFs arrive as pointer stubs.

## Deliberately NOT in the repo

**`Mycofi Design.zip`** — 1.9 GB, 321 files, at
`/mnt/c/Users/jeffe/Downloads/Mycofi Design.zip`. Contains `Book/`, `Merch/`,
`Images/`, and packaged InDesign sources. Excluded for size, and because it
bundles licensed fonts (ABC Dinamo, Seriously Nostalgic) that `.gitignore`
blocks on purpose.

**InDesign `Links/`** — 591 MB, 93 linked images, at
`/mnt/c/Users/jeffe/Downloads/BOOK_Mycofi Pages_Full_Draft/Links/`. The
committed `.indd` will open with missing links until this folder is relinked.
Excluded for size.

**Licensed fonts** — ABC Dinamo and Seriously Nostalgic are commercial
licenses, not redistributable. Install system-wide at
`~/.local/share/fonts/Mycofi/` so Scribus and InDesign resolve them via
fontconfig. Source copies live in `Document fonts/` inside the design zip.

## Rebuilding

```
python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build_print.py [--isbn-kdp 979-8-…] [--isbn-lulu 978-…] [--paper standard-color]
```

`build_print.py` starts from the designer's PDF, not from the IDML. It repairs the
export (page boxes, InDesign's Windows-1252-in-MacRoman glyph bug that printed
’ “ ” – as í ì î ≠, and the "Unlicensed Trial" ABC Connect Mono, swapped for the
identical licensed font), applies the 2026 edit list (`mycofi_print/edits.py`),
appends the glossary, drops the two blank lead pages and renumbers, then writes
KDP (outside-edge bleed), Lulu (all-sides bleed) and web (trimmed, two-up)
interiors and both covers. New text is set in the book's own faces, rebuilt from
the fonts embedded in the designer PDF into `build/fonts/` (gitignored — licensed).
The cover must be rebuilt whenever the page count changes: spine width follows it.

Not used any more: the Scribus/IDML route (`mycofi_publish.py`,
`scribus_kdp_bleed.py`, `build_kdp_interior.py`, `build_kdp_cover.py`,
`build_glossary.py`). Scribus' IDML import lost every font and image, and the
"final" PDF it was credited with was really the InDesign export re-boxed.
DesignCraft 0.9 (Rust InDesign clone) imports the IDML well but mis-threads text
on several pages and exports 600-800 MB PDFs, so it is not yet a print tool.
