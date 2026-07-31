"""
PyMuPDF (fitz) parser — fastest for digital PDFs.
Extracts text page by page.
"""
from pathlib import Path
from typing import Union

import fitz

from app.pdf_parser.base import ParsedPage, ParseResult, ParseError


def parse_with_pymupdf(pdf_path: Union[str, Path]) -> ParseResult:
    """Parse a PDF using PyMuPDF. Best for digital (text-based) PDFs."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise ParseError("Failed to open PDF", "pymupdf", cause=e)

    pages: list[ParsedPage] = []
    total_length = 0

    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            text = page.get_text()
            if not text.strip():
                text = ""
            pages.append(ParsedPage(
                page_number=page_num + 1,
                text=text,
            ))
            total_length += len(text)
        except Exception as e:
            # Log and continue with empty page
            pages.append(ParsedPage(page_number=page_num + 1, text=""))
            raise ParseError(
                f"Failed to extract text from page {page_num + 1}: {e}",
                "pymupdf",
            )

    doc.close()

    return ParseResult(
        pages=pages,
        page_count=len(pages),
        total_text_length=total_length,
        engine_used="pymupdf",
    )
