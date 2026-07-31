"""
Multi-agent paper analysis — planner → specialists → aggregator.

Unlike a single monolithic LLM call, each analysis dimension is handled by a
specialist "agent" with its own role prompt and *targeted* retrieval from the
paper (via hybrid_search), so the reviewer, methodologist, experimenter,
critic and related-work surveyor each focus on the fragments they care about.
A planner agent generates the per-dimension retrieval queries, and an
aggregator agent merges everything into the final structured JSON.

Flow:
  1. Planner    → per-dimension retrieval queries (JSON)
  2. Specialists→ each retrieves top-k chunks + writes one section
  3. Aggregator → combines sections into the 8-field AnalysisResponse JSON

Any step that fails degrades gracefully (default queries / text fallback /
field-level "未生成"), so the pipeline never breaks on a single bad call.
"""

import json
import re
from typing import Optional

from app.services.llm import LLMService

# ── Dimensions ────────────────────────────────────────────────────

SPECIALIST_KEYS = ["innovation", "methods", "experiments", "limitations", "related_work"]

DEFAULT_QUERIES = {
    "innovation": "核心创新点 主要贡献 与现有方法的区别 优点",
    "methods": "研究方法 技术 算法 模型结构 训练方式 优化",
    "experiments": "实验设计 数据集 评估指标 基线方法 结果对比",
    "limitations": "局限性 不足 缺点 失败 未来工作",
    "related_work": "相关工作 与现有研究的联系 对比 背景",
}

SPECIALIST_ROLES = {
    "innovation": "你是论文创新点分析师，擅长提炼论文相对现有工作的核心贡献与改进。",
    "methods": "你是论文方法分析师，擅长梳理论文使用的技术、算法、模型结构与训练流程。",
    "experiments": "你是论文实验分析师，擅长总结实验设计、数据集、评估指标与关键结果。",
    "limitations": "你是论文批判性评审员，擅长客观指出论文的局限、不足与未解决的问题。",
    "related_work": "你是相关工作研究员，擅长梳理论文与已有研究的关系与定位。",
}

# ── Prompts ───────────────────────────────────────────────────────

PLANNER_SYSTEM = """你是论文分析规划员。给定论文标题和摘要，为每个分析维度设计一条中文检索词，
用于从论文全文片段中检索最相关的信息。检索词要具体、贴合论文内容。
只输出 JSON，不要其他文字。JSON 格式：
{"innovation": "检索词", "methods": "检索词", "experiments": "检索词", "limitations": "检索词", "related_work": "检索词"}"""


def _specialist_system(key: str) -> str:
    return (
        f"{SPECIALIST_ROLES[key]}\n"
        f"请基于下方提供的论文原文片段，撰写「{key}」部分的专业分析（中文）。\n"
        f"要求：\n"
        f"1. 只依据提供的片段，不要编造原文没有的内容；片段不足时如实说明；\n"
        f"2. 条理清晰，可使用简短的要点式（每点一句话）；\n"
        f"3. 输出纯文本即可，不要用 Markdown 代码块或 JSON。"
    )


AGGREGATOR_SYSTEM = """你是一个论文分析总编辑。你将收到论文标题、摘要以及多个维度的分析草稿，
请将其整合成一份结构化的中文分析 JSON。只输出 JSON，不要包含其他文字。字段：
- abstract: 论文摘要/简介（中文，200字以内）
- innovation: 主要创新点（中文，列举3-5点，每点一句话）
- methods: 研究方法（中文，说明使用的技术、算法、框架）
- experiments: 实验设计（中文，包括数据集、评估指标、基线方法、主要结果）
- limitations: 局限性（中文，2-3点）
- related_work: 相关工作（中文，简要说明与现有工作的关系）
- one_sentence: 一句话总结（中文，20字以内）
- pros_cons: 优缺点分析（中文，优点和缺点各2-3点）
若某个维度的草稿缺失或不足，请根据其他信息合理推断或标注"未明确说明"。
字段值必须是字符串，不要使用数组。"""


# ── JSON helpers ──────────────────────────────────────────────────


