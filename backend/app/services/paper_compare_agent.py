"""
Multi-agent paper comparison — Planner → parallel Specialists → Aggregator.

Orchestration (each stage is a separate LLM call, feature-tagged for the LLM
usage dashboard):

  1. Planner   proposes 3-5 comparison dimensions for the given paper set
               (falls back to a fixed dimension list if parsing fails).
  2. Specialists (ThreadPoolExecutor, one per paper) extract each paper's
               stance on every dimension from its cached structured analysis.
  3. Aggregator synthesizes the N x D matrix into the final comparison JSON.

The generator yields ("status", text) / ("result", dict) / ("error", text)
tuples so the SSE endpoint can stream progress live.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from app.services.llm import LLMService
from app.services.paper_compare import _paper_summary, _extract_json, _to_str

FALLBACK_DIMENSIONS = [
    "研究动机与问题",
    "方法与技术路线",
    "实验设计与数据集",
    "主要结论",
    "优势与不足",
]

PLANNER_PROMPT = """你是论文对比策划专家。给定以下论文集合，规划 3-5 个最能体现论文间差异的对比维度。
只输出 JSON 数组，如 ["研究动机", "方法", "实验", "结论"]，不要输出其他文字。

论文列表：
{paper_list}"""

SPECIALIST_PROMPT = """你是论文分析专家。给定一篇论文的结构化信息，按给定的维度提取该论文在每个维度上的要点。
只输出 JSON 对象，键为维度名，值为该论文在该维度的一句话到两句话要点。不要输出其他文字。

论文信息：
{summary}

维度：{dimensions}"""

AGGREGATE_PROMPT = """你是论文对比专家。以下是一个对比矩阵：多篇论文在若干维度上的要点。
请据此生成多论文对比结果。只输出 JSON，不要包含其他文字。字段：
- papers: 数组，每项 {{"paper_id": 数字, "one_sentence": "一句话概述"}}
- similarities: 所有论文的共同点（3-5 点）
- method_differences: 方法与技术路线的主要差异（按论文编号归属）
- experiment_differences: 实验设计与数据集的主要差异
- conclusion_differences: 主要结论与贡献取向的差异
- strengths_weaknesses: 各自的优势与不足（按论文分组）
- final_verdict: 综合对比结论（每篇论文分别适合什么场景）
要求：基于矩阵信息，不要编造；信息不足时如实标注。指代论文时使用其编号，如"论文1"。

对比矩阵：
{matrix}"""


def _plan_dimensions(papers: list) -> list[str]:
    """Planner: propose comparison dimensions for the paper set."""
    try:
        paper_list = "\n".join(
            f"- 论文{i}: {p.title or ''}" for i, p in enumerate(papers, start=1)
        )
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": PLANNER_PROMPT.format(paper_list=paper_list)},
            ],
            temperature=0.3,
            max_tokens=512,
            feature="compare_planner",
        )
        data = _extract_json(reply)
        if isinstance(data, list):
            dims = [str(x).strip() for x in data if str(x).strip()]
            return dims[:5] if dims else list(FALLBACK_DIMENSIONS)
    except Exception:
        pass
    return list(FALLBACK_DIMENSIONS)


def _extract_stances(paper, db, dimensions: list[str]) -> dict:
    """Specialist: extract one paper's stance on every dimension."""
    if not LLMService.available():
        return {}
    try:
        from app.models.paper_analysis import PaperAnalysis

        analysis = db.query(PaperAnalysis).filter(
            PaperAnalysis.paper_id == paper.id
        ).first()
    except Exception:
        analysis = None

    dim_str = "、".join(dimensions)
    try:
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": SPECIALIST_PROMPT.format(
                    summary=_paper_summary(paper, analysis), dimensions=dim_str,
                )},
            ],
            temperature=0.3,
            max_tokens=1024,
            feature="compare_specialist",
        )
        data = _extract_json(reply)
        if isinstance(data, dict):
            return {k: _to_str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _aggregate(papers: list, dimensions: list[str], stances: list[dict]) -> Optional[dict]:
    """Aggregator: synthesize the N x D matrix into the final comparison."""
    if not LLMService.available():
        return None
    rows = []
    for i, p in enumerate(papers, start=1):
        lines = [f"## 论文{i}（id: {p.id}）"]
        s = stances[i - 1] or {}
        if not s:
            lines.append("  (该论文未能提取到有效要点)")
        for dim in dimensions:
            lines.append(f"- {dim}: {s.get(dim, '未提及')}")
        rows.append("\n".join(lines))
    matrix = "\n\n".join(rows)

    try:
        reply = LLMService.chat(
            messages=[
                {"role": "system", "content": AGGREGATE_PROMPT.format(matrix=matrix)},
            ],
            temperature=0.3,
            max_tokens=4096,
            feature="compare_aggregate",
        )
    except Exception:
        return None

    data = _extract_json(reply)
    if not data:
        return None

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


def compare_papers_agent_stream(papers: list, db):
    """Run the multi-agent comparison, yielding stage events as they happen.

    Yields ("status", text) / ("result", dict) / ("error", text).
    """
    if not LLMService.available():
        yield ("error", "LLM 服务未配置")
        return

    n = len(papers)
    yield ("status", f"🧠 Planner 分析 {n} 篇论文，规划对比维度…")
    dimensions = _plan_dimensions(papers)
    yield ("status", f"📐 规划完成：{'、'.join(dimensions[:5])}")

    yield ("status", f"⚡ 并行提取 {n} 篇论文在各维度的要点…")
    stances: list[dict] = [{}] * n
    try:
        with ThreadPoolExecutor(max_workers=min(5, n)) as ex:
            futures = {
                ex.submit(_extract_stances, p, db, dimensions): i
                for i, p in enumerate(papers)
            }
            for fut in futures:
                stances[futures[fut]] = fut.result()
    except Exception:
        pass
    done = sum(1 for s in stances if s)
    yield ("status", f"✅ 要点提取完成（{done}/{n} 篇）")

    yield ("status", "🧩 Aggregator 聚合对比结果…")
    result = _aggregate(papers, dimensions, stances)
    if result is None:
        yield ("error", "对比结果聚合失败，请稍后重试")
        return
    yield ("result", result)
