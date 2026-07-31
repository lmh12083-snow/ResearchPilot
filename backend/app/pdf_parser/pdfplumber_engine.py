"""
pdfplumber parser — slower but better for tables and complex layouts.
Extracts text + tables per page.
"""
from pathlib import Path
from typing import Union

import pdfplumber

from app.pdf_parser.base import ParsedPage, ParseResult, ParseError


def parse_with_pdfplumber(pdf_path: Union[str, Path]) -> ParseResult:
    """Parse a PDF using pdfplumber. Better for table extraction."""
    try:
        doc = pdfplumber.open(pdf_path)
    except Exception as e:
        raise ParseError("Failed to open PDF with pdfplumber", "pdfplumber", cause=e)

    pages: list[ParsedPage] = []
    total_length = 0

    for page_num, page in enumerate(doc.pages, start=1):
        try:
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            pages.append(ParsedPage(
                page_number=page_num,
                text=text,
                tables=tables,
            ))
            total_length += len(text)
        except Exception as e:
            pages.append(ParsedPage(page_number=page_num, text=""))
            raise ParseError(
                f"Failed to extract page {page_num}: {e}", "pdfplumber"
            )

    doc.close()

    return ParseResult(
        pages=pages,
        page_count=len(pages),
        total_text_length=total_length,
        engine_used="pdfplumber",
    )
