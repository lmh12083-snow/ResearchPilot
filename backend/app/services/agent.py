"""
Agent service — Function Calling + ReAct loop for the paper assistant.

Tools let the LLM autonomously decide how to gather information:
- search_paper:      semantic search inside the current paper
- search_project:    semantic search across all papers in the project
- search_web:        web search
- get_paper_meta:    paper metadata (title/authors/abstract/...)
- list_project_papers: papers in the current project

Tool results are formatted with running [n] citation numbers so the LLM
can cite its sources and the frontend can display matching tags.
"""

import json

# ── Tool schemas (OpenAI / DeepSeek function-calling format) ──────────

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_paper",
            "description": (
                "在当前论文中做语义检索，找到与问题相关的内容片段。"
                "当用户需要论文中的具体细节（研究方法、实验、结论、数据集等）时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要检索的关键词或问题"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_project",
            "description": (
                "在用户当前的项目中跨论文检索，找到与问题相关的内容片段（包含是哪篇论文）。"
                "当问题可能需要项目中其他论文的信息时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要检索的关键词或问题"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "联网搜索最新资料、论文之外的背景信息或行业动态。"
                "当问题涉及最新进展、本论文之外的资料时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "返回结果条数，默认5", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_meta",
            "description": "获取当前论文的基本信息（标题、作者、摘要、关键词、年份、DOI）。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_papers",
            "description": "列出当前项目中的所有论文（标题、状态）。当用户询问项目里有什么论文时使用。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]

TOOL_LABELS = {
    "search_paper": "📄 检索当前论文",
    "search_project": "📚 检索项目论文",
    "search_web": "🌐 联网搜索",
    "get_paper_meta": "📋 读取论文信息",
    "list_project_papers": "🗂️ 列出项目论文",
}

RELEVANCE_THRESHOLD = 0.30

AGENT_SYSTEM_PROMPT = """你是一个智能学术论文助手（Agent），帮助用户理解论文、检索资料、查找信息。

你可以调用工具获取信息：
- 需要论文中的具体细节（方法/实验/结论）时，先用 search_paper 在当前论文检索；
- 需要项目内其他论文的信息时，用 search_project；
- 需要最新资料或论文外的信息时，用 search_web；
- 需要论文基本信息时，用 get_paper_meta；
- 需要了解项目里有哪些论文时，用 list_project_papers。

规则：
1. 先判断用户需要什么信息，再选择合适的工具（一次可调用多个工具）；
2. 工具返回的每条信息都带引用编号，如 [1]、[2]，回答时必须标注这些编号；
3. 引用编号必须与实际给出的编号一致，不要臆造编号；
4. 如果检索结果不足以回答问题，请如实说明，不要编造；
5. 用中文回答，回答清晰有条理。"""


class AgentExecutor:
    """Executes agent tools, collecting citations in order for the frontend."""

    def __init__(self, paper, db):
        self.paper = paper
        self.db = db
        self.citations = []  # list of Citation
        self._counter = 0

    def _next_citation(self, page_number=None, chunk_index=None, text=None):
        from app.schemas.paper import Citation
        self._counter += 1
        self.citations.append(Citation(
            page_number=page_number,
            chunk_index=chunk_index,
            text=(text or "")[:200],
        ))
        return self._counter

    def execute(self, name: str, arguments: str) -> str:
        """Execute a tool by name. Returns a formatted JSON string for the LLM."""
        args = json.loads(arguments or "{}")
        handler = getattr(self, f"tool_{name}", None)
        if handler is None:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
        return handler(**args)

    # ── Tool implementations ──

    def tool_search_paper(self, query: str) -> str:
        from app.services.hybrid_search import hybrid_search

        results = hybrid_search(query, paper_id=self.paper.id, top_k=8)

        parts = []
        for r in results:
            if r.get("vector_score", 0.0) < RELEVANCE_THRESHOLD:
                continue
            meta = r["metadata"]
            n = self._next_citation(
                page_number=meta.get("page_number"),
                chunk_index=meta.get("chunk_index"),
                text=r["text"],
            )
            page_str = f"，第{meta['page_number']}页" if meta.get("page_number") is not None else ""
            parts.append(f"[{n}] (当前论文，第{meta['chunk_index']}段{page_str})\n{r['text']}")

        if not parts:
            return json.dumps({"results": [], "message": "论文中未找到相关片段"}, ensure_ascii=False)
        return json.dumps({"results": parts}, ensure_ascii=False)

    def tool_search_project(self, query: str) -> str:
        from app.services.hybrid_search import hybrid_search
        from app.models.paper import Paper

        if not self.paper.project_id:
            return json.dumps({"error": "该论文不属于任何项目"}, ensure_ascii=False)

        project_paper_ids = [
            p.id for p in self.db.query(Paper.id)
            .filter(Paper.project_id == self.paper.project_id).all()
        ]
        id_to_title = {
            p.id: p.title for p in self.db.query(Paper).filter(Paper.id.in_(project_paper_ids)).all()
        }

        results = hybrid_search(query, project_paper_ids=project_paper_ids, top_k=10)

        parts = []
        for r in results:
            if r.get("vector_score", 0.0) < RELEVANCE_THRESHOLD:
                continue
            pid = r["metadata"].get("paper_id")
            if pid not in project_paper_ids:
                continue
            meta = r["metadata"]
            n = self._next_citation(
                page_number=meta.get("page_number"),
                chunk_index=meta.get("chunk_index"),
                text=r["text"],
            )
            page_str = f"，第{meta['page_number']}页" if meta.get("page_number") is not None else ""
            parts.append(f"[{n}] (论文《{id_to_title.get(pid, pid)}》，第{meta['chunk_index']}段{page_str})\n{r['text']}")

        if not parts:
            return json.dumps({"results": [], "message": "项目论文中未找到相关片段"}, ensure_ascii=False)
        return json.dumps({"results": parts}, ensure_ascii=False)

    def tool_search_web(self, query: str, max_results: int = 5) -> str:
        from app.services.web_search import WebSearchService

        results = WebSearchService.search(query, max_results=max(1, min(max_results, 8)))
        parts = []
        for r in results:
            n = self._next_citation(text=r.snippet)
            parts.append(f"[{n}] ({r.title})\n来源: {r.url}\n{r.snippet}")

        if not parts:
            return json.dumps({"results": [], "message": "联网搜索未返回结果"}, ensure_ascii=False)
        return json.dumps({"results": parts}, ensure_ascii=False)

    def tool_get_paper_meta(self) -> str:
        p = self.paper
        authors = []
        if p.authors:
            try:
                authors = json.loads(p.authors)
                if isinstance(authors, str):
                    authors = [authors]
            except Exception:
                authors = [p.authors]
        return json.dumps({
            "title": p.title,
            "authors": ", ".join(str(a) for a in authors),
            "year": p.year,
            "abstract": p.abstract,
            "keywords": p.keywords,
            "doi": p.doi,
            "arxiv_id": p.arxiv_id,
            "source": p.source_type.value if hasattr(p.source_type, "value") else str(p.source_type),
        }, ensure_ascii=False)

    def tool_list_project_papers(self) -> str:
        from app.models.paper import Paper
        if not self.paper.project_id:
            return json.dumps({"papers": [], "message": "该论文不属于任何项目"}, ensure_ascii=False)
        papers = self.db.query(Paper).filter(Paper.project_id == self.paper.project_id).all()
        return json.dumps({
            "papers": [
                {"id": p.id, "title": p.title, "status": p.status.value if hasattr(p.status, "value") else str(p.status)}
                for p in papers
            ]
        }, ensure_ascii=False)


def _agent_messages(paper, message: str) -> list[dict]:
    return [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT + f"\n\n当前论文标题：{paper.title}"},
        {"role": "user", "content": message},
    ]


def run_agent(paper, db, message: str, max_steps: int = 4) -> tuple[str, list]:
    """Non-streaming agent loop. Returns (reply_text, citations)."""
    from app.services.llm import LLMService

    executor = AgentExecutor(paper, db)
    messages = _agent_messages(paper, message)

    for _ in range(max_steps):
        msg = LLMService.chat_response(messages, tools=AGENT_TOOLS, temperature=0.3, max_tokens=2048, feature="agent")
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return (msg.get("content") or "").strip(), executor.citations

        messages.append(msg)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            try:
                result_str = executor.execute(name, fn.get("arguments", "{}"))
            except Exception as e:
                result_str = json.dumps({"error": str(e)}, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "content": result_str,
            })

    return "已达到最大工具调用轮数，请尝试更具体的问题。", executor.citations
