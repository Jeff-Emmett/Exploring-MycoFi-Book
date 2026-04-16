#!/usr/bin/env python3
"""
Batch converter — finds all PDFs in a directory and converts them to EPUB.

Usage:
    python3 converter/batch_convert.py /path/to/pdfs/ --output-dir output/
    python3 converter/batch_convert.py . --dpi 150  # lower DPI for smaller files
"""

import argparse
import os
from pathlib import Path

from pdf_to_epub import convert_pdf_to_epub


# Known book metadata — add entries as we convert more flipbooks
BOOK_METADATA = {
    "ExploringMycoFiBook.pdf": {
        "title": "Exploring MycoFi: Mycelial Design Patterns for Web3 and Beyond",
        "author": "Jeff Emmett & Contributors",
        "description": (
            "A Mycopunk publication from the Greenpill Network exploring "
            "how mycelial networks can inform the design of decentralized "
            "economic systems, DAOs, and Web3 infrastructure."
        ),
    },
    "psilocybernetics.pdf": {
        "title": "Psilocybernetics",
        "author": "Jeff Emmett",
        "description": "An exploration of psychedelic-informed cybernetics.",
    },
}


def find_pdfs(directory: str) -> list[Path]:
    """Find all PDF files in a directory (non-recursive)."""
    return sorted(Path(directory).glob("*.pdf"))


def batch_convert(
    input_dir: str,
    output_dir: str = "output",
    dpi: int = 200,
):
    """Convert all PDFs found in input_dir to EPUBs in output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    pdfs = find_pdfs(input_dir)

    if not pdfs:
        print(f"No PDFs found in {input_dir}")
        return

    print(f"Found {len(pdfs)} PDF(s) to convert:\n")
    for pdf in pdfs:
        print(f"  - {pdf.name}")
    print()

    results = []
    for pdf in pdfs:
        meta = BOOK_METADATA.get(pdf.name, {})
        output_path = os.path.join(output_dir, pdf.stem + ".epub")

        print(f"{'=' * 60}")
        print(f"Converting: {pdf.name}")
        print(f"{'=' * 60}\n")

        try:
            result = convert_pdf_to_epub(
                pdf_path=str(pdf),
                output_path=output_path,
                title=meta.get("title"),
                author=meta.get("author"),
                dpi=dpi,
                description=meta.get("description", ""),
            )
            results.append((pdf.name, result, "OK"))
        except Exception as e:
            print(f"ERROR converting {pdf.name}: {e}")
            results.append((pdf.name, None, str(e)))
        print()

    # Summary
    print(f"\n{'=' * 60}")
    print("BATCH CONVERSION SUMMARY")
    print(f"{'=' * 60}")
    for name, path, status in results:
        if status == "OK":
            size = os.path.getsize(path) / (1024 * 1024)
            print(f"  OK  {name} → {path} ({size:.1f} MB)")
        else:
            print(f"  ERR {name}: {status}")


def main():
    parser = argparse.ArgumentParser(description="Batch convert PDFs to fixed-layout EPUB")
    parser.add_argument("input_dir", help="Directory containing PDF files")
    parser.add_argument("--output-dir", "-o", default="output", help="Output directory (default: output/)")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI (default: 200)")

    args = parser.parse_args()
    batch_convert(args.input_dir, args.output_dir, args.dpi)


if __name__ == "__main__":
    main()
