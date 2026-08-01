"""
Literature review generation — Planner → section-wise Writer.

1. Planner proposes a review outline (4-6 sections) from per-paper summaries.
2. Writer generates each section in a separate LLM call (keeps each call short),
   citing papers as [1], [2], … in the user's chosen order.
3. Intro (abstract/overview) and conclusion are generated too, then assembled
   into a single Markdown document with a reference list.

The generator yields ("status", text) / ("result", markdown) / ("error", text)
so the SSE endpoint can stream progress live.

All LLM calls are feature-tagged (review_planner / review_section /
review_intro) for the usage dashboard.
"""

import json
import re

from app.services.llm import LLMService
from app.services.paper_compare import _paper_summary, _load_analysis

FALLBACK_SECTIONS = [
    "研究背景与问题",
    "方法分类与综述",
    "关键发现与实验对比",
    "挑战与开放问题",
    "总结与展望",
]

PLANNER_PROMPT = """你是文献综述策划专家。给定若干论文的一句话总结，规划 4-6 个综述章节标题，覆盖：研究背景、方法分类、对比分析、挑战与未来方向。
只输出 JSON 数组，如 ["研究背景","方法综述","技术对比","挑战与展望"]，不要输出其他文字。

论文列表：
{paper_list}"""

SECTION_PROMPT = """你是文献综述写作专家。正在撰写一篇文献综述，请撰写下面这一章节。
要求：
1. 内容必须基于提供的论文信息，不得编造；信息不足时如实说明；
2. 引用论文时用 [编号] 标注，编号与论文列表一致，例如"研究者[1]提出…"；
3. 使用 Markdown 小标题（###）与条目组织内容，条理清晰；
4. 中文写作，学术、客观、简洁，避免空话套话。

论文列表（[N] 对应论文 N 的信息）：
{paper_profiles}

本章节标题：{section}"""

INTRO_PROMPT = """你是文献综述写作专家。给定论文列表，撰写综述的【摘要与概述】，用 Markdown 写 2-3 段。
要点：综述覆盖的主题范围、论文数量与研究主题分布、综述的整体结构安排。
要求：基于提供的论文信息，引用时用 [编号]，中文学术写作，不得编造。

论文列表：
{paper_profiles}"""

CONCLUSION_PROMPT = """你是文献综述写作专家。给定论文列表，撰写综述的【结论与未来展望】，用 Markdown 写 2-3 段。
要点：当前研究的主要共识与不足、未来值得探索的方向。
要求：基于提供的论文信息，引用时用 [编号]，中文学术写作，不得编造。

论文列表：
{paper_profiles}"""


def _extract_json_list(text):
    """Tolerant extraction of a JSON array from LLM output."""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, list) else None
        except Exception:
            return None
    return None


def _paper_profiles(papers, db) -> str:
    """Per-paper summaries, labeled [1], [2], … for citation."""
    lines = []
    for i, p in enumerate(papers, start=1):
        summary = _paper_summary(p, _load_analysis(db, p))
        lines.append(f"[{i}] 论文{i}: {p.title or ''}\n{summary}")
    return "\n\n".join(lines)


def _plan_sections(papers, db) -> list[str]:
    """Planner: propose review sections. Falls back on any failure."""
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
            feature="review_planner",
        )
        data = _extract_json_list(reply)
        if isinstance(data, list):
            sections = [str(x).strip() for x in data if str(x).strip()]
            if len(sections) >= 3:
                return sections[:6]
    except Exception:
        pass
    return list(FALLBACK_SECTIONS)


def _write(profile_md, prompt, feature) -> str:
    return (
        LLMService.chat(
            messages=[{"role": "system", "content": prompt.format(paper_profiles=profile_md)}],
            temperature=0.4,
            max_tokens=1500,
            feature=feature,
        )
        or ""
    ).strip()


def generate_lit_review_stream(papers, db):
    """Run the review generation, yielding stage events.

    Yields ("status", text) / ("result", markdown) / ("error", text).
    """
    if not LLMService.available():
        yield ("error", "LLM 服务未配置")
        return

    n = len(papers)
    yield ("status", f"🧠 Planner 规划综述结构（{n} 篇论文）…")
    sections = _plan_sections(papers, db)
    yield ("status", f"📑 结构：{' → '.join(sections)}")

    profiles = _paper_profiles(papers, db)
    if len(profiles) > 12000:
        profiles = profiles[:12000]

    parts = []

    yield ("status", "📝 撰写摘要与概述…")
    try:
        parts.append(f"# 文献综述\n\n{_write(profiles, INTRO_PROMPT, 'review_intro')}")
    except Exception as e:
        parts.append(f"# 文献综述\n\n> 摘要生成失败：{e}")

    for i, sec in enumerate(sections, start=1):
        yield ("status", f"✍️ 撰写第 {i}/{len(sections)} 章：{sec}…")
        try:
            body = _write(profiles, SECTION_PROMPT, "review_section")
            # The section prompt includes a placeholder; swap the header in.
            parts.append(f"\n\n## {sec}\n\n{body}")
        except Exception as e:
            parts.append(f"\n\n## {sec}\n\n> 该章节生成失败：{e}")

    yield ("status", "🧩 撰写结论与展望…")
    try:
        parts.append(f"\n\n## 结论与展望\n\n{_write(profiles, CONCLUSION_PROMPT, 'review_section')}")
    except Exception as e:
        parts.append(f"\n\n## 结论与展望\n\n> 生成失败：{e}")

    refs = "\n".join(
        f"[{i}] {p.title or f'Paper {i}'}" for i, p in enumerate(papers, start=1)
    )
    parts.append(f"\n\n## 参考文献\n\n{refs}")

    yield ("result", "\n".join(parts))
