"""
Recursive text chunker for academic papers.

Splits text by decreasing granularity:
  1. Paragraph boundaries (\n\n)
  2. Sentence boundaries (. ? ! 。？！)
  3. Word boundaries (space)
  4. Exact character count (last resort)

Each chunk includes estimated page number based on character position.
"""

import re
from typing import Optional

SENTENCE_BOUNDARIES = {".", "?", "!", "。", "？", "！"}

# ── Layout-noise filtering ─────────────────────────────────────────
#
# PDF text extraction leaks non-body blocks into the text stream: page
# numbers, arXiv preprint footers, table cells, figure-diagram labels,
# fragmented equations and section headings. These are retrieval noise
# (a "what is the result?" query must never match a grid of numbers), so
# the chunker drops them before splitting. Prose is always wrapped wider
# than these fragments — even narrow two-column papers wrap at 40+ chars
# per line while table cells/equation tokens stay under ~30 — so a *run* of
# very short lines is a safe, paper-agnostic discriminator.

_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_ARXIV_FOOTER_RE = re.compile(r"^arXiv:\d{4}\.\d{4,5}")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHORT_LINE_MAX = 30  # table cells / equation tokens / headings stay under this
NOISE_RUN_MIN = 3  # a run of this many short lines is a layout block


def _is_prose_line(line: str) -> bool:
    """True if a line looks like real paragraph text (long + punctuated)."""
    s = line.strip()
    if len(s) < 40:
        return False
    return any(p in s for p in (".", ",", "!", "?"))


def _is_author_line(line: str) -> bool:
    """True if a line belongs to the title/author/affiliation front matter.

    Author lines carry unmistakable signatures — affiliation markers
    (†‡⋆*), emails, or a superscript-annotated name ("Gautier Izacard1,2,3")
    — that body prose never has.
    """
    s = line.strip()
    if not s:
        return True
    if any(ch in s for ch in "†‡⋆*@"):
        return True
    if re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\d[\d,\s]*$", s):
        return True
    # Comma-joined list of 3+ capitalized names ("Patrick Lewis, Ethan Perez, ...")
    if re.search(r"[A-Z][a-z]+ [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z][a-z]+){2,}", s):
        return True
    return False


def _drop_noise_lines(text: str) -> str:
    """Strip PDF layout noise from raw extracted text (before splitting).

    Drops, in order: control characters / nbsp, the front-matter block
    (title/author/affiliation/email lines before the Abstract or first prose
    paragraph), standalone page numbers, arXiv preprint footers, and runs of
    very short lines (tables, figure-diagram labels, equations, headings).
    Figure/table *captions* are real sentences and survive.
    """
    text = _CONTROL_CHARS_RE.sub("", text).replace("\xa0", " ")
    lines = text.split("\n")

    # Front matter: title / authors / affiliations / email before the
    # Abstract heading or the first body-prose paragraph.
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            break
        if s.lower().startswith("abstract"):
            break
        if _is_prose_line(lines[i]) and not _is_author_line(lines[i]):
            break
        i += 1
    lines = lines[i:]

    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        # Standalone page numbers & arXiv preprint footers
        if _PAGE_NUMBER_RE.match(s) or _ARXIV_FOOTER_RE.match(s):
            i += 1
            continue
        # Run of very short lines → layout noise block (table/figure/equation)
        if s and len(s) <= SHORT_LINE_MAX:
            j = i
            while j < n:
                sj = lines[j].strip()
                if sj and len(sj) <= SHORT_LINE_MAX:
                    j += 1
                else:
                    break
            if j - i >= NOISE_RUN_MIN:
                i = j
                continue
        out.append(lines[i])
        i += 1

    # Collapse runs of blank lines left by removed blocks.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def _split_by(text: str, sep: str) -> list[str]:
    """Split text by separator, merge with separator back."""
    parts = text.split(sep)
    result = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i < len(parts) - 1:
            result.append(part + sep)
        else:
            result.append(part)
    return result


def _split_sentences(text: str) -> list[str]:
    """Split text at sentence boundaries while keeping the delimiter."""
    chunks = []
    current = []
    for ch in text:
        current.append(ch)
        if ch in SENTENCE_BOUNDARIES:
            chunks.append("".join(current))
            current = []
    if current:
        chunks.append("".join(current))
    return [c.strip() for c in chunks if c.strip()]


