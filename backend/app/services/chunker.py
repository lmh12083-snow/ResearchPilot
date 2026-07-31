"""
Recursive text chunker for academic papers.

Splits text by decreasing granularity:
  1. Paragraph boundaries (\n\n)
  2. Sentence boundaries (. ? ! 。？！)
  3. Word boundaries (space)
  4. Exact character count (last resort)

Each chunk includes estimated page number based on character position.
"""

from typing import Optional

SENTENCE_BOUNDARIES = {".", "?", "!", "。", "？", "！"}


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
            # Overlap: carry over last chunk_overlap chars
            overlap_text = current[-chunk_overlap:] if len(current) > chunk_overlap else current
            current = overlap_text + split

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
