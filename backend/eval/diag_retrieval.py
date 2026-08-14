"""
只读诊断工具：针对 report_manual.json 中的错误用例（retrieval_miss / unfaithful），
打印 gold 片段全文 + 三种检索路径（纯向量 / 混合无重排 / 混合加重排）的 top-5，
用于定位错误根因（检索漏检 vs 片段质量问题 vs 裁判误判）。

用法（在 backend/ 目录下）:
    python -m eval.diag_retrieval [--ids 2,6,11,14,16,17,18,22,24,30] [--top-k 5]

只读 Chroma，不写库、不写文件。
"""

import argparse
import json
from pathlib import Path

from app.core.config import settings
from app.services.embedding import EmbeddingService
from app.services.hybrid_search import hybrid_search
from app.services.vector_store import VectorStore

QA_FILE = Path(__file__).parent / "qa_pairs.json"


def _gold_chunk(paper_id: int, gt_chunk: int) -> dict | None:
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    for c in vs.get_all_chunks([paper_id]):
        if int((c["metadata"] or {}).get("chunk_index", -1)) == gt_chunk:
            return c
    return None


def _rank_of(ids: list[str], gold: int) -> int:
    for i, cid in enumerate(ids, start=1):
        if cid.split("_")[-1] == str(gold):
            return i
    return 0


def _print_retrieval(label: str, results: list[dict], gold: int) -> None:
    print(f"\n  [{label}] (gold@{_rank_of([r['id'] for r in results], gold) or '-'}):")
    for i, r in enumerate(results, start=1):
        idx = (r["metadata"] or {}).get("chunk_index")
        vs = r.get("vector_score")
        rr = r.get("rerank_score")
        bm = r.get("bm25_score")
        line = f"    {i}. chunk {idx}  vec={vs and round(vs, 3)}"
        if bm is not None:
            line += f" bm25={round(bm, 2)}"
        if rr is not None:
            line += f" rerank={round(rr, 3)}"
        if idx == gold:
            line += "  <<< GOLD"
        print(line)
        print(f"       {(r['text'] or '').replace(chr(10), ' ')[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose error cases from report_manual.json")
    parser.add_argument("--ids", type=str, default="2,6,11,14,16,17,18,22,24,30")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    ids = {int(x) for x in args.ids.split(",") if x.strip()}

    qa_list = json.loads(QA_FILE.read_text(encoding="utf-8"))
    cases = {q["id"]: q for q in qa_list if q["id"] in ids}
    print(f"诊断 {len(cases)} 个用例: {sorted(cases)}")

    for qid, qa in sorted(cases.items()):
        pid, gt, q = qa["paper_id"], qa["ground_truth_chunk"], qa["question"]
        print("\n" + "=" * 78)
        print(f"Q{qid} p{pid} gt=chunk {gt} | {q}")
        gold = _gold_chunk(pid, gt)
        if gold is None:
            print("  !! 找不到 gold 片段（可能被 _filter_chunks 剔除或 chunk_index 不匹配）")
        else:
            t = (gold.get("text") or "").replace("\n", " ")
            print(f"  GOLD TEXT ({len(t)} chars): {t[:600]}")

        emb = EmbeddingService.embed([q])[0]
        vec = VectorStore(settings.CHROMA_PERSIST_DIR).similarity_search(
            emb, top_k=args.top_k, paper_id=pid
        )
        hyb_nore = hybrid_search(q, paper_id=pid, top_k=args.top_k, rerank=False)
        hyb_rer = hybrid_search(q, paper_id=pid, top_k=args.top_k, rerank=True)

        _print_retrieval("纯向量", vec, gt)
        _print_retrieval("混合(无重排)", hyb_nore, gt)
        _print_retrieval("混合(加重排)", hyb_rer, gt)


if __name__ == "__main__":
    main()
