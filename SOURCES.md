# Source assets — what's in the repo, what isn't

## In the repo

| Path | What it is |
|---|---|
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

`build_kdp_interior.py` and `build_kdp_cover.py` drive Scribus to produce the
KDP-ready 6×9 files. `mycofi_publish.py` wraps the build and runs the
doc-forge `kdp-print-color` finalizer.
