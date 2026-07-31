from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedPage:
    """Result from parsing a single PDF page."""
    page_number: int
    text: str
    tables: list = field(default_factory=list)  # raw table data


@dataclass
class ParseResult:
    """Full result of PDF parsing."""
    pages: list[ParsedPage]
    page_count: int
    total_text_length: int
    engine_used: str  # which parser engine was primary


class ParseError(Exception):
    """Raised when a parser engine fails."""
    def __init__(self, message: str, engine: str, cause: Optional[Exception] = None):
        self.engine = engine
        self.cause = cause
        super().__init__(f"[{engine}] {message}")
