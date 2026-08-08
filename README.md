# ResearchPilot

**AI research paper copilot** — a full-stack academic paper management & RAG platform that turns your PDF library into an interactive reading, Q&A, and writing workspace.

RAG chat with hybrid retrieval & reranking · multi-agent paper analysis & comparison · automatic literature review · reading notes with Markdown export · LLM-judged RAG evaluation.

Built with **FastAPI · Vue 3 · ChromaDB · DeepSeek**.

> ⚠️ **自行配置 API Key / API key required** — 本仓库不内置任何 API Key。若需要使用本项目，请先在 `.env` 中自行填入 `DEEPSEEK_API_KEY`（DeepSeek 官方 key，OpenAI 兼容接口）。未配置时对话 / 分析 / 综述 / 评测等 LLM 功能不可用。No API keys are bundled with this repository — provide your own `DEEPSEEK_API_KEY` to enable the LLM-powered features.

---

## ✨ Features

### 1. Paper management
- Upload PDFs (auto-detect layout → pdfplumber / PyMuPDF / optional OCR) or import directly from arXiv.
- Asynchronous processing pipeline: **parse → chunk → embed → index**, with per-step progress and status tracking.

### 2. RAG chat (4 retrieval modes)
- `📄 paper_only` — answer strictly from one paper
- `📚 project_search` — retrieve across an entire project's papers
- `🌐 web_search` — DuckDuckGo / Bing search (agentic, returns citations)
- `🤖 auto` — the agent decides retrieval strategy per question
- SSE **token streaming** with per-answer **citations** back to page / chunk, and no-answer fallback suggestions.

### 3. Hybrid retrieval & reranking
Dense vectors (ChromaDB) + **BM25** sparse keyword matching, fused by **Reciprocal Rank Fusion (RRF)**, then re-ranked by a **cross-encoder** (`mmarco-mMiniLMv2-L12-H384-v1`). CJK-aware tokenization.

### 4. Multi-agent paper analysis
Instead of one monolithic LLM call, a **Planner** generates per-dimension retrieval queries, then **parallel specialists** each analyze one dimension against targeted context (innovation / methods / experiments / limitations / related work), and an **Aggregator** merges them into an 8-field structured analysis (plus abstract, pros & cons, one-line summary).

### 5. Multi-paper comparison (2–5 papers)
Two modes:
- **Single-call** comparison for a quick structured result
- **Multi-agent** orchestration: **Planner** → parallel **Specialists** → **Aggregator**, streamed via SSE with live status.

### 6. Automatic literature review
Streams a full survey document: **Planner** proposes the section outline → intro → each section (cited `[1]`, `[2]`…) → conclusion → auto-generated reference list. Copy / download the Markdown result.

### 7. Reading notes & Markdown export
Annotate papers — capture selected text as an anchor, add notes and tags, or let the **LLM summarize** key points. Export everything as structured **Markdown** grouped by project and paper.

### 8. RAG evaluation
Self-contained evaluation harness: **LLM-generates a validated test set** from your own papers, then measures **hit@1/3/5, MRR, answer accuracy, and faithfulness** (LLM-as-judge) in background jobs with live progress. No external benchmark data needed. Questions are filtered for validity (answerable from their source chunk) and reference/bibliography sections are excluded, so metrics reflect real content retrieval.

Measured on 32 validated questions across 2 papers: the production hybrid pipeline lifts **hit@1 from 31% → 66%, hit@5 from 59% → 91%, MRR 0.41 → 0.77** vs. pure dense retrieval, with **84% answer accuracy and 88% faithfulness**.

### 9. Dashboard, account & usage
Project/paper dashboards, avatar upload, profile & password management, and per-feature **LLM token usage tracking**.

---

## 🏗 Architecture

```
┌───────────────────────────  Frontend (Vue 3 + TS + Element Plus)  ───────────────────────────┐
│  Dashboard · Projects · PaperReading (PDF+Text+Notes) · RAG Eval · Settings                  │
│  SSE reader clients: chat / compare / review    Axios REST clients                            │
└───────────────────────────────┬──────────────────────────────────────────────────────────────┘
                                │ REST + SSE (JWT)
┌───────────────────────────────▼──────────────────────────────────────────────────────────────┐
│                                   FastAPI (Python 3.12)                                      │
│                                                                                              │
│  ┌─ Paper Pipeline ─────┐   ┌─ Retrieval ──────────────┐   ┌─ Agent Orchestration ────────┐  │
│  │ parse (pdfplumber/    │   │ dense: ChromaDB          │   │ Analysis:  Planner →        │  │
│  │  pymupdf / OCR)       │   │ sparse: BM25             │   │            Spec → Aggregator │  │
│  │ chunk → embed → index │   │ fuse: RRF                │   │ Compare:   Planner → Spec → │  │
│  └───────────────────────┘   │ rerank: cross-encoder    │   │            Aggregator        │  │
│                              └──────────────────────────┘   │ Review:    Planner → sections│  │
│  ┌─ RAG Eval ─────────────┐                                 └──────────────────────────────┘  │
│  │ self-gen test set →     │   ┌─ LLM (DeepSeek, OpenAI-   │                                  │
│  │ retrieve/answer/judge   │   │   compatible) + usage log │                                  │
│  │ (background job)        │   └───────────────────────────┘                                  │
│  └─────────────────────────┘                                                                 │
└───────────────────────────┬───────────────────────────────┬──────────────────────────────────┘
                            │                               │
                     ┌──────▼──────┐                 ┌──────▼──────┐
                     │    MySQL    │                 │   ChromaDB  │
                     │ (SQLAlchemy)│                 │  (vectors)  │
                     └─────────────┘                 └─────────────┘
```

