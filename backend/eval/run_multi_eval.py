"""
Multi-paper RAG evaluation — auto-generated test set across a project's papers.

Unlike eval/evaluate.py (single paper, manually curated qa_pairs.json), this
driver builds the test set from the LLM (each sampled chunk of every completed
paper becomes one question, and that chunk is the gold), then evaluates BOTH
retrieval pipelines on every question:

  - pure-vector : dense similarity only (VectorStore.similarity_search)
  - hybrid      : production path — dense + BM25 + RRF + cross-encoder rerank

Gold chunks are matched by FULL chunk id ("{paper_id}_{chunk_index}"), so the
metric is correct even when several papers are in scope (the old suffix-only
match broke across papers).

Generation metrics (LLM-as-judge, reuses app.services.rag_eval judges):
  - answer_accuracy : fraction of answers the judge marks correct
  - faithfulness    : fraction of answers the judge marks grounded in context

Usage (from backend/):
    python -m eval.run_multi_eval [--project 2] [--sample-per-paper 20] [--top-k 5]

Writes report.json in this directory.
"""

import argparse
import json
import time
from pathlib import Path

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.paper import Paper, PaperStatus
from app.models.project import Project
from app.services.embedding import EmbeddingService
from app.services.hybrid_search import hybrid_search
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.services import rag_eval  # reuse _filter_chunks/_sample_chunks/_answer/_judge

REPORT_PATH = Path(__file__).parent / "report.json"

# LLM 自生成测试集存在乐观偏差，写入报告并打印警告。
BIAS_NOTE = (
    "测试集由 LLM 自生成：gold 片段即采样片段本身，问题也由同一 LLM 基于该片段生成，"
    "因此检索与生成指标存在乐观偏差（分数偏高），只能反映不同检索方法/配置间的相对差异，"
    "不代表绝对质量。请与人工评测集 backend/eval/qa_pairs.json 的结果对照解读。"
)


def _build_test_set(project_id: int, sample_per_paper: int):
    """Generate one question per sampled chunk for every completed paper."""
    from app.services.rag_eval import _filter_chunks, _generate_questions_for_paper, _sample_chunks

    db = SessionLocal()
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    items = []
    try:
        papers = (
            db.query(Paper)
            .filter(Paper.project_id == project_id, Paper.status == PaperStatus.COMPLETED)
            .all()
        )
        if not papers:
            raise RuntimeError(f"project {project_id}: no completed papers")

        for paper in papers:
            chunks = vs.get_all_chunks([paper.id])
            chunks = _filter_chunks(chunks)
            if not chunks:
                print(f"  paper {paper.id}: no usable chunks, skipped")
                continue
            sample = _sample_chunks(chunks, sample_per_paper)
            try:
                qas = _generate_questions_for_paper(paper, sample)
            except Exception as e:
                print(f"  paper {paper.id}: question generation failed: {e}")
                continue
            for qa in qas:
                c = qa["chunk"]
                items.append({
                    "paper_id": paper.id,
                    "paper_title": paper.title,
                    "question": qa["question"],
                    "gold_chunk_id": c["id"],
                    "gold_text": (c.get("text") or "")[:4000],
                })
            print(f"  paper {paper.id}: {len(qas)} questions from {len(sample)} sampled chunks")
    finally:
        db.close()
    return items


def _rank_of(ids: list[str], gold: str) -> int | None:
    """1-based rank of the gold chunk id, or None if not in top-k."""
    for i, cid in enumerate(ids, start=1):
        if cid == gold:
            return i
    return None


def _vector_retrieve(question: str, paper_id: int, top_k: int) -> list[dict]:
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    emb = EmbeddingService.embed([question])[0]
    return vs.similarity_search(emb, top_k=top_k, paper_id=paper_id)


def _error_breakdown(rows: list[dict]) -> dict:
    """Deterministic error classes from existing case fields (no extra LLM calls).

    Priority: retrieval_miss > unjudged > answer_incorrect > unfaithful > ok.
    `--no-judge` runs (or judge parse failures) land in `unjudged` so they are
    not miscounted as ok or answer_incorrect.
    """
    counts = {"retrieval_miss": 0, "unjudged": 0, "answer_incorrect": 0, "unfaithful": 0, "ok": 0}
    for r in rows:
        if r["hyb_rank"] is None:
            counts["retrieval_miss"] += 1
        elif r["answer_correct"] is None:
            counts["unjudged"] += 1
        elif r["answer_correct"] is False:
            counts["answer_incorrect"] += 1
        elif r["faithful"] is False:
            counts["unfaithful"] += 1
        else:
            counts["ok"] += 1
    n = len(rows)
    pcts = {k: (round(v / n * 100, 1) if n else 0.0) for k, v in counts.items()}
    return {"counts": counts, "pcts": pcts}


