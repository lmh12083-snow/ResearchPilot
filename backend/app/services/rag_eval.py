"""
RAG evaluation — self-generated test set + retrieval/answer metrics.

Pipeline (all LLM calls tagged feature="eval" for the usage dashboard):

  1. Generate   — sample informative chunks from each completed paper and ask the
                  LLM to produce one question per chunk (answerable from that chunk
                  alone). The chunk becomes the "gold" ground-truth passage.
  2. Retrieve   — run the production hybrid_search for each question; record the
                  gold chunk's rank (hit / MRR contribution).
  3. Answer     — answer the question using only the retrieved top-k context.
  4. Judge      — an LLM judge compares the answer against the gold passage and
                  returns correct / faithful verdicts.

`run_eval_job` runs in a background thread, committing progress after every
question so the frontend can poll live status.
"""

import json
import re
import time

from app.core.config import settings
from app.models.rag_eval import RagEvalRun, RagEvalQuestion
from app.models.project import Project
from app.models.paper import Paper, PaperStatus

# ── Prompts ──────────────────────────────────────────────────────

GEN_PROMPT = """你是 RAG 测试集生成器。给定论文《{title}》的若干段落，为每段生成一个"仅凭该段落即可回答"的具体问题。
问题要聚焦段落中的实质信息（方法、数据、结论、概念、关系等），不要泛泛而问，不要跨段引用。
只输出 JSON 字符串数组，元素与段落一一对应（第 i 个问题对应第 i 段），如 ["问题1","问题2",...]。不要输出其他文字。

段落：
{chunks}"""

ANSWER_PROMPT = """你是问答助手。请根据下面的"检索片段"回答用户问题。
规则：
1. 只能依据检索片段作答，严禁使用片段之外的先验知识；
2. 如果片段不足以回答，明确回答"无法从提供的资料中回答"；
3. 回答简洁准确，使用中文。

检索片段：
{context}

问题：{question}"""

JUDGE_PROMPT = """你是 RAG 评测裁判。判断参考答案是否正确、是否忠实于"标准答案片段"。
- correct：参考答案的主要信息与标准片段一致且能正确回答问题。标准片段必然包含答案，因此若参考答案声称"无法回答"，判 false。
- faithful：参考答案没有编造片段中不存在的信息，也没有与片段矛盾。
只输出 JSON：{{"correct": true/false, "faithful": true/false, "reasoning": "一句话理由"}}

标准答案片段：
{gold}

问题：{question}

参考答案：
{answer}"""


# ── JSON extraction (tolerant of code fences / trailing text) ────

def _find_json_end(text: str, start: int) -> int:
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_json(text: str):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except Exception:
        pass
    for marker in ("[", "{"):
        start = text.find(marker)
        if start == -1:
            continue
        end = _find_json_end(text, start)
        if end != -1:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                continue
    return None


# ── Chunk sampling ──────────────────────────────────────────────

# Citation signatures used to locate the references/bibliography section.
# Reference entries cram several of these together; body prose rarely does.
_CITATION_MARKERS = [
    r"\barXiv\b", r"\bURL\b", r"\bdoi\.org\b", r"\bACL\b", r"\bEMNLP\b", r"\bNeurIPS\b",
    r"\bICLR\b", r"\bNAACL\b", r"\bAAAI\b", r"\bCVPR\b", r"Proceedings of the",
    r"Annual Meeting of the", r"Association for Computational", r"\. In ",
    r"pages \d+", r"\(\d{4}\)", r"pp\.\s?\d+",
]


def _reference_density(text: str) -> int:
    """Count citation markers in a chunk — high in reference lists."""
    return sum(len(re.findall(p, text, re.IGNORECASE)) for p in _CITATION_MARKERS)


def _drop_reference_section(chunks: list[dict]) -> list[dict]:
    """Remove the references/bibliography section from a chunk list.

    A reference list split across chunks only has its first chunk under a
    "References" heading, so a per-chunk heading check misses the rest. Instead
    we find the first chunk with a dense citation signature (sustained by the
    next chunk) and drop everything from there to the end.
    """
    ordered = sorted(chunks, key=lambda c: (c.get("metadata") or {}).get("chunk_index", 0))
    for i, c in enumerate(ordered):
        if _reference_density(c.get("text") or "") < 5:
            continue
        if i + 1 < len(ordered) and _reference_density(ordered[i + 1].get("text") or "") >= 3:
            return ordered[:i]  # references run from chunk i to the end
    return ordered