def _split_text(text: str, chunk_size: int) -> list[str]:
    """Iteratively split text until all pieces are <= chunk_size.

    Uses a queue-based approach (no recursion) to avoid stack overflow
    on very large or pathological inputs.
    """
    queue = [text]
    result: list[str] = []

    while queue:
        t = queue.pop(0)
        if len(t) <= chunk_size:
            result.append(t)
            continue

        # Try strategies in order, fall through if a strategy doesn't split
        parts: list[str] | None = None

        # 1. Paragraph split
        if "\n\n" in t:
            parts = _split_by(t, "\n\n")

        # 2. Sentence-boundary split
        if parts is None or len(parts) <= 1:
            if any(b in t for b in SENTENCE_BOUNDARIES):
                parts = _split_by(t, ". ")
            if parts is None or len(parts) <= 1:
                parts = _split_by(t, "。")
            if parts is None or len(parts) <= 1:
                parts = _split_sentences(t)

        # 3. Word split
        if parts is None or len(parts) <= 1:
            if " " in t:
                words = t.split(" ")
                parts = [w + " " for w in words[:-1]] + [words[-1]]

        # 4. Last resort: exact character split
        if parts is None or len(parts) <= 1:
            result.extend(t[i : i + chunk_size] for i in range(0, len(t), chunk_size))
            continue

        # Add oversized parts back to the queue
        for p in parts:
            if p:
                queue.append(p)

    return result


def _sentence_aligned_overlap(text: str, chunk_overlap: int) -> str:
    """Tail of text to carry as overlap, aligned to a sentence boundary.

    The naive `text[-chunk_overlap:]` slice starts mid-word/mid-sentence, which
    makes the next chunk begin with a half-sentence fragment — a weak embedding
    anchor that hurt retrieval in eval error-case analysis. Instead, start the
    overlap at the first sentence boundary within the overlap window, so the next
    chunk opens with a complete sentence.
    """
    if len(text) <= chunk_overlap:
        return text
    start = len(text) - chunk_overlap
    for i in range(start, len(text)):
        if text[i] in SENTENCE_BOUNDARIES:
            return text[i + 1 :].lstrip()
    # No boundary in the window — fall back to the raw tail.
    return text[start:].lstrip()


def _merge_chunks(
    splits: list[str], chunk_size: int, chunk_overlap: int
) -> list[dict]:
    """Merge splits into chunks of target size with overlap."""
    if not splits:
        return []

    chunks = []
    current = ""
    for split in splits:
        if not current:
            current = split
        elif len(current) + len(split) <= chunk_size:
            current += split
        else:
            chunks.append({"text": current.strip(), "raw_len": len(current)})
            # Overlap: carry over the tail aligned to a sentence boundary
            current = _sentence_aligned_overlap(current, chunk_overlap) + split

    if current.strip():
        chunks.append({"text": current.strip(), "raw_len": len(current)})

    return chunks


def _estimate_page(char_start: int, total_length: int, page_count: int) -> int:
    """Estimate page number from character position."""
    if total_length <= 0 or page_count <= 0:
        return 1
    chars_per_page = total_length / page_count
    page = int(char_start / chars_per_page) + 1
    return max(1, min(page, page_count))


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 150,
    page_count: Optional[int] = None,
    total_length: Optional[int] = None,
) -> list[dict]:
    """
    Split text into overlapping chunks.

    Args:
        text: Full text to chunk.
        chunk_size: Target characters per chunk.
        chunk_overlap: Overlap characters between consecutive chunks.
        page_count: Total pages (for page estimation).
        total_length: Total text length (for page estimation).

    Returns:
        List of dicts: {text, chunk_index, page_number}.
    """
    if not text or not text.strip():
        return []

    total_length = total_length or len(text)

    # Step 0: Drop PDF layout noise (tables, figure labels, page numbers, ...)
    text = _drop_noise_lines(text)
    if not text.strip():
        return []

    # Step 1: Iteratively split into small pieces
    splits = _split_text(text, chunk_size)

    # Step 2: Merge into chunks with overlap
    merged = _merge_chunks(splits, chunk_size, chunk_overlap)

    # Step 3: Annotate with index and page number
    char_pos = 0
    result = []
    for i, m in enumerate(merged):
        page_num = _estimate_page(char_pos, total_length, page_count or 1)
        result.append({
            "text": m["text"],
            "chunk_index": i,
            "page_number": page_num,
        })
        char_pos += m["raw_len"]

    return result
