"""
RAG 评测脚本 — 检索指标 + LLM-as-judge 生成质量指标。

用法（在 backend 目录下）:
    python -m eval.evaluate [--top-k 5] [--sample 16]

指标:
  检索指标 (基于人工标注的 ground_truth_chunk):
    - hit_rate@k:     top-k 检索结果中包含答案片段的比例
    - mrr@k:          mean reciprocal rank（答案片段在结果中排名的倒数）
  两种检索方法对比: pure-vector（仅向量检索） vs hybrid（向量 + BM25 + RRF）
  生成质量指标 (LLM-as-judge):
    - faithfulness:   生成答案中的论断是否都被检索片段支持（0..1）
    - answer_correctness: 生成答案与参考答案的一致性打分（1..5）
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from app.core.config import settings
from app.services.embedding import EmbeddingService
from app.services.hybrid_search import hybrid_search
from app.services.llm import LLMService
from app.services.vector_store import VectorStore

QA_FILE = Path(__file__).parent / "qa_pairs.json"


# ── Retrieval ─────────────────────────────────────────────────────


def _vector_retrieve(query: str, paper_id: int, top_k: int) -> list[dict]:
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    emb = EmbeddingService.embed([query])[0]
    return vs.similarity_search(emb, top_k=top_k, paper_id=paper_id)


def _rank_of_ground_truth(chunk_ids: list[str], gt_chunk: int) -> int:
    """1-based rank of the ground-truth chunk, or 0 if missing."""
    for rank, cid in enumerate(chunk_ids, start=1):
        if cid.split("_")[-1] == str(gt_chunk):
            return rank
    return 0


# ── Generation + judge ─────────────────────────────────────────────


def _answer(question: str, chunks: list[dict]) -> str:
    """Generate a grounded answer using the retrieved chunks (like chat)."""
    context = "\n\n".join(
        f"[{i+1}] ({chunk['metadata'].get('chunk_index')}段)\n{chunk['text'][:1500]}"
        for i, chunk in enumerate(chunks[:3])
    )
    system = (
        "你是论文问答助手。请仅依据提供的论文片段回答问题，不要编造。"
        "如果片段不足以回答，请说明。引用片段用 [n] 标注。"
    )
    user = f"论文片段:\n{context}\n\n问题: {question}"
    return (LLMService.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=512,
        feature="eval",
    ) or "").strip()


def _judge_faithfulness(question: str, answer: str, chunks: list[dict]) -> float:
    context = "\n\n".join(c["text"][:1200] for c in chunks[:3])
    system = (
        "你是事实核验员。判断下面的回答是否完全基于提供的论文片段（无编造）。"
        "只输出一个数字：1 表示完全支持，0 表示有编造或片段无法支撑。"
    )
    user = f"论文片段:\n{context}\n\n问题: {question}\n\n回答: {answer}"
    reply = LLMService.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=10,
        feature="eval",
    ) or ""
    return 1.0 if reply.strip().startswith("1") else 0.0


def _judge_correctness(question: str, answer: str, reference: str) -> float:
    system = (
        "你是评测员。比较模型回答与参考答案，从 1 到 5 打分（整数），"
        "5 表示完全一致且正确，1 表示完全错误。只输出数字。"
    )
    user = (
        f"问题: {question}\n\n参考答案: {reference}\n\n模型回答: {answer}\n\n打分(1-5):"
    )
    reply = LLMService.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
        max_tokens=10,
        feature="eval",
    ) or ""
    try:
        return float(int(reply.strip()[:1]))
    except ValueError:
        return 0.0


# ── Report ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG evaluation")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--sample", type=int, default=0, help="limit to first N questions (0 = all)")
    args = parser.parse_args()

    qa_list = json.loads(QA_FILE.read_text(encoding="utf-8"))[: args.sample or None]
    paper_ids = {q["paper_id"] for q in qa_list}

    print(f"评测集: {len(qa_list)} 条 QA，论文: {paper_ids}，top_k={args.top_k}\n")

    rows = []
    for qa in qa_list:
        qid, question, gt, ref = qa["id"], qa["question"], qa["ground_truth_chunk"], qa["reference"]
        pid = qa["paper_id"]

        # 1. Retrieval comparison
        vec = _vector_retrieve(question, pid, args.top_k)
        hyb = hybrid_search(question, paper_id=pid, top_k=args.top_k, rerank=False)
        vec_rank = _rank_of_ground_truth([r["id"] for r in vec], gt)
        hyb_rank = _rank_of_ground_truth([r["id"] for r in hyb], gt)

        # 2. Generation (hybrid top-3) + LLM judge
        t0 = time.time()
        answer = _answer(question, hyb)
        faithfulness = _judge_faithfulness(question, answer, hyb)
        correctness = _judge_correctness(question, answer, ref)
        elapsed = time.time() - t0

        rows.append({
            "id": qid, "question": question, "gt_chunk": gt,
            "vec_rank": vec_rank, "hyb_rank": hyb_rank,
            "faithfulness": faithfulness, "correctness": correctness,
            "answer": answer[:200], "elapsed": round(elapsed, 1),
        })
        print(f"  Q{qid:>2} [{gt:>3}] vec@{vec_rank or '-':>1} hyb@{hyb_rank or '-':>1} "
              f"faith={faithfulness:.0f} corr={correctness:.0f} ({elapsed:.0f}s) {question[:40]}")

    # ── Aggregate ──
    n = len(rows)
    def _rate(key):
        return round(sum(r[key] > 0 for r in rows) / n * 100, 1)

    def _mrr(key):
        return round(sum(1.0 / r[key] for r in rows if r[key] > 0) / n, 4)

    report = {
        "qa_count": n,
        "top_k": args.top_k,
        "retrieval": {
            "pure_vector": {"hit_rate": _rate("vec_rank"), "mrr": _mrr("vec_rank")},
            "hybrid": {"hit_rate": _rate("hyb_rank"), "mrr": _mrr("hyb_rank")},
        },
        "generation": {
            "faithfulness": round(sum(r["faithfulness"] for r in rows) / n, 4),
            "answer_correctness": round(sum(r["correctness"] for r in rows) / n, 2),
        },
        "cases": rows,
    }

    out_path = Path(__file__).parent / "report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 56)
    print(f"总条目: {n}   top_k={args.top_k}")
    print(f"检索 hit_rate@k   pure-vector: {report['retrieval']['pure_vector']['hit_rate']}%   "
          f"hybrid: {report['retrieval']['hybrid']['hit_rate']}%")
    print(f"检索 MRR@k        pure-vector: {report['retrieval']['pure_vector']['mrr']}   "
          f"hybrid: {report['retrieval']['hybrid']['mrr']}")
    print(f"生成 faithfulness:        {report['generation']['faithfulness']}")
    print(f"生成 answer_correctness:  {report['generation']['answer_correctness']} / 5.0")
    print(f"\n报告已写入: {out_path}")


if __name__ == "__main__":
    main()