def _metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {}

    def _for(method: str) -> dict:
        ranks = [r[f"{method}_rank"] for r in rows]
        hits = {
            k: sum(1 for rk in ranks if rk is not None and rk <= k) / n
            for k in (1, 3, 5)
        }
        mrr = sum(1.0 / rk for rk in ranks if rk is not None) / n
        return {"hit_at_1": round(hits[1], 4), "hit_at_3": round(hits[3], 4),
                "hit_at_5": round(hits[5], 4), "mrr": round(mrr, 4)}

    judged = [r for r in rows if r["answer_correct"] is not None]
    return {
        "qa_count": n,
        "retrieval": {
            "pure_vector": _for("vec"),
            "hybrid": _for("hyb"),
        },
        "generation": {
            "answer_accuracy": round(sum(1 for r in judged if r["answer_correct"]) / len(judged), 4) if judged else None,
            "faithfulness": round(sum(1 for r in judged if r["faithful"]) / len(judged), 4) if judged else None,
            "judged": len(judged),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-paper RAG evaluation")
    parser.add_argument("--project", type=int, default=2)
    parser.add_argument("--sample-per-paper", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--no-judge", action="store_true", help="skip LLM answer/judge (retrieval only)")
    parser.add_argument("--out", type=Path, default=REPORT_PATH,
                        help="report output path (default: eval/report.json)")
    args = parser.parse_args()

    if not LLMService.available():
        raise SystemExit("LLM API key not configured — cannot generate test set / judge")

    print(f"Project {args.project}: generating test set (sample {args.sample_per_paper}/paper)...")
    t0 = time.time()
    items = _build_test_set(args.project, args.sample_per_paper)
    if not items:
        raise SystemExit("no test questions generated")
    print(f"Test set: {len(items)} questions across {len({i['paper_id'] for i in items})} papers\n")

    rows = []
    for idx, item in enumerate(items, start=1):
        q, pid, gold = item["question"], item["paper_id"], item["gold_chunk_id"]
        try:
            # 1. retrieval comparison
            vec = _vector_retrieve(q, pid, args.top_k)
            hyb = hybrid_search(q, paper_id=pid, top_k=args.top_k, rerank=True)
            vec_rank = _rank_of([r["id"] for r in vec], gold)
            hyb_rank = _rank_of([r["id"] for r in hyb], gold)

            # 2. generation (hybrid top-3) + judge, unless skipped
            answer, correct, faithful, reasoning = None, None, None, None
            if not args.no_judge:
                context = "\n\n".join(f"[{i + 1}] {r['text']}" for i, r in enumerate(hyb[:3]))
                answer = rag_eval._answer(q, context)
                correct, faithful, reasoning = rag_eval._judge(q, item["gold_text"], answer)
        except Exception as e:
            print(f"  Q{idx} failed: {e}")
            vec_rank, hyb_rank, answer = None, None, None
            correct, faithful, reasoning = None, None, None

        rows.append({
            "id": idx,
            "paper_id": pid,
            "paper_title": item["paper_title"],
            "question": q,
            "gold_chunk_id": gold,
            "vec_rank": vec_rank,
            "hyb_rank": hyb_rank,
            "answer_correct": correct,
            "faithful": faithful,
            "judge_reasoning": reasoning,
            "answer": (answer or "")[:300],
        })
        print(f"  Q{idx:>2} p{pid} vec@{vec_rank or '-':>1} hyb@{hyb_rank or '-':>1} "
              f"corr={correct} faith={faithful} | {q[:40]}")

    metrics = _metrics(rows)
    report = {
        "project_id": args.project,
        "top_k": args.top_k,
        "sample_per_paper": args.sample_per_paper,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "bias_note": BIAS_NOTE,
        **metrics,
        "error_breakdown": _error_breakdown(rows),
        "cases": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"QA: {metrics['qa_count']}   top_k={args.top_k}   papers={len({i['paper_id'] for i in items})}   elapsed={round(time.time() - t0, 1)}s")
    for method in ("pure_vector", "hybrid"):
        m = metrics["retrieval"][method]
        print(f"  {method:>11}: hit@1={m['hit_at_1']:.3f} hit@3={m['hit_at_3']:.3f} "
              f"hit@5={m['hit_at_5']:.3f} MRR={m['mrr']:.3f}")
    g = metrics["generation"]
    print(f"  generation: accuracy={g['answer_accuracy']} faithfulness={g['faithfulness']} (judged={g['judged']})")
    eb = report["error_breakdown"]
    print("  错误分类: " + "  ".join(
        f"{k}={eb['counts'][k]} ({eb['pcts'][k]}%)" for k in eb["counts"]
    ))
    print("\n\033[93m[警告] " + BIAS_NOTE + "\033[0m")
    print(f"\nReport written: {args.out}")


if __name__ == "__main__":
    main()
