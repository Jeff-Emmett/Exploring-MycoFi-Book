#!/usr/bin/env python3
"""
Add or update Table of Contents for an EPUB built by pdf_to_epub.

Since the PDF has no embedded TOC, chapter markers are defined manually
in a JSON config file. This script patches an existing EPUB's navigation.

Usage:
    python3 converter/add_toc.py output/ExploringMycoFiBook.epub --toc toc_mycofi.json

TOC JSON format:
[
    {"title": "Cover", "page": 1},
    {"title": "Introduction", "page": 5},
    {"title": "Chapter 1: Mycelial Networks", "page": 12},
    ...
]
"""

import argparse
import json
import os
import sys
import zipfile
import tempfile
import shutil
from pathlib import Path

from ebooklib import epub


def patch_toc(epub_path: str, toc_entries: list[dict]) -> str:
    """Patch the TOC of an existing EPUB with manual chapter markers.

    Args:
        epub_path: Path to the EPUB file
        toc_entries: List of {"title": str, "page": int} dicts (1-indexed pages)

    Returns:
        Path to the patched EPUB
    """
    book = epub.read_epub(epub_path)

    # Find all page items sorted by filename
    pages = sorted(
        [item for item in book.get_items() if item.file_name.startswith("pages/")],
        key=lambda x: x.file_name,
    )

    if not pages:
        print("Error: No page items found in EPUB")
        sys.exit(1)

    # Build new TOC from entries
    new_toc = []
    for entry in toc_entries:
        page_idx = entry["page"] - 1  # Convert 1-indexed to 0-indexed
        if 0 <= page_idx < len(pages):
            page_item = pages[page_idx]
            # Create a link using the page's file_name
            new_toc.append(epub.Link(page_item.file_name, entry["title"], f"toc_{page_idx}"))
        else:
            print(f"Warning: Page {entry['page']} out of range (1-{len(pages)}), skipping: {entry['title']}")

    book.toc = new_toc

    # Re-add navigation items
    for item in list(book.get_items()):
        if isinstance(item, (epub.EpubNcx, epub.EpubNav)):
            book.items.remove(item)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write back
    epub.write_epub(epub_path, book, {})
    print(f"Updated TOC with {len(new_toc)} entries in {epub_path}")
    return epub_path


def main():
    parser = argparse.ArgumentParser(description="Add/update EPUB table of contents")
    parser.add_argument("epub", help="Path to EPUB file")
    parser.add_argument("--toc", required=True, help="Path to TOC JSON file")

    args = parser.parse_args()

    with open(args.toc) as f:
        toc_entries = json.load(f)

    patch_toc(args.epub, toc_entries)


if __name__ == "__main__":
    main()
