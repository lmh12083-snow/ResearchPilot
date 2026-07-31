"""
Paper analysis service — generates structured analysis using LLM.
"""
import json
from typing import Optional

from app.services.llm import LLMService
from app.models.paper import Paper
from app.models.paper_analysis import PaperAnalysis


SYSTEM_PROMPT = """你是一个学术论文分析助手。请分析以下论文文本，生成结构化的分析结果。
必须以 JSON 格式输出，不要包含其他文字。JSON 字段：

- abstract: 论文摘要/简介（中文，200字以内）
- innovation: 主要创新点（中文，列举3-5点，每点一句话）
- methods: 研究方法（中文，说明使用的技术、算法、框架）
- experiments: 实验设计（中文，包括数据集、评估指标、基线方法、主要结果）
- limitations: 局限性（中文，2-3点）
- related_work: 相关工作（中文，简要说明与现有工作的关系）
- one_sentence: 一句话总结（中文，20字以内）
- pros_cons: 优缺点分析（中文，优点和缺点各2-3点）

如果论文文本中缺乏某些信息，请根据上下文合理推断或标注"未明确说明"。
"""


def get_or_create_analysis(paper: Paper, parsed_text: str = "") -> Optional[PaperAnalysis]:
    """Get existing analysis or generate one via LLM.

    Generation pipeline: multi-agent (planner/specialists/aggregator) first,
    falling back to a single-shot prompt if the multi-agent run fails.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        existing = db.query(PaperAnalysis).filter(PaperAnalysis.paper_id == paper.id).first()
        if existing:
            return existing

        # Generate analysis
        text = parsed_text or ""
        if not text and paper.parsed_text_path:
            from pathlib import Path
            from app.core.config import settings
            txt_path = Path(settings.UPLOAD_PATH) / paper.parsed_text_path
            if txt_path.exists():
                text = txt_path.read_text(encoding="utf-8")

        if not text or len(text.strip()) < 50:
            return None

        if not LLMService.available():
            return None

        # Truncate to avoid excessive token usage (~50K chars is fine for DeepSeek)
        text = text[:50000]

        # 1) Multi-agent pipeline (targeted retrieval + specialist LLM calls)
        from app.services.analysis_agent import run_multi_agent_analysis

        analysis_data = None
        try:
            analysis_data = run_multi_agent_analysis(paper, parsed_text=text)
        except Exception:
            analysis_data = None

        # 2) Fallback — single monolithic LLM call over the full text
        if not analysis_data:
            try:
                reply = LLMService.chat(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"论文标题: {paper.title}\n\n全文:\n{text}"},
                    ],
                    temperature=0.3,
                    max_tokens=4096,
                    feature="analysis",
                )
            except Exception:
                return None
            analysis_data = _parse_json(reply)
            if not analysis_data:
                return None

        # Ensure all text fields are strings (LLM may return arrays)
        def _to_str(v):
            if isinstance(v, list):
                return "\n".join(str(item) for item in v)
            return str(v) if v is not None else None

        analysis = PaperAnalysis(
            paper_id=paper.id,
            abstract=_to_str(analysis_data.get("abstract")),
            innovation=_to_str(analysis_data.get("innovation")),
            methods=_to_str(analysis_data.get("methods")),
            experiments=_to_str(analysis_data.get("experiments")),
            limitations=_to_str(analysis_data.get("limitations")),
            related_work=_to_str(analysis_data.get("related_work")),
            one_sentence=_to_str(analysis_data.get("one_sentence")),
            pros_cons=_to_str(analysis_data.get("pros_cons")),
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis

    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles ```json fences)."""
    import re

    # Try to find JSON block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