def _extract_json(text: str) -> Optional[dict]:
    """Extract a JSON object from LLM output (handles ```json fences)."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _to_str(v) -> Optional[str]:
    if isinstance(v, list):
        return "\n".join(str(item) for item in v)
    return str(v) if v is not None else None


# ── Retrieval ─────────────────────────────────────────────────────


def _retrieve(paper_id: int, query: str, parsed_text: str, top_k: int = 4) -> str:
    """Targeted retrieval: hybrid chunks first, raw-text window as fallback."""
    try:
        from app.services.hybrid_search import hybrid_search

        results = hybrid_search(query, paper_id=paper_id, top_k=top_k, rerank=False)
        if results:
            parts = []
            for r in results:
                meta = r["metadata"]
                page = f"[第{meta['page_number']}页]" if meta.get("page_number") is not None else ""
                parts.append(f"(第{meta.get('chunk_index')}段{page})\n{r['text']}")
            return "\n\n".join(parts)
    except Exception:
        pass

    # Fallback: leading window of raw text (covers unindexed papers)
    text = parsed_text or ""
    if not text:
        return ""
    return text[:4000]


# ── Orchestration ─────────────────────────────────────────────────


def run_multi_agent_analysis(paper, parsed_text: str = "") -> Optional[dict]:
    """Planner → specialists → aggregator. Returns the 8-field dict or None."""
    if not LLMService.available():
        return None

    title = paper.title or ""
    abstract = (paper.abstract or "")[:1000]
    paper_id = paper.id

    # 1. Planner — per-dimension queries (fall back to defaults)
    queries = dict(DEFAULT_QUERIES)
    try:
        plan_reply = LLMService.chat(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": f"论文标题: {title}\n\n摘要: {abstract or '无'}"},
            ],
            temperature=0.2,
            max_tokens=600,
            feature="analysis",
        )
        plan = _extract_json(plan_reply)
        if plan:
            for k in SPECIALIST_KEYS:
                if isinstance(plan.get(k), str) and plan[k].strip():
                    queries[k] = plan[k].strip()
    except Exception:
        pass

    # 2. Specialists — one LLM call per dimension with targeted context.
    #    Retrieval runs sequentially (ChromaDB isn't thread-safe); the LLM calls
    #    (pure HTTP) run in parallel to cut total latency ~5x.
    contexts = {}
    for key in SPECIALIST_KEYS:
        contexts[key] = _retrieve(paper_id, queries[key], parsed_text)

    def _specialist(key: str) -> tuple[str, str]:
        context = contexts[key]
        if not context:
            return key, "未生成（原文片段不足）"
        try:
            reply = LLMService.chat(
                messages=[
                    {"role": "system", "content": _specialist_system(key)},
                    {"role": "user", "content": f"论文标题: {title}\n\n相关原文片段:\n{context}"},
                ],
                temperature=0.3,
                max_tokens=1200,
                feature="analysis",
            )
            return key, (reply or "").strip() or "未生成"
        except Exception:
            return key, "未生成（生成失败）"

    from concurrent.futures import ThreadPoolExecutor

    sections: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(SPECIALIST_KEYS)) as pool:
        for key, content in pool.map(_specialist, SPECIALIST_KEYS):
            sections[key] = content

    # 3. Aggregator — merge into final JSON
    drafts = "\n\n".join(
        f"## {key}\n{sections[key]}" for key in SPECIALIST_KEYS
    )
    try:
        agg_reply = LLMService.chat(
            messages=[
                {"role": "system", "content": AGGREGATOR_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"论文标题: {title}\n\n摘要: {abstract or '无'}\n\n"
                        f"各维度分析草稿:\n{drafts}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=2048,
            feature="analysis",
        )
        final = _extract_json(agg_reply)
    except Exception:
        final = None

    if not final:
        # Aggregator failed — best-effort: keep abstract + join sections
        final = {"abstract": abstract or None, "one_sentence": None, "pros_cons": None}
        for key in SPECIALIST_KEYS:
            final[key] = sections[key]

    return {
        "abstract": _to_str(final.get("abstract")),
        "innovation": _to_str(final.get("innovation", sections.get("innovation"))),
        "methods": _to_str(final.get("methods", sections.get("methods"))),
        "experiments": _to_str(final.get("experiments", sections.get("experiments"))),
        "limitations": _to_str(final.get("limitations", sections.get("limitations"))),
        "related_work": _to_str(final.get("related_work", sections.get("related_work"))),
        "one_sentence": _to_str(final.get("one_sentence")),
        "pros_cons": _to_str(final.get("pros_cons")),
    }
