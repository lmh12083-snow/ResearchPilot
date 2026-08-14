"""
只读工具：导出论文"可检索正文块"，用于人工标注评测题（ground_truth_chunk）。

不依赖 chromadb：直接用标准库 sqlite3 读 chroma.sqlite3，重建与
VectorStore.get_all_chunks 相同结构的 dict 列表，再用 rag_eval._filter_chunks
（剔短块 + 截断参考文献段）得到与检索侧一致的"可检索正文块"。

用法（在 backend/ 目录下）:
    python -m eval.dump_chunks --paper-id 2 [--max-chars 240] [--start 0] [--count 999]

只读 Chroma，不写库、不写文件。
"""

import argparse
import sqlite3
from pathlib import Path

from app.core.config import settings
from app.services import rag_eval

CHROMA_DB = Path(settings.CHROMA_PERSIST_DIR) / "chroma.sqlite3"


def _load_chunks(paper_id: int) -> list[dict]:
    """Replicate VectorStore.get_all_chunks([paper_id]) via raw sqlite."""
    con = sqlite3.connect(CHROMA_DB)
    con.row_factory = sqlite3.Row
    try:
        emb_rows = con.execute(
            "SELECT id, embedding_id FROM embeddings WHERE embedding_id LIKE ?",
            (f"{paper_id}_%",),
        ).fetchall()
        text_by_rowid = {
            r["rowid"]: r["string_value"]
            for r in con.execute("SELECT rowid, string_value FROM embedding_fulltext_search")
        }
        meta_rows = con.execute(
            "SELECT id, key, string_value, int_value FROM embedding_metadata"
        ).fetchall()
    finally:
        con.close()

    meta_by_id: dict[int, dict] = {}
    for r in meta_rows:
        key, val = r["key"], None
        if r["string_value"] is not None:
            val = r["string_value"]
        elif r["int_value"] is not None:
            val = r["int_value"]
        meta_by_id.setdefault(r["id"], {})[key] = val

    chunks = []
    for r in emb_rows:
        eid = r["embedding_id"]
        idx = int(eid.split("_")[-1])
        meta = meta_by_id.get(r["id"], {})
        meta.setdefault("chunk_index", idx)
        chunks.append(
            {"id": eid, "text": text_by_rowid.get(r["id"], ""), "metadata": meta}
        )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump retrievable body chunks of a paper")
    parser.add_argument("--paper-id", type=int, required=True)
    parser.add_argument("--max-chars", type=int, default=240, help="text preview length per chunk")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=999)
    args = parser.parse_args()

    chunks = rag_eval._filter_chunks(_load_chunks(args.paper_id))
    ordered = sorted(chunks, key=lambda c: (c["metadata"] or {}).get("chunk_index", 0))
    ordered = ordered[args.start : args.start + args.count]

    print(f"paper {args.paper_id}: 可检索正文块 {len(ordered)} 个")
    for c in ordered:
        m = c["metadata"]
        idx = m.get("chunk_index")
        text = (c.get("text") or "").replace("\n", " ")
        print(f"\n[chunk {idx}] page={m.get('page_number')} len={m.get('char_length')}")
        print(text[: args.max_chars])


if __name__ == "__main__":
    main()
