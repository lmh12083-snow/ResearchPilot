"""
PDF parsing pipeline — orchestrates the three engines.

Auto-detection logic:
  1. Detect PDF type with PyMuPDF (digital vs scanned)
  2. Digital → PyMuPDF for speed
  3. Tables detected → pdfplumber for those pages
  4. Scanned → PaddleOCR (if available, graceful fallback)

Output: concatenated full text + per-page results.
"""
from pathlib import Path
from typing import Union, Optional

from app.pdf_parser.base import ParsedPage, ParseResult, ParseError
from app.pdf_parser.detector import detect_pdf_type, PdfType
from app.pdf_parser.pymupdf_engine import parse_with_pymupdf
from app.pdf_parser.pdfplumber_engine import parse_with_pdfplumber
from app.pdf_parser.ocr_engine import parse_with_ocr

# Minimum average chars per page to consider digital text "good enough"
MIN_DIGITAL_CHARS = 80


def parse_pdf(pdf_path: Union[str, Path], prefer_ocr: bool = False) -> ParseResult:
    """
    Parse a PDF with automatic engine selection.

    Args:
        pdf_path: Path to the PDF file.
        prefer_ocr: Force OCR even for digital PDFs (useful for CJK).

    Returns:
        ParseResult with all pages and full concatenated text.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise ParseError(f"File not found: {pdf_path}", "pipeline")

    # ── Step 1: detect type ──
    pdf_type, page_count, sample_chars = detect_pdf_type(pdf_path)

    # ── Step 2: choose primary engine ──
    if prefer_ocr or pdf_type in (PdfType.SCANNED, PdfType.UNKNOWN):
        # Try OCR, fall back to PyMuPDF
        try:
            result = parse_with_ocr(pdf_path)
            result.engine_used = "paddleocr"
            return _enrich(result)
        except ParseError:
            pass  # fall through

    # ── Step 3: PyMuPDF (fast path) ──
    result = parse_with_pymupdf(pdf_path)

    avg_chars = result.total_text_length / max(page_count, 1)

    # ── Step 4: if text quality is poor, try pdfplumber ──
    if avg_chars < MIN_DIGITAL_CHARS or pdf_type == PdfType.MIXED:
        try:
            plumber_result = parse_with_pdfplumber(pdf_path)
            # If pdfplumber got more text, use it
            if plumber_result.total_text_length > result.total_text_length:
                result = plumber_result
        except ParseError:
            pass  # keep pymupdf result

    # ── Step 5: if still too little text, attempt OCR as fallback ──
    if result.total_text_length < 100 and page_count > 0:
        try:
            ocr_result = parse_with_ocr(pdf_path)
            if ocr_result.total_text_length > result.total_text_length:
                result = ocr_result
                result.engine_used = "paddleocr"
        except ParseError:
            pass

    result.engine_used = result.engine_used or "pymupdf"
    return _enrich(result)


def _enrich(result: ParseResult) -> ParseResult:
    """Post-processing: trim, recalculate total."""
    total = 0
    for page in result.pages:
        page.text = page.text.strip()
        total += len(page.text)
    result.total_text_length = total
    result.page_count = len(result.pages)
    return result


def get_full_text(result: ParseResult) -> str:
    """Concatenate all pages into a single text blob."""
    return "\n\n".join(p.text for p in result.pages if p.text.strip())
