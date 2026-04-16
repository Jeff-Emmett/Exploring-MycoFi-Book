#!/usr/bin/env python3
"""
PDF to Fixed-Layout EPUB Converter

Converts visually-rich PDFs (like designed books from InDesign) into
fixed-layout EPUB3 files suitable for Kindle and ebook readers.

Each PDF page becomes a full-page image in the EPUB, preserving the
original design, typography, and layout.

Usage:
    python3 converter/pdf_to_epub.py input.pdf [--output output.epub] [--dpi 200]
    python3 converter/pdf_to_epub.py input.pdf --title "My Book" --author "Author Name"
"""

import argparse
import io
import os
import sys
import uuid
from pathlib import Path

import fitz  # PyMuPDF
from ebooklib import epub


def extract_pages_as_images(pdf_path: str, dpi: int = 200) -> list[tuple[bytes, int, int]]:
    """Extract each PDF page as a JPEG image.

    Returns list of (image_bytes, width_px, height_px) tuples.
    """
    doc = fitz.open(pdf_path)
    pages = []
    zoom = dpi / 72  # PDF is 72 DPI by default
    matrix = fitz.Matrix(zoom, zoom)

    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix)
        img_bytes = pix.tobytes("jpeg", jpg_quality=92)
        pages.append((img_bytes, pix.width, pix.height))
        print(f"  Extracted page {i + 1}/{doc.page_count} ({pix.width}x{pix.height})")

    doc.close()
    return pages


def extract_metadata(pdf_path: str) -> dict:
    """Pull whatever metadata we can from the PDF."""
    doc = fitz.open(pdf_path)
    meta = doc.metadata
    doc.close()
    return {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "subject": meta.get("subject", ""),
    }


def build_fixed_layout_epub(
    pages: list[tuple[bytes, int, int]],
    title: str,
    author: str,
    output_path: str,
    language: str = "en",
    cover_page: int = 0,
    description: str = "",
) -> str:
    """Build a fixed-layout EPUB3 from page images.

    Args:
        pages: List of (jpeg_bytes, width, height) per page
        title: Book title
        author: Book author
        output_path: Where to save the .epub
        language: Language code
        cover_page: Which page index to use as cover (default 0)
        description: Book description for metadata

    Returns:
        Path to the created EPUB file
    """
    book = epub.EpubBook()
    book_id = str(uuid.uuid4())

    # -- Metadata --
    book.set_identifier(book_id)
    book.set_title(title)
    book.set_language(language)
    book.add_author(author)
    if description:
        book.add_metadata("DC", "description", description)

    # Fixed-layout metadata (EPUB3 rendition properties)
    book.add_metadata(
        None,
        "meta",
        "pre-paginated",
        {"property": "rendition:layout"},
    )
    book.add_metadata(
        None,
        "meta",
        "auto",
        {"property": "rendition:orientation"},
    )
    book.add_metadata(
        None,
        "meta",
        "none",
        {"property": "rendition:spread"},
    )

    # Use first page dimensions as viewport default
    _, vp_w, vp_h = pages[0] if pages else (None, 1024, 1366)

    # -- Add cover image (metadata only, actual image added in page loop) --
    cover_bytes, _, _ = pages[cover_page]
    book.set_cover("images/cover.jpg", cover_bytes, create_page=False)

    # -- CSS for fixed-layout pages --
    page_css = epub.EpubItem(
        uid="page_css",
        file_name="style/page.css",
        media_type="text/css",
        content=b"""
body {
    margin: 0;
    padding: 0;
    overflow: hidden;
}
.page-image {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
}
""",
    )
    book.add_item(page_css)

    # -- Build page chapters --
    chapters = []
    for i, (img_bytes, w, h) in enumerate(pages):
        # Add image
        img_item = epub.EpubImage()
        img_item.file_name = f"images/page_{i:04d}.jpg"
        img_item.media_type = "image/jpeg"
        img_item.content = img_bytes
        book.add_item(img_item)

        # Create HTML page with viewport matching image dimensions
        chapter = epub.EpubHtml(
            title=f"Page {i + 1}",
            file_name=f"pages/page_{i:04d}.xhtml",
            lang=language,
        )
        chapter.content = f"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width={w}, height={h}"/>
    <title>Page {i + 1}</title>
    <link rel="stylesheet" type="text/css" href="../style/page.css"/>
</head>
<body>
    <div><img class="page-image" src="../images/page_{i:04d}.jpg" alt="Page {i + 1}"/></div>
</body>
</html>""".encode("utf-8")
        chapter.add_item(page_css)
        book.add_item(chapter)
        chapters.append(chapter)

    # -- Spine & TOC --
    book.spine = chapters
    # Simple TOC — just first, middle, last for now
    # Can be enhanced with actual chapter markers
    book.toc = [chapters[0]]
    if len(chapters) > 2:
        book.toc.append(chapters[len(chapters) // 2])
    if len(chapters) > 1:
        book.toc.append(chapters[-1])

    # Required EPUB3 navigation
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # -- Write --
    epub.write_epub(output_path, book, {})
    return output_path


def convert_pdf_to_epub(
    pdf_path: str,
    output_path: str | None = None,
    title: str | None = None,
    author: str | None = None,
    dpi: int = 200,
    description: str = "",
) -> str:
    """Main conversion function. Takes a PDF, produces a fixed-layout EPUB.

    Args:
        pdf_path: Path to input PDF
        output_path: Path for output EPUB (default: same name as PDF with .epub)
        title: Override title (otherwise extracted from PDF metadata)
        author: Override author
        dpi: Resolution for page rendering (higher = sharper but larger file)
        description: Book description

    Returns:
        Path to created EPUB
    """
    pdf_path = str(Path(pdf_path).resolve())
    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    # Default output path
    if output_path is None:
        output_path = str(Path(pdf_path).with_suffix(".epub"))

    # Extract metadata from PDF as fallback
    meta = extract_metadata(pdf_path)
    title = title or meta["title"] or Path(pdf_path).stem
    author = author or meta["author"] or "Unknown"

    print(f"Converting: {pdf_path}")
    print(f"  Title:  {title}")
    print(f"  Author: {author}")
    print(f"  DPI:    {dpi}")
    print()

    # Extract pages
    print("Extracting pages...")
    pages = extract_pages_as_images(pdf_path, dpi=dpi)
    print(f"\n{len(pages)} pages extracted.")

    # Build EPUB
    print(f"\nBuilding EPUB: {output_path}")
    result = build_fixed_layout_epub(
        pages=pages,
        title=title,
        author=author,
        output_path=output_path,
        description=description,
    )

    file_size = os.path.getsize(result) / (1024 * 1024)
    print(f"\nDone! {result} ({file_size:.1f} MB)")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to fixed-layout EPUB for Kindle/ebook readers"
    )
    parser.add_argument("pdf", help="Path to input PDF file")
    parser.add_argument("--output", "-o", help="Output EPUB path (default: same name as PDF)")
    parser.add_argument("--title", "-t", help="Book title (overrides PDF metadata)")
    parser.add_argument("--author", "-a", help="Book author (overrides PDF metadata)")
    parser.add_argument("--dpi", type=int, default=200, help="Render DPI (default: 200)")
    parser.add_argument("--description", "-d", default="", help="Book description")

    args = parser.parse_args()
    convert_pdf_to_epub(
        pdf_path=args.pdf,
        output_path=args.output,
        title=args.title,
        author=args.author,
        dpi=args.dpi,
        description=args.description,
    )


if __name__ == "__main__":
    main()
