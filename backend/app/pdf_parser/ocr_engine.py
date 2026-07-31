"""
PaddleOCR parser — for scanned/image-only PDFs.

Requires optional dependencies:
  pip install paddlepaddle paddleocr

If not installed, this module degrades gracefully and raises
an ImportError at runtime when actually called.
"""
from pathlib import Path
from typing import Union

from app.pdf_parser.base import ParsedPage, ParseResult, ParseError


def parse_with_ocr(pdf_path: Union[str, Path]) -> ParseResult:
    """
    Parse a PDF using PaddleOCR (OCR for scanned documents).

    Falls back to a descriptive error if PaddleOCR is not installed.
    """
    try:
        from paddleocr import PaddleOCR
        import fitz
    except ImportError:
        raise ParseError(
            "PaddleOCR is not installed. "
            "Install with: pip install paddlepaddle paddleocr",
            "ocr",
        )

    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise ParseError("Failed to initialize OCR engine", "ocr", cause=e)

    pages: list[ParsedPage] = []
    total_length = 0

    for page_num in range(len(doc)):
        try:
            # Render page to image
            pix = doc[page_num].get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")

            # OCR on image
            result = ocr.ocr(img_bytes)
            text_lines = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0] if line and len(line) > 1 else ""
                    text_lines.append(text)

            text = "\n".join(text_lines)
            pages.append(ParsedPage(page_number=page_num + 1, text=text))
            total_length += len(text)
        except Exception as e:
            pages.append(ParsedPage(page_number=page_num + 1, text=""))
            raise ParseError(
                f"OCR failed on page {page_num + 1}: {e}", "ocr"
            )

    doc.close()
    ocr = None  # allow GC

    return ParseResult(
        pages=pages,
        page_count=len(pages),
        total_text_length=total_length,
        engine_used="paddleocr",
    )
