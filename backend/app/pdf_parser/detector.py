"""
PDF type detection using PyMuPDF.

Determines whether a PDF is "digital" (text can be extracted natively)
or "scanned" (image-based, requires OCR).
"""
import enum
from pathlib import Path
from typing import Union

import fitz  # PyMuPDF


class PdfType(enum.Enum):
    DIGITAL = "digital"     # native text, use PyMuPDF
    MIXED = "mixed"          # some pages have text, some don't
    SCANNED = "scanned"     # image-only, needs OCR
    UNKNOWN = "unknown"     # can't determine


TEXT_THRESHOLD_PER_PAGE = 50  # chars — below this → likely scanned
SAMPLE_PAGES = 3              # first N pages to check


def detect_pdf_type(pdf_path: Union[str, Path]) -> tuple[PdfType, int, int]:
    """
    Open a PDF and determine its type.

    Returns:
        (PdfType, page_count, total_chars_in_sample)
    """
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    if page_count == 0:
        doc.close()
        return PdfType.UNKNOWN, 0, 0

    pages_to_check = min(SAMPLE_PAGES, page_count)
    total_chars = 0
    textless_pages = 0

    for i in range(pages_to_check):
        text = doc[i].get_text().strip()
        total_chars += len(text)
        if len(text) < TEXT_THRESHOLD_PER_PAGE:
            textless_pages += 1

    doc.close()

    ratio = textless_pages / pages_to_check if pages_to_check > 0 else 1

    if ratio == 0:
        return PdfType.DIGITAL, page_count, total_chars
    elif ratio < 0.5:
        return PdfType.MIXED, page_count, total_chars
    elif ratio < 1.0:
        return PdfType.SCANNED, page_count, total_chars
    else:
        return PdfType.SCANNED, page_count, total_chars
