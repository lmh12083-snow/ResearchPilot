"""
Hybrid search — combines dense vector retrieval with sparse BM25 keywords,
fuses rankings via Reciprocal Rank Fusion (RRF), then optionally re-ranks the
top candidates with a cross-encoder for higher precision.

Each returned item carries:
  - text / metadata (same shape as VectorStore.similarity_search)
  - vector_score: cosine similarity of the vector match (0..1)
  - rerank_score: cross-encoder score (0..1), None if reranker unavailable

The vector_score gate can be reused by callers for the "has_answer" decision.
"""

import re
from typing import Optional

from app.core.config import settings


def _tokenize(text: str) -> list[str]:
    """Tokenize for BM25: lowercase latin words + digits, plus each CJK char.

    CJK handled char-wise (no jieba dependency) so Chinese queries still give
    exact-match signal against Chinese text.
    """
    text = text.lower()
    latin = re.findall(r"[a-z0-9]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    return latin + cjk


class Reranker:
    """Lazy-loaded cross-encoder. Falls back to RRF order on any failure."""

    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            from sentence_transformers import CrossEncoder
            cls._model = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
        return cls._model

    @classmethod
    def rerank(cls, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """Score candidate (query, text) pairs with the cross-encoder."""
        try:
            model = cls._get_model()
        except Exception:
            # Reranker unavailable (no model / no network) — keep RRF order
            for c in candidates:
                c["rerank_score"] = None
            return candidates[:top_k]

        pairs = [(query, c["text"]) for c in candidates]
        try:
            scores = model.predict(pairs)
        except Exception:
            for c in candidates:
                c["rerank_score"] = None
            return candidates[:top_k]

        # Cross-encoder outputs raw logits; sigmoid-normalize to 0..1.
        # Ordering is preserved (sigmoid is monotonic) but the score is now
        # interpretable as a relevance probability for display/gating.
        import math
        for c, s in zip(candidates, scores):
            c["rerank_score"] = 1.0 / (1.0 + math.exp(-float(s)))
        ordered = sorted(candidates, key=lambda c: -c["rerank_score"])
        return ordered[:top_k]


# Reference-list signatures. A chunk dense in these is a bibliography entry,
# not body prose — pure noise for RAG retrieval (chat / agent / search / eval).
# Mirrors the marker set used by rag_eval's reference-section filter.
_REFERENCE_MARKERS = [
    r"\barXiv\b", r"\bURL\b", r"\bdoi\.org\b", r"\bACL\b", r"\bEMNLP\b", r"\bNeurIPS\b",
    r"\bICLR\b", r"\bNAACL\b", r"\bAAAI\b", r"\bCVPR\b", r"Proceedings of the",
    r"Annual Meeting of the", r"Association for Computational", r"\. In ",
    r"pages \d+", r"\(\d{4}\)", r"pp\.\s?\d+",
]
_REFERENCE_HEADING_PREFIXES = (
    "references", "bibliography", "参考文献", "致谢", "acknowledg", "contents", "目录",
)

# Reference entries that a chunk boundary splits mid-way lose the dense
# citation markers above, but keep their author-list shape: "Xxx Yyy, Zzz Aaa,
# and Bbb Ccc". Body prose almost never lists 3+ named authors like this.
_AUTHOR_LIST_RE = re.compile(r"[A-Z][a-z]+ [A-Z][a-z]+(?:, [A-Z][a-z]+ [A-Z][a-z]+){1,}")
# "…editors, Proceedings of the…" / "…editor, Advances in…" — a split reference
# entry that keeps its proceedings line. Note: we deliberately do NOT match a
# bare ", and X" — that fires on body prose like "…generate r…" ("RAG-Token").
_REFERENCE_PUBLISH_RE = re.compile(
    r"(editors|editor),\s+(Advances in|Proceedings of|Journal of)"
)


def _is_reference_chunk(text: str) -> bool:
    """True if a chunk is (likely) bibliography/acknowledgement boilerplate.

    A chunk either starts under a reference heading, is dense in citation
    signatures (year-in-parens, pp. ranges, "Proceedings of", ...), or lists
    several named authors — the shape of a split reference entry. Body prose
    rarely trips any of these, so this is a safe per-chunk filter.
    """
    t = (text or "").strip()
    if not t:
        return True
    if t[:60].lower().startswith(_REFERENCE_HEADING_PREFIXES):
        return True
    if _AUTHOR_LIST_RE.search(t) or _REFERENCE_PUBLISH_RE.search(t):
        return True
    density = sum(len(re.findall(p, t, re.IGNORECASE)) for p in _REFERENCE_MARKERS)
    return density >= 5


def _drop_reference_chunks(items: list[dict]) -> list[dict]:
    """Remove bibliography/acknowledgement chunks from a candidate list."""
    return [c for c in items if not _is_reference_chunk(c.get("text") or "")]


def _rrf_fuse(vec_results: list[dict], bm25_results: list[dict], top_k: int) -> list[dict]:
    """Reciprocal Rank Fusion of two ranked lists of {id, text, metadata}."""
    K = 60
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for rank, item in enumerate(vec_results):
        iid = item["id"]
        items.setdefault(iid, item)
        item.setdefault("vector_score", 1.0 - item.get("distance", 0.0))
        scores[iid] = scores.get(iid, 0.0) + 1.0 / (K + rank + 1)

    for rank, item in enumerate(bm25_results):
        iid = item["id"]
        if iid in items:
            merged = items[iid]
        else:
            merged = dict(item)
            merged.setdefault("vector_score", 0.0)
            items[iid] = merged
        scores[iid] = scores.get(iid, 0.0) + 1.0 / (K + rank + 1)

    ordered = sorted(items.values(), key=lambda c: -scores[c["id"]])
    return ordered[:top_k]


def _bm25_search(
    query: str,
    chunks: list[dict],
    top_k: int,
) -> list[dict]:
    from rank_bm25 import BM25Okapi

    if not chunks:
        return []

    tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))

    ranked_idx = sorted(range(len(scores)), key=lambda i: -scores[i])[:top_k]
    results = []
    for i in ranked_idx:
        if scores[i] <= 0:
            continue
        item = dict(chunks[i])
        item["bm25_score"] = float(scores[i])
        results.append(item)
    return results