---

## 🛠 Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 |
| Frontend | Vue 3 · TypeScript · Vite · Pinia · Vue Router · Element Plus |
| Database | MySQL (`pymysql`) · ChromaDB (vector store) |
| Retrieval | sentence-transformers · `rank_bm25` · cross-encoder reranker |
| LLM | DeepSeek (OpenAI-compatible) · SSE streaming |
| Auth | JWT (python-jose) · passlib/bcrypt |
| Misc | Alembic · httpx · ddgs (web search) |

---

## 🚀 Quick Start

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` (see [Configuration](#configuration) below), then start:

```bash
python -m uvicorn app.main:app --reload --port 8006
```

Tables are created automatically on startup. ChromaDB vectors and uploaded files persist under `backend/chroma_db/` and `backend/uploads/`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Register an account in the UI, create a project, upload a PDF, and wait for the paper to reach `已完成` (COMPLETED) — then try analysis, chat, comparison, review, and notes.

---

## 🐳 Docker 部署（一键起全套）

`docker compose` 一键拉起 **MySQL + 后端 + 前端（nginx 反向代理）**，`http://localhost:8080` 即完整应用。REST 与 SSE 流式经 nginx `/api/` 同源代理，无需配置 CORS。

```bash
# 1. 在仓库根目录 .env 中填入 DEEPSEEK_API_KEY（可先 cp .env.example .env）
# 2. 构建并启动（首次构建会拉取基础镜像并安装依赖，约需数分钟）
docker compose up --build
```

> **Embedding / reranker 模型不下载进镜像**，而是把宿主机 HuggingFace 缓存挂载进容器（`/root/.cache/huggingface`），并设 `HF_HUB_OFFLINE=1` 纯离线加载。原因是国内网络下 huggingface.co 被墙、`hf-mirror.com` 会 308 重定向回源站，构建时下载不可靠。首次对话/上传即从缓存加载，无需等待。缓存路径默认取本机家目录 `~/.cache/huggingface`，如需指定请在 `.env` 里设置 `HF_CACHE_DIR`（如 Windows 上 `HF_CACHE_DIR=C:/Users/<you>/.cache/huggingface`）。

**演示路径（无需本地 PDF）：** 注册账号 → 新建项目 → 用 arXiv 导入功能粘贴一个 arXiv ID（如 `2007.01282`），系统自动下载并走解析 → 分块 → 向量化管线 → 论文状态变为「已完成」后即可体验分析 / 对话 / 对比 / 综述 / 评测。

**数据持久化：** MySQL 数据、ChromaDB 向量库、上传文件分别存于命名卷 `mysql_data` / `chroma_data` / `uploads_data`，`docker compose down` 不会丢失，`docker compose down -v` 才会清空重建。

**环境变量：** 见下表。容器内 `DATABASE_URL` 指向 MySQL 服务（`mysql`）、`UPLOAD_PATH=/app/uploads`、`CHROMA_PERSIST_DIR=/app/chroma_db`，由 compose 统一覆盖，无需手动改代码。

---

## ⚙️ Configuration

Backend reads `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://user:pass@localhost/researchpilot` | MySQL connection |
| `JWT_SECRET_KEY` | — | Change in production |
| `DEEPSEEK_API_KEY` | — | LLM API key |
| `LLM_API_BASE` | `https://api.deepseek.com` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `deepseek-chat` | Model name |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | Local sentence-transformer |
| `WEB_SEARCH_PROVIDER` | `duckduckgo` | `duckduckgo` \| `bing` |
| `BING_SEARCH_API_KEY` | — | Optional, if using Bing |

---

## 📁 Project Structure

```
ResearchPilot/
├── frontend/
│   └── src/
│       ├── views/          # Dashboard · Projects · PaperReading · Eval · Settings · Login
│       ├── api/            # REST + SSE clients (chat / compare / review streaming)
│       ├── components/     # AppLayout, shared components
│       └── stores/         # Pinia (user)
└── backend/
    └── app/
        ├── api/            # FastAPI routers (auth, project, paper, notes, eval, llm, dashboard)
        ├── services/       # hybrid_search · embedding · vector_store · agent ·
        │                   # analysis_agent · paper_compare* · lit_review · rag_eval ·
        │                   # web_search · metadata · chunker · llm
        ├── pdf_parser/     # parser pipeline (pdfplumber / pymupdf / OCR)
        ├── models/         # SQLAlchemy models
        ├── schemas/        # Pydantic schemas
        └── core/           # config · security · database
```

---

## 📝 Roadmap

- [x] Paper upload & arXiv import with processing pipeline
- [x] Hybrid RAG retrieval + cross-encoder reranking
- [x] Multi-agent paper analysis (8 dimensions)
- [x] Multi-paper comparison (single-call + multi-agent streaming)
- [x] Automatic literature review (streamed, cited)
- [x] Reading notes + AI summarize + Markdown export
- [x] RAG evaluation (self-generated test set, LLM judge)
- [x] Settings (avatar / profile / password) & LLM usage stats
- [ ] Feedback loop: promote eval failures into better chunking/retrieval
- [ ] Batch literature-review over the full project
