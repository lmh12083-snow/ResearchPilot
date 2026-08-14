"""
RAG 评测脚本 — 人工评测集（backend/eval/qa_pairs.json）+ 检索指标 + LLM-as-judge 生成质量指标。

支持正负样本：负样本（negative=true）无 ground_truth_chunk，不参与检索命中率，
单独统计"正确拒绝率"（reject_rate）与"幻觉率"（hallucination_rate）。

指标:
  检索指标 (基于人工标注的 ground_truth_chunk，仅正样本):
    - hit_rate@k:     top-k 检索结果中包含答案片段的比例
    - mrr@k:          mean reciprocal rank（答案片段在结果中排名的倒数）
  两种检索方法对比: pure-vector（仅向量检索） vs hybrid（向量 + BM25 + RRF）
  生成质量指标 (LLM-as-judge):
    - faithfulness:   生成答案中的论断是否都被检索片段支持（0..1，仅正样本）
    - answer_correctness: 生成答案与参考答案的一致性打分（1..5，仅正样本）
    - reject_rate:    负样本中模型正确拒绝（不编造）的比例

用法（在 backend 目录下）:
    python -m eval.evaluate [--top-k 5] [--sample N] [--only all|positive|negative]
    python -m eval.evaluate --out report_manual.json
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from app.core.config import settings
from app.services.embedding import EmbeddingService
from app.services.hybrid_search import hybrid_search
from app.services.llm import LLMService
from app.services.vector_store import VectorStore

QA_FILE = Path(__file__).parent / "qa_pairs.json"
REPORT_FILE = Path(__file__).parent / "report.json"


# ── Loading + validation ─────────────────────────────────────────


def _load_qa(path: Path) -> list[dict]:
    """Load qa_pairs.json, normalizing/normalizing the schema and validating it.

    - `negative` defaults to False (backward compatible with v1 entries).
    - positive 必须提供非空 int 的 ground_truth_chunk；negative 必须为 null。
    """
    qa_list = json.loads(path.read_text(encoding="utf-8"))
    for qa in qa_list:
        qa.setdefault("negative", False)
        qid = qa["id"]
        if not (qa.get("question") or "").strip():
            raise ValueError(f"Q{qid}: question 为空")
        if not (qa.get("reference") or "").strip():
            raise ValueError(f"Q{qid}: reference 为空")
        if qa["negative"]:
            if qa.get("ground_truth_chunk") is not None:
                raise ValueError(f"Q{qid}: negative 样本 ground_truth_chunk 必须为 null")
        else:
            if not isinstance(qa.get("ground_truth_chunk"), int):
                raise ValueError(f"Q{qid}: positive 样本 ground_truth_chunk 必须为非空 int")
    return qa_list


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


def _judge_rejection(question: str, answer: str, chunks: list[dict]) -> float:
    """Negative-sample judge: 1 if the model correctly declined, 0 if it fabricated."""
    context = "\n\n".join(c["text"][:1200] for c in chunks[:3])
    system = (
        "你是反幻觉评测员。判断模型是否正确拒绝回答了一个论文中不存在答案的问题。\n"
        "若回答明确表示无法回答、资料中没有相关信息（包括'根据片段无法判断'），输出 1；\n"
        "若回答给出了实质性的答案（即使声称来自片段）或编造了信息，输出 0。\n"
        "只输出一个数字：0 或 1。"
    )
    user = f"问题: {question}\n\n检索片段:\n{context}\n\n模型回答:\n{answer}\n\n输出(0或1):"
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


# ── Error classification ──────────────────────────────────────────


def _classify_pos(row: dict) -> str:
    """Deterministic error class for a positive row (priority order)."""
    if row["hyb_rank"] <= 0:
        return "retrieval_miss"
    if row["faithfulness"] == 0:
        return "unfaithful"
    if row["correctness"] <= 2:
        return "low_correctness"
    return "ok"


def _error_breakdown(pos_rows: list[dict]) -> dict:
    counts = Counter(_classify_pos(r) for r in pos_rows)
    n = len(pos_rows)
    ordered = ["retrieval_miss", "unfaithful", "low_correctness", "ok"]
    counts = {k: counts.get(k, 0) for k in ordered}
    pcts = {k: (round(v / n * 100, 1) if n else 0.0) for k, v in counts.items()}
    return {"counts": counts, "pcts": pcts}


# ── Report ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG evaluation (manual test set)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--sample", type=int, default=0, help="limit to first N questions (0 = all)")
    parser.add_argument("--only", choices=["all", "positive", "negative"], default="all",
                        help="filter by question type")
    parser.add_argument("--out", type=Path, default=REPORT_FILE,
                        help="report output path (default: eval/report.json)")
    args = parser.parse_args()

    qa_list = _load_qa(QA_FILE)
    if args.only != "all":
        qa_list = [q for q in qa_list if (q["negative"] == (args.only == "negative"))]
    qa_list = qa_list[: args.sample or None]

    paper_ids = {q["paper_id"] for q in qa_list}
    print(f"评测集: {len(qa_list)} 条 QA（positive={sum(1 for q in qa_list if not q['negative'])}"
          f", negative={sum(1 for q in qa_list if q['negative'])}）"
          f"，论文: {sorted(paper_ids)}，top_k={args.top_k}\n")

    rows = []
    for qa in qa_list:
        qid, question, gt, ref, neg = (
            qa["id"], qa["question"], qa["ground_truth_chunk"], qa["reference"], qa["negative"]
        )
        pid = qa["paper_id"]

        # 1. Retrieval comparison (positive questions get a gold rank; negatives don't)
        vec = _vector_retrieve(question, pid, args.top_k)
        hyb = hybrid_search(question, paper_id=pid, top_k=args.top_k, rerank=False)
        vec_rank = hyb_rank = None
        if gt is not None:
            vec_rank = _rank_of_ground_truth([r["id"] for r in vec], gt)
            hyb_rank = _rank_of_ground_truth([r["id"] for r in hyb], gt)

        # 2. Generation + judge (positive: faithfulness + correctness; negative: rejection)
        t0 = time.time()
        answer = _answer(question, hyb)
        faithfulness = correctness = rejection = None
        if neg:
            rejection = _judge_rejection(question, answer, hyb)
        else:
            faithfulness = _judge_faithfulness(question, answer, hyb)
            correctness = _judge_correctness(question, answer, ref)
        elapsed = time.time() - t0

        row = {
            "id": qid, "paper_id": pid, "negative": neg, "question": question,
            "gt_chunk": gt, "vec_rank": vec_rank, "hyb_rank": hyb_rank,
            "faithfulness": faithfulness, "correctness": correctness,
            "rejection": rejection, "answer": answer[:200], "elapsed": round(elapsed, 1),
        }
        row["error_class"] = None if neg else _classify_pos(row)
        rows.append(row)
        print(f"  Q{qid:>2} p{pid}{'[neg]' if neg else '':<3} "
              f"vec@{vec_rank or '-':>1} hyb@{hyb_rank or '-':>1} "
              f"faith={faithfulness if faithfulness is not None else '-':>2} "
              f"corr={correctness if correctness is not None else '-':>2} "
              f"reject={rejection if rejection is not None else '-':>1} ({elapsed:.0f}s) "
              f"{question[:34]}")

    # ── Aggregate ──
    pos_rows = [r for r in rows if not r["negative"]]
    neg_rows = [r for r in rows if r["negative"]]
    n_pos, n_neg = len(pos_rows), len(neg_rows)

    def _rate(key):
        return round(sum(r[key] > 0 for r in pos_rows) / n_pos * 100, 1) if n_pos else None

    def _mrr(key):
        return round(sum(1.0 / r[key] for r in pos_rows if r[key] > 0) / n_pos, 4) if n_pos else None

    report = {
        "schema_version": 2,
        "qa_count": len(rows),
        "positive_count": n_pos,
        "negative_count": n_neg,
        "top_k": args.top_k,
        "retrieval": {  # 仅正样本（负样本无 gold）
            "pure_vector": {"hit_rate": _rate("vec_rank"), "mrr": _mrr("vec_rank")},
            "hybrid": {"hit_rate": _rate("hyb_rank"), "mrr": _mrr("hyb_rank")},
        },
        "generation": {
            "positive": ({
                "count": n_pos,
                "faithfulness": round(sum(r["faithfulness"] for r in pos_rows) / n_pos, 4),
                "answer_correctness": round(sum(r["correctness"] for r in pos_rows) / n_pos, 2),
            } if n_pos else None),
            "negative": ({
                "count": n_neg,
                "reject_rate": round(sum(r["rejection"] for r in neg_rows) / n_neg, 4),
                "hallucination_rate": round(1 - sum(r["rejection"] for r in neg_rows) / n_neg, 4),
            } if n_neg else None),
        },
        "error_breakdown": _error_breakdown(pos_rows),
        "cases": rows,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"总条目: {len(rows)}  positive: {n_pos}  negative: {n_neg}   top_k={args.top_k}")
    print(f"检索 hit_rate@k（仅 positive） pure-vector: {report['retrieval']['pure_vector']['hit_rate']}%   "
          f"hybrid: {report['retrieval']['hybrid']['hit_rate']}%")
    print(f"检索 MRR@k（仅 positive）      pure-vector: {report['retrieval']['pure_vector']['mrr']}   "
          f"hybrid: {report['retrieval']['hybrid']['mrr']}")
    gp = report["generation"]["positive"]
    gn = report["generation"]["negative"]
    if gp:
        print(f"生成 positive  faithfulness: {gp['faithfulness']}   answer_correctness: {gp['answer_correctness']} / 5.0")
    if gn:
        print(f"生成 negative  reject_rate: {gn['reject_rate']}   hallucination_rate: {gn['hallucination_rate']}")
    eb = report["error_breakdown"]
    print("错误分类（仅 positive）: " + "  ".join(
        f"{k}={eb['counts'][k]} ({eb['pcts'][k]}%)" for k in eb["counts"]
    ))
    print(f"\n报告已写入: {args.out}")


if __name__ == "__main__":
    main()
