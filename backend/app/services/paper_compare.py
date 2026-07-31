"""
Paper comparison service — structured side-by-side comparison of two papers.

Leverages the cached structured analysis of each paper (8 dimensions) when
available, so the comparator reasons over aligned facets (methods, experiments,
limitations, …) instead of raw text. Falls back to metadata + abstract for
papers that haven't been analyzed yet.
"""

import json
import re
from typing import Optional

from app.services.llm import LLMService

COMPARE_SYSTEM = """你是一个论文对比专家。给定两篇论文的结构化信息，从以下维度进行客观、具体的对比。
只输出 JSON，不要包含其他文字。字段（全部为字符串）：
- overview: 总体概述（分别一句话说明两篇论文研究什么问题、提出什么）
- similarities: 两篇论文的共同点（3-5点）
- method_differences: 方法/技术路线的主要差异
- experiment_differences: 实验设计、数据集与结果的主要差异
- conclusion_differences: 主要结论与贡献取向的差异
- strengths_weaknesses: 各自的优势与不足
- final_verdict: 对比结论（分别适合什么场景，谁更胜一筹）
要求：基于给出的信息对比，不要编造不存在的内容；信息不足时如实标注。"""


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


def compare_papers(paper_a, paper_b, db) -> Optional[dict]:
    """Compare two papers. Returns the 7-field comparison dict or None."""
    if not LLMService.available():
        return None

    # Reuse cached structured analyses when available (no forcing — keeps the
    # comparison responsive even for papers that haven't been analyzed).
    analysis_a = analysis_b = None
    try:
        from app.models.paper_analysis import PaperAnalysis

        analysis_a = db.query(PaperAnalysis).filter(
            PaperAnalysis.paper_id == paper_a.id
        ).first()
        analysis_b = db.query(PaperAnalysis).filter(
            PaperAnalysis.paper_id == paper_b.id
        ).first()
    except Exception:
        pass

    summary_a = _paper_summary(paper_a, analysis_a)
    summary_b = _paper_summary(paper_b, analysis_b)

    try:
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": COMPARE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"## 论文 A\n{summary_a}\n\n"
                        f"## 论文 B\n{summary_b}\n\n"
                        f"请按系统要求输出对比 JSON。"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=2048,
            feature="compare",
        )
    except Exception:
        return None

    data = _extract_json(reply)
    if not data:
        return None

    def _to_str(v):
        if isinstance(v, list):
            return "\n".join(str(x) for x in v)
        return str(v) if v is not None else ""

    return {
        "overview": _to_str(data.get("overview")),
        "similarities": _to_str(data.get("similarities")),
        "method_differences": _to_str(data.get("method_differences")),
        "experiment_differences": _to_str(data.get("experiment_differences")),
        "conclusion_differences": _to_str(data.get("conclusion_differences")),
        "strengths_weaknesses": _to_str(data.get("strengths_weaknesses")),
        "final_verdict": _to_str(data.get("final_verdict")),
    }
