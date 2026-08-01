"""
Paper comparison service — structured comparison of 2..N papers.

Reuses the cached structured analysis of each paper (8 dimensions) when
available, so the comparator reasons over aligned facets (methods, experiments,
limitations, …) instead of raw text. Falls back to metadata + abstract for
papers that haven't been analyzed yet. A single LLM call handles the whole set.
"""

import json
import re
from typing import Optional

from app.services.llm import LLMService

COMPARE_SYSTEM = """你是一个论文对比专家。给定多篇论文的结构化信息，从以下维度进行客观、具体的对比。
只输出 JSON，不要包含其他文字。字段：
- papers: 数组，每项 {"paper_id": 数字, "one_sentence": "一句话概述"} —— 每篇论文研究什么问题、提出什么
- similarities: 所有论文的共同点（3-5 点）
- method_differences: 方法/技术路线的主要差异（按论文名或编号归属）
- experiment_differences: 实验设计、数据集与结果的主要差异
- conclusion_differences: 主要结论与贡献取向的差异
- strengths_weaknesses: 各自的优势与不足（按论文分组，每篇单独一段）
- final_verdict: 综合对比结论（每篇论文分别适合什么场景，谁更胜一筹）
要求：基于给出的信息对比，不要编造不存在的内容；信息不足时如实标注。指代论文时必须使用其编号，如"论文1"。"""


def _paper_summary(paper, analysis) -> str:
    if analysis is not None:
        return "\n".join([
            f"标题: {paper.title or ''}",
            f"作者: {paper.authors or '未收录'}",
            f"年份: {paper.year or '未知'}",
            f"一句话总结: {analysis.one_sentence or '无'}",
            f"创新点: {analysis.innovation or '无'}",
            f"方法: {analysis.methods or '无'}",
            f"实验: {analysis.experiments or '无'}",
            f"局限: {analysis.limitations or '无'}",
        ])
    return "\n".join([
        f"标题: {paper.title or ''}",
        f"作者: {paper.authors or '未收录'}",
        f"年份: {paper.year or '未知'}",
        f"摘要: {paper.abstract or '无'}",
    ])


def _extract_json(text: str) -> Optional[dict]:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _to_str(v) -> str:
    """Normalize a parsed JSON value into display text.

    LLMs often return per-paper differences as a dict keyed by paper name or as
    a list of bullets — both are flattened into readable lines here.
    """
    if isinstance(v, dict):
        lines = []
        for k, val in v.items():
            if isinstance(val, list):
                val = "；".join(_to_str(x) for x in val)
            lines.append(f"{k}: {val}")
        return "\n".join(lines)
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    return str(v) if v is not None else ""


def _load_analysis(db, paper):
    try:
        from app.models.paper_analysis import PaperAnalysis

        return db.query(PaperAnalysis).filter(
            PaperAnalysis.paper_id == paper.id
        ).first()
    except Exception:
        return None


def compare_papers(papers: list, db) -> Optional[dict]:
    """Compare 2..N papers. Returns the scaled comparison dict or None."""
    if not LLMService.available():
        return None

    summaries = []
    for i, p in enumerate(papers, start=1):
        summaries.append(
            f"## 论文{i}（id: {p.id}）\n{_paper_summary(p, _load_analysis(db, p))}"
        )
    user_content = "\n\n".join(summaries) + "\n\n请按系统要求输出对比 JSON。"

    try:
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": COMPARE_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=4096,
            feature="compare",
        )
    except Exception:
        return None

    data = _extract_json(reply)
    if not data:
        return None

    # Map per-paper overviews back to the input papers. Prefer positional order
    # (the LLM is asked to output them in the same order), fall back to id match.
    raw_overviews = data.get("papers")
    overviews = []
    if isinstance(raw_overviews, list):
        if len(raw_overviews) == len(papers) and all(
            isinstance(o, dict) for o in raw_overviews
        ):
            overviews = raw_overviews
        else:
            by_id = {
                o.get("paper_id"): o
                for o in raw_overviews
                if isinstance(o, dict) and o.get("paper_id") is not None
            }
            overviews = [by_id.get(p.id) or {} for p in papers]

    papers_out = []
    for i, p in enumerate(papers):
        o = overviews[i] if i < len(overviews) else {}
        papers_out.append({
            "paper_id": p.id,
            "title": p.title or "",
            "summary": _to_str(o.get("one_sentence") or ""),
        })

    return {
        "papers": papers_out,
        "similarities": _to_str(data.get("similarities")),
        "method_differences": _to_str(data.get("method_differences")),
        "experiment_differences": _to_str(data.get("experiment_differences")),
        "conclusion_differences": _to_str(data.get("conclusion_differences")),
        "strengths_weaknesses": _to_str(data.get("strengths_weaknesses")),
        "final_verdict": _to_str(data.get("final_verdict")),
    }