def _filter_chunks(chunks: list[dict]) -> list[dict]:
    """Drop too-short chunks, boilerplate pages, and the reference section."""
    out = []
    for c in chunks:
        text = (c.get("text") or "").strip()
        if len(text) < 150:
            continue
        head = text[:80].lower()
        if head.startswith(
            ("references", "bibliography", "参考文献", "致谢", "acknowledg", "contents", "目录")
        ):
            continue
        out.append(c)
    return _drop_reference_section(out)


def _sample_chunks(chunks: list[dict], sample_size: int) -> list[dict]:
    """Evenly spread `sample_size` chunks across the paper (keeps order)."""
    if len(chunks) <= sample_size:
        return chunks
    idx = sorted(
        {round(i * (len(chunks) - 1) / (sample_size - 1)) for i in range(sample_size)}
    )
    return [chunks[i] for i in idx]


# ── Stage 1: question generation ────────────────────────────────

VALIDATE_PROMPT = """你是 RAG 测试集质检员。判断下面的问题是否【仅凭】给定的论文段落即可回答。
- 若段落确实包含回答问题所需的关键信息 → 只输出 YES
- 若段落没有足够信息、或问题指向段落之外的内容 → 只输出 NO
只输出 YES 或 NO，不要输出其他文字。

段落：
{chunk}

问题：
{question}"""


def _validate_question(question: str, chunk_text: str) -> bool:
    """Keep only questions answerable from their own source chunk.

    The generator sometimes produces a question that actually refers to a
    different part of the paper; such questions make retrieval scores unfairly
    low, so they are dropped from the test set.
    """
    from app.services.llm import LLMService

    try:
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": VALIDATE_PROMPT.format(
                    chunk=(chunk_text or "")[:1500], question=question,
                )},
            ],
            temperature=0.0,
            max_tokens=10,
            feature="eval",
        )
        return (reply or "").strip().upper().startswith("YES")
    except Exception:
        return True  # fail-open: keep the question on transient errors


def _generate_questions_for_paper(paper, chunks: list[dict]) -> list[dict]:
    """Batch-generate one question per chunk. Returns [{"question", "chunk"}...]."""
    from app.services.llm import LLMService

    numbered = "\n".join(
        f"[{i + 1}] {(c.get('text') or '')[:800]}" for i, c in enumerate(chunks)
    )
    reply = LLMService.chat(
        messages=[{"role": "system", "content": GEN_PROMPT.format(title=paper.title or "", chunks=numbered)}],
        temperature=0.5,
        max_tokens=1024,
        feature="eval",
    )
    data = _extract_json(reply)
    if not isinstance(data, list):
        return []
    questions = []
    for i, q in enumerate(data):
        if i >= len(chunks) or not isinstance(q, str) or not q.strip():
            continue
        if not _validate_question(q.strip(), chunks[i].get("text") or ""):
            continue
        questions.append({"question": q.strip(), "chunk": chunks[i]})
    return questions


# ── Stage 2/3: retrieval + answer ───────────────────────────────

def _retrieve(query: str, paper_id: int, top_k: int = 5) -> list[dict]:
    from app.services.hybrid_search import hybrid_search

    return hybrid_search(query, paper_id=paper_id, top_k=top_k)


def _answer(question: str, context: str) -> str:
    from app.services.llm import LLMService

    return LLMService.chat(
        messages=[
            {"role": "system", "content": ANSWER_PROMPT.format(
                context=context[:6000], question=question,
            )},
        ],
        temperature=0.3,
        max_tokens=512,
        feature="eval",
    ).strip()


# ── Stage 4: LLM judge ──────────────────────────────────────────

def _judge(question: str, gold_text: str, answer: str) -> tuple:
    """Returns (correct, faithful, reasoning); None verdicts on parse failure."""
    from app.services.llm import LLMService

    reply = LLMService.chat(
        messages=[
            {"role": "system", "content": JUDGE_PROMPT.format(
                gold=gold_text[:3000], question=question, answer=answer,
            )},
        ],
        temperature=0.0,
        max_tokens=512,
        feature="eval",
    )
    data = _extract_json(reply)
    if not isinstance(data, dict):
        return None, None, "裁判输出无法解析"
    return (
        bool(data.get("correct")),
        bool(data.get("faithful")),
        str(data.get("reasoning") or "")[:500],
    )


# ── Metrics ─────────────────────────────────────────────────────

