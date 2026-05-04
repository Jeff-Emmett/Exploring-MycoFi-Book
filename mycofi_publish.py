#!/usr/bin/env python3
"""End-to-end Mycofi publish: Scribus interior export + KDP color finalize.

Sequence:
  1. ``scribus -g -ns -py scribus_kdp_bleed.py`` — re-exports the IDML to
     ``ExploringMycoFiBook_KDP_6x9_bleed.pdf`` (with bleed, fonts embedded
     by Scribus's own settings).
  2. Pipe that through doc-forge's ``kdp-print-color`` finalizer (sRGB
     colorspace, font embedding belt-and-braces, 300dpi downsample, dates
     stripped) → ``ExploringMycoFiBook_KDP_6x9_bleed_final.pdf``.

The cover is built separately by ``build_kdp_cover.py``; not handled here.

Usage::

    python3 mycofi_publish.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
SCRIBUS_SCRIPT = REPO / "scribus_kdp_bleed.py"
INTERIOR_PDF = REPO / "ExploringMycoFiBook_KDP_6x9_bleed.pdf"
FINAL_PDF = REPO / "ExploringMycoFiBook_KDP_6x9_bleed_final.pdf"

# Reuse the shared doc-forge client. Hard-pin path; if dev-ops moves, fix here.
sys.path.insert(0, str(REPO.parent / "dev-ops" / "scripts"))
import docforge_client as df  # noqa: E402

KDP_TARGET = "kdp-print-color"


def main() -> int:
    print("=== scribus phase ===")
    print(f"  running: scribus -g -ns -py {SCRIBUS_SCRIPT.name}")
    rc = subprocess.run(
        ["scribus", "-g", "-ns", "-py", str(SCRIBUS_SCRIPT)],
        cwd=REPO,
    ).returncode
    if rc != 0:
        print(f"Scribus exited {rc}; aborting", file=sys.stderr)
        return rc
    if not INTERIOR_PDF.exists():
        print(f"Scribus produced no PDF at {INTERIOR_PDF}", file=sys.stderr)
        return 1
    raw_bytes = INTERIOR_PDF.read_bytes()
    print(f"  Scribus output: {INTERIOR_PDF.name} ({len(raw_bytes):,} bytes)")

    print()
    print(f"=== finalize phase: {KDP_TARGET} ===")
    try:
        finalized = df.finalize(raw_bytes, target=KDP_TARGET)
    except df.ConvertError as e:
        print(f"doc-forge finalize failed: {e}", file=sys.stderr)
        return 1
    FINAL_PDF.write_bytes(finalized)
    print(f"  wrote {FINAL_PDF.name} ({len(finalized):,} bytes)")
    print()
    print("DONE — submission-ready interior at", FINAL_PDF)
    return 0


if __name__ == "__main__":
    sys.exit(main())