def hybrid_search(
    query: str,
    *,
    paper_id: Optional[int] = None,
    project_paper_ids: Optional[list[int]] = None,
    top_k: int = 5,
    rerank: bool = True,
) -> list[dict]:
    """Hybrid retrieval: vector + BM25 + RRF (+ optional cross-encoder rerank).

    Scope is either a single paper (paper_id) or a set of project paper ids.
    """
    from app.services.embedding import EmbeddingService
    from app.services.vector_store import VectorStore

    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    embedding = EmbeddingService.embed([query])[0]

    # 1. Dense retrieval — over-retrieve for recall
    if paper_id is not None:
        vec_results = vs.similarity_search(embedding, top_k=50, paper_id=paper_id)
        scope_ids: Optional[list[int]] = [paper_id]
    else:
        vec_results = vs.similarity_search(embedding, top_k=50)
        ids = set(project_paper_ids or [])
        vec_results = [r for r in vec_results if r["metadata"].get("paper_id") in ids]
        scope_ids = list(ids) or None

    # 2. Sparse retrieval — BM25 over the same scope
    chunks = vs.get_all_chunks(scope_ids)
    bm25_results = _bm25_search(query, chunks, top_k=50)

    # 3. Fuse with RRF
    fused = _rrf_fuse(vec_results, bm25_results, top_k=30)

    # 3b. Drop bibliography/acknowledgement chunks before reranking — they are
    # retrieval noise (a "summarize this paper" query must never return them).
    fused = _drop_reference_chunks(fused)

    # 4. Cross-encoder rerank (optional)
    if rerank:
        return Reranker.rerank(query, fused, top_k)

    for c in fused:
        c["rerank_score"] = None
    return fused[:top_k]