def _compute_metrics(questions: list[RagEvalQuestion]) -> dict:
    n = len(questions)
    if n == 0:
        return {}
    hit1 = sum(1 for q in questions if q.retrieved_rank == 1) / n
    hit3 = sum(1 for q in questions if q.retrieved_rank is not None and q.retrieved_rank <= 3) / n
    hit5 = sum(1 for q in questions if q.retrieved_rank is not None and q.retrieved_rank <= 5) / n
    mrr = sum((1.0 / q.retrieved_rank) if q.retrieved_rank else 0.0 for q in questions) / n

    judged = [q for q in questions if q.answer_correct is not None]
    acc = sum(1 for q in judged if q.answer_correct) / len(judged) if judged else 0.0
    faithful = sum(1 for q in judged if q.faithful) / len(judged) if judged else 0.0

    return {
        "hit_at_1": round(hit1, 4),
        "hit_at_3": round(hit3, 4),
        "hit_at_5": round(hit5, 4),
        "mrr": round(mrr, 4),
        "answer_accuracy": round(acc, 4),
        "faithfulness": round(faithful, 4),
    }


# ── Background job ──────────────────────────────────────────────

def run_eval_job(run_id: int):
    """Orchestrate one eval run in a background thread (own DB session)."""
    from app.core.database import SessionLocal
    from app.services.llm import LLMService
    from app.services.vector_store import VectorStore

    db = SessionLocal()
    try:
        run = db.query(RagEvalRun).filter(RagEvalRun.id == run_id).first()
        if not run:
            return

        if not LLMService.available():
            run.status = "failed"
            run.error_message = "LLM 服务未配置"
            db.commit()
            return

        papers = (
            db.query(Paper)
            .filter(Paper.project_id == run.project_id, Paper.status == PaperStatus.COMPLETED)
            .all()
        )
        if not papers:
            run.status = "failed"
            run.error_message = "项目中没有已完成索引的论文"
            db.commit()
            return

        start = time.time()
        vs = VectorStore(settings.CHROMA_PERSIST_DIR)

        # Stage 1 — generate the test set
        test_items = []
        for paper in papers:
            try:
                chunks = vs.get_all_chunks([paper.id])
                chunks = _filter_chunks(chunks)
                if not chunks:
                    continue
                sample = _sample_chunks(chunks, run.sample_size)
                for item in _generate_questions_for_paper(paper, sample):
                    c = item["chunk"]
                    test_items.append({
                        "paper_id": paper.id,
                        "paper_title": paper.title,
                        "question": item["question"],
                        "gold_chunk_id": c["id"],
                        "gold_text": (c.get("text") or "")[:4000],
                    })
            except Exception:
                continue  # skip a bad paper, don't abort the run

        if not test_items:
            run.status = "failed"
            run.error_message = "未能从论文中生成测试问题"
            db.commit()
            return

        run.question_count = len(test_items)
        run.progress = 0
        db.commit()

        # Stages 2-4 — retrieve, answer, judge per question
        for item in test_items:
            row = RagEvalQuestion(run_id=run.id, **item)
            try:
                retrieved = _retrieve(item["question"], item["paper_id"])
                rank = None
                context = ""
                if retrieved:
                    rank = next(
                        (i + 1 for i, r in enumerate(retrieved) if r["id"] == item["gold_chunk_id"]),
                        None,
                    )
                    context = "\n\n".join(f"[{i + 1}] {r['text']}" for i, r in enumerate(retrieved))
                row.retrieved_rank = rank
                row.hit = rank is not None
                if context:
                    row.answer = _answer(item["question"], context)
                    row.answer_correct, row.faithful, row.judge_reasoning = _judge(
                        item["question"], item["gold_text"], row.answer
                    )
            except Exception:
                pass  # keep whatever was set (rank/hit), skip answer/judge
            db.add(row)
            run.progress += 1
            db.commit()  # per-question commit → live progress polling

        metrics = _compute_metrics(
            db.query(RagEvalQuestion).filter(RagEvalQuestion.run_id == run.id).all()
        )
        run.metrics = json.dumps(metrics, ensure_ascii=False) if metrics else None
        run.status = "completed"
        run.duration_seconds = round(time.time() - start, 1)
        db.commit()
    except Exception as e:
        try:
            run = db.query(RagEvalRun).filter(RagEvalRun.id == run_id).first()
            run.status = "failed"
            run.error_message = str(e)[:500]
            db.commit()
        except Exception:
            pass
    finally:
        db.close()
