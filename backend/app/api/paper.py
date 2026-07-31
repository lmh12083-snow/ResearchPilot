import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, BackgroundTasks, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.models.paper import Paper, PaperStatus, PaperSource
from typing import Optional, Union, Dict
from app.models.project import Project
from app.schemas.paper import (
    PaperResponse,
    PaperStatusResponse,
    ArxivImportRequest,
    SearchRequest,
    SearchResponse,
    PaperContentResponse,
)
from app.api.auth import get_current_user
from app.models.user import User
from app.pdf_parser import parse_pdf, get_full_text
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStore
from app.services.metadata import enrich_paper_metadata
from app.services.paper_analyzer import get_or_create_analysis
from app.services.web_search import WebSearchService
from app.models.paper_analysis import PaperAnalysis
from app.models.chat_message import ChatMessage
from app.schemas.paper import (
    AnalysisResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    Citation,
    CompareRequest,
    CompareResponse,
)

router = APIRouter(prefix="", tags=["papers"])

ALLOWED_EXTENSIONS = {".pdf"}
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}.pdf"
ARXIV_ABS_URL = "https://arxiv.org/abs/{arxiv_id}"


def _ensure_user_upload_dir(user_id: int) -> Path:
    dir_path = Path(settings.UPLOAD_PATH) / f"user_{user_id}"
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _create_paper_record(
    db: Session,
    project_id: int,
    title: str,
    source_type: PaperSource,
    file_name: Optional[str],
    file_path: Optional[str],
    file_size: Optional[int],
    arxiv_id: Optional[str] = None,
) -> Paper:
    paper = Paper(
        project_id=project_id,
        title=title,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
        source_type=source_type,
        arxiv_id=arxiv_id,
        status=PaperStatus.UPLOADING,
        processing_progress=0,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


def _update_status(
    db: Session,
    paper: Paper,
    status: PaperStatus,
    progress: Optional[int] = None,
    error: Optional[str] = None,
):
    paper.status = status
    if progress is not None:
        paper.processing_progress = progress
    if error is not None:
        paper.error_message = error
    db.commit()
    db.refresh(paper)


# ── Background Parsing ────────────────────────────────────────────


def _run_parsing(paper_id: int, upload_dir: str):
    """Background task: parse PDF, chunk, embed, and index into vector store."""
    from app.core.database import SessionLocal
    from app.services.chunker import chunk_text
    from app.services.embedding import EmbeddingService
    from app.services.vector_store import VectorStore

    db = SessionLocal()
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    try:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper or not paper.file_path:
            return

        pdf_path = Path(upload_dir) / paper.file_path
        if not pdf_path.exists():
            _update_status(db, paper, PaperStatus.FAILED, error="PDF file not found")
            return

        # ── PARSING ──
        _update_status(db, paper, PaperStatus.PARSING, progress=30)

        result = parse_pdf(pdf_path)

        # Save extracted text alongside the PDF
        txt_name = pdf_path.stem + ".txt"
        txt_path = pdf_path.with_name(txt_name)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(get_full_text(result))

        rel_txt_path = str(Path(paper.file_path).with_name(txt_name))
        paper.parsed_text_path = rel_txt_path
        paper.page_count = result.page_count
        db.commit()

        # ── CHUNKING ──
        _update_status(db, paper, PaperStatus.CHUNKING, progress=50)
        full_text = get_full_text(result)
        chunks = chunk_text(
            full_text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            page_count=result.page_count,
            total_length=result.total_text_length,
        )

        if not chunks:
            _update_status(db, paper, PaperStatus.FAILED, error="Chunking produced zero chunks")
            return

        paper.chunk_count = len(chunks)
        db.commit()

        # ── EMBEDDING ──
        _update_status(db, paper, PaperStatus.EMBEDDING, progress=70)
        texts = [c["text"] for c in chunks]
        embeddings = EmbeddingService.embed(texts)

        # ── INDEXING ──
        _update_status(db, paper, PaperStatus.INDEXING, progress=90)

        # Remove any existing chunks for this paper (re-processing)
        vs.delete_paper_chunks(paper.id)
        vs.add_paper_chunks(paper.id, chunks, embeddings)

        # ── COMPLETED ──
        _update_status(db, paper, PaperStatus.COMPLETED, progress=100)

    except Exception as e:
        try:
            _update_status(db, paper, PaperStatus.FAILED, error=str(e))
        except Exception:
            pass
    finally:
        db.close()


# ── Upload ──────────────────────────────────────────────────────


@router.post("/papers/upload", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
def upload_paper(
    project_id: int = Form(...),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify project ownership
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Only PDF allowed.")

    # Save file with UUID name
    unique_name = f"paper_{uuid.uuid4().hex}{ext}"
    upload_dir = _ensure_user_upload_dir(current_user.id)
    save_path = upload_dir / unique_name

    content = file.file.read()
    file_size = len(content)
    with open(save_path, "wb") as f:
        f.write(content)

    rel_path = f"user_{current_user.id}/{unique_name}"

    paper = _create_paper_record(
        db=db,
        project_id=project_id,
        title=file.filename or "untitled",
        source_type=PaperSource.UPLOAD,
        file_name=file.filename,
        file_path=rel_path,
        file_size=file_size,
    )

    # Transition to PENDING then kick off background parsing
    _update_status(db, paper, PaperStatus.PENDING, progress=10)
    background_tasks.add_task(_run_parsing, paper.id, settings.UPLOAD_PATH)

    return paper


# ── arXiv Import ────────────────────────────────────────────────


@router.post("/papers/arxiv", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
def import_arxiv(
    data: ArxivImportRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify project ownership
    project = db.query(Project).filter(
        Project.id == data.project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    arxiv_id = data.arxiv_id.strip()
    # Basic arXiv ID validation (e.g. "1706.03762" or "1706.03762v1")
    if not arxiv_id.replace("v", "").replace(".", "").isdigit():
        raise HTTPException(status_code=400, detail="Invalid arXiv ID format")

    # Check for duplicate
    existing = db.query(Paper).filter(
        Paper.arxiv_id == arxiv_id, Paper.project_id == data.project_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This arXiv paper is already in the project")

    pdf_url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    paper = _create_paper_record(
        db=db,
        project_id=data.project_id,
        title=f"arXiv:{arxiv_id}",
        source_type=PaperSource.ARXIV,
        file_name=f"arxiv_{arxiv_id}.pdf",
        file_path=None,
        file_size=None,
        arxiv_id=arxiv_id,
    )

    # Download PDF
    try:
        resp = httpx.get(pdf_url, follow_redirects=True, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        _update_status(db, paper, PaperStatus.FAILED, error=f"Download failed: {str(e)}")
        raise HTTPException(status_code=502, detail=f"Failed to download PDF from arXiv: {str(e)}")

    # Save file
    unique_name = f"arxiv_{arxiv_id}.pdf"
    upload_dir = _ensure_user_upload_dir(current_user.id)
    save_path = upload_dir / unique_name

    with open(save_path, "wb") as f:
        f.write(resp.content)

    rel_path = f"user_{current_user.id}/{unique_name}"
    paper.file_path = rel_path
    paper.file_size = len(resp.content)

    # Enrich metadata from arXiv + Semantic Scholar
    try:
        meta = enrich_paper_metadata(arxiv_id=arxiv_id)
        if meta.get("title"):
            paper.title = meta["title"]
        if meta.get("authors"):
            paper.authors = meta["authors"]
        if meta.get("abstract"):
            paper.abstract = meta["abstract"]
        if meta.get("doi"):
            paper.doi = meta["doi"]
        if meta.get("year"):
            paper.year = meta["year"]
        if meta.get("keywords"):
            paper.keywords = meta["keywords"]
        db.commit()
    except Exception:
        pass  # Non-blocking — paper still works without enriched metadata

    # Transition to PENDING then kick off background parsing
    _update_status(db, paper, PaperStatus.PENDING, progress=10)
    background_tasks.add_task(_run_parsing, paper.id, settings.UPLOAD_PATH)

    return paper


# ── Status ──────────────────────────────────────────────────────


@router.get("/papers/{paper_id}/status", response_model=PaperStatusResponse)
def get_paper_status(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


# ── Semantic Search ──────────────────────────────────────────────


@router.post("/papers/search", response_model=SearchResponse)
def search_papers(
    data: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Semantic search across paper chunks."""
    if not data.query.strip():
        return SearchResponse(results=[])

    from app.services.hybrid_search import hybrid_search

    # Restrict retrieval to papers owned by the current user
    owned_paper_ids = [
        p.id
        for p in db.query(Paper.id)
        .join(Project, Project.id == Paper.project_id)
        .filter(Project.user_id == current_user.id)
        .all()
    ]
    owned_set = set(owned_paper_ids)

    # Hybrid retrieval (vector + BM25 + rerank), scoped to the user's papers
    if data.paper_id:
        if data.paper_id not in owned_set:
            return SearchResponse(results=[])
        raw_results = hybrid_search(data.query, paper_id=data.paper_id, top_k=data.top_k)
    elif data.project_id:
        project = db.query(Project).filter(
            Project.id == data.project_id, Project.user_id == current_user.id
        ).first()
        if not project:
            return SearchResponse(results=[])
        project_paper_ids = [
            p.id for p in db.query(Paper.id).filter(Paper.project_id == data.project_id).all()
        ]
        raw_results = hybrid_search(data.query, project_paper_ids=project_paper_ids, top_k=data.top_k)
    else:
        raw_results = hybrid_search(data.query, project_paper_ids=owned_paper_ids, top_k=data.top_k)

    # Enrich with paper titles
    paper_cache: Dict[int, Optional[Paper]] = {}
    enriched: list = []

    for r in raw_results:
        pid = r["metadata"]["paper_id"]
        if pid not in owned_set:
            continue

        if pid not in paper_cache:
            paper_cache[pid] = db.query(Paper).filter(Paper.id == pid).first()
        paper = paper_cache[pid]
        if paper is None:
            continue

        enriched.append({
            "chunk_id": r["id"],
            "text": r["text"],
            "paper_id": pid,
            "paper_title": paper.title,
            "page_number": r["metadata"].get("page_number"),
            "chunk_index": r["metadata"].get("chunk_index", 0),
            "score": round(r.get("vector_score", 0.0), 4),
        })

        if len(enriched) >= data.top_k:
            break

    return SearchResponse(results=enriched[: data.top_k])


# ── Paper Content ────────────────────────────────────────────────


@router.get("/papers/{paper_id}/content", response_model=PaperContentResponse)
def get_paper_content(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full parsed text content of a paper for reading."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.parsed_text_path:
        return PaperContentResponse(
            id=paper.id,
            project_id=paper.project_id,
            title=paper.title,
            text="",
            page_count=paper.page_count,
            chunk_count=paper.chunk_count,
            status=paper.status,
        )

    txt_path = Path(settings.UPLOAD_PATH) / paper.parsed_text_path
    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Parsed text file not found")

    text = txt_path.read_text(encoding="utf-8")
    return PaperContentResponse(
        id=paper.id,
        project_id=paper.project_id,
        title=paper.title,
        text=text,
        page_count=paper.page_count,
        chunk_count=paper.chunk_count,
        status=paper.status,
    )


# ── PDF File ──────────────────────────────────────────────────


@router.get("/papers/{paper_id}/file")
def get_paper_file(
    paper_id: int,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """Serve the original PDF file for in-browser viewing.

    Supports both header-based (axios) and query-param (iframe) auth.
    """
    # Try header-based auth first, then query-param token
    auth_token = authorization[7:] if authorization and authorization.startswith("Bearer ") else token
    if not auth_token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    from app.core.security import decode_access_token
    payload = decode_access_token(auth_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.file_path:
        raise HTTPException(status_code=404, detail="Paper file not found")

    pdf_path = Path(settings.UPLOAD_PATH) / paper.file_path
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    filename = paper.file_name or f"paper_{paper_id}.pdf"
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""},
    )


# ── List / Get / Delete ─────────────────────────────────────────


@router.get("/projects/{project_id}/papers", response_model=list[PaperResponse])
def list_papers(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Paper).filter(Paper.project_id == project_id).order_by(Paper.created_at.desc()).all()


@router.get("/papers/{paper_id}", response_model=PaperResponse)
def get_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.delete("/papers/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Delete from vector store
    from app.services.vector_store import VectorStore
    vs = VectorStore(settings.CHROMA_PERSIST_DIR)
    vs.delete_paper_chunks(paper.id)

    if paper.file_path:
        full_path = Path(settings.UPLOAD_PATH) / paper.file_path
        if full_path.exists():
            full_path.unlink()

    if paper.parsed_text_path:
        txt_full_path = Path(settings.UPLOAD_PATH) / paper.parsed_text_path
        if txt_full_path.exists():
            txt_full_path.unlink()

    db.delete(paper)
    db.commit()


# ── Analysis ──────────────────────────────────────────────────────


@router.get("/papers/{paper_id}/analysis", response_model=AnalysisResponse)
def get_paper_analysis(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get paper analysis. Generates via LLM if not already cached."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Try to get parsed text for LLM
    text = ""
    if paper.parsed_text_path:
        txt_path = Path(settings.UPLOAD_PATH) / paper.parsed_text_path
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8")

    analysis = get_or_create_analysis(paper, parsed_text=text)
    if analysis is None:
        raise HTTPException(
            status_code=503,
            detail="Analysis unavailable. LLM may not be configured, or paper text is insufficient.",
        )

    return analysis


@router.post("/papers/{paper_id}/analysis", response_model=AnalysisResponse)
def regenerate_paper_analysis(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Force-regenerate paper analysis by deleting cached version first."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    # Delete existing analysis
    existing = db.query(PaperAnalysis).filter(PaperAnalysis.paper_id == paper_id).first()
    if existing:
        db.delete(existing)
        db.commit()

    # Get parsed text
    text = ""
    if paper.parsed_text_path:
        txt_path = Path(settings.UPLOAD_PATH) / paper.parsed_text_path
        if txt_path.exists():
            text = txt_path.read_text(encoding="utf-8")

    analysis = get_or_create_analysis(paper, parsed_text=text)
    if analysis is None:
        raise HTTPException(
            status_code=503,
            detail="Analysis unavailable. LLM may not be configured, or paper text is insufficient.",
        )

    return analysis


# ── Compare ──────────────────────────────────────────────────────


@router.post("/papers/compare", response_model=CompareResponse)
def compare_papers(
    data: CompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured comparison of two papers (LLM-generated)."""
    if len(data.paper_ids) != 2:
        raise HTTPException(status_code=400, detail="请选择两篇论文进行对比")

    owned_paper_ids = {
        p.id
        for p in db.query(Paper.id)
        .join(Project, Project.id == Paper.project_id)
        .filter(Project.user_id == current_user.id)
        .all()
    }
    for pid in data.paper_ids:
        if pid not in owned_paper_ids:
            raise HTTPException(status_code=404, detail=f"论文 {pid} 不存在或无权访问")

    paper_a = db.query(Paper).filter(Paper.id == data.paper_ids[0]).first()
    paper_b = db.query(Paper).filter(Paper.id == data.paper_ids[1]).first()

    from app.services.paper_compare import compare_papers as run_compare

    result = run_compare(paper_a, paper_b, db)
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="对比生成失败。LLM 可能未配置，请稍后重试。",
        )
    return CompareResponse(**result)


# ── Chat ──────────────────────────────────────────────────────────


def _sse(event: str, data: dict) -> str:
    """Format an SSE event frame."""
    import json
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _prepare_chat(paper: Paper, db: Session, mode: str, message: str) -> dict:
    """Shared retrieval + prompt construction for chat endpoints.

    Returns dict with keys: system_prompt, citations, has_answer, suggestions.
    """
    from app.services.hybrid_search import hybrid_search

    # ── Web Search mode ──
    if mode == "web_search":
        web_results = WebSearchService.search(message, max_results=5)
        if web_results:
            context_parts = []
            citations_data = []
            for i, r in enumerate(web_results):
                context_parts.append(
                    f"[{i+1}] ({r.title})\n来源: {r.url}\n{r.snippet}"
                )
                citations_data.append(Citation(
                    page_number=None,
                    chunk_index=None,
                    text=r.snippet[:200],
                ))

            context_text = "\n\n".join(context_parts)

            system_prompt = (
                f"你是一个学术论文助手。用户正在阅读论文：{paper.title}\n"
                f"用户的问题是：{message}\n\n"
                f"以下是从网络搜索中获取的相关信息：\n\n{context_text}\n\n"
                f"要求：\n"
                f"1. 基于以上搜索结果回答用户问题\n"
                f"2. 每引用一个信息源必须在末尾标注编号，如 [1]、[2]\n"
                f"3. 请在回答末尾注明信息来源为网络搜索\n"
                f"4. 如果搜索结果不足以回答问题，请如实说明"
            )
            has_answer = True
            suggestions = []
        else:
            context_text = ""
            citations_data = []
            suggestions = [
                "仅基于当前论文回答",
                "在当前 Project 中继续检索",
                "查找相关最新论文",
            ]
            system_prompt = (
                f"你是一个学术论文助手。用户正在阅读论文：{paper.title}\n"
                f"用户的问题是：{message}\n\n"
                f"注意：网络搜索未能获取到相关信息。请如实告知用户搜索失败，"
                f"并建议用户尝试其他模式。"
            )
            has_answer = False

    # ── Paper / Project search mode ──
    else:
        if mode == "project_search" and paper.project_id:
            # Hybrid search across all papers in the project
            project_paper_ids = [
                p.id for p in db.query(Paper.id).filter(Paper.project_id == paper.project_id).all()
            ]
            raw_results = hybrid_search(message, project_paper_ids=project_paper_ids, top_k=5)
        else:
            # paper_only (default): hybrid search within this paper
            raw_results = hybrid_search(message, paper_id=paper.id, top_k=5)

        # ── Build context from chunks ──
        RELEVANCE_THRESHOLD = 0.30
        good_chunks = [r for r in raw_results if r.get("vector_score", 0.0) >= RELEVANCE_THRESHOLD]

        if good_chunks:
            context_parts = []
            citations_data = []
            for i, r in enumerate(good_chunks):
                meta = r["metadata"]
                page_str = f" [第{meta['page_number']}页]" if meta.get("page_number") is not None else ""
                context_parts.append(
                    f"[{i+1}] (来源: 第{meta['chunk_index']}段{page_str})\n{r['text']}"
                )
                citations_data.append(Citation(
                    page_number=meta.get("page_number"),
                    chunk_index=meta.get("chunk_index"),
                    text=r["text"][:200],
                ))

            context_text = "\n\n".join(context_parts)

            system_prompt = (
                f"你是一个学术论文助手。请根据提供的论文原文片段回答用户问题。\n\n"
                f"论文标题: {paper.title}\n"
                f"{'作者: ' + paper.authors if paper.authors else ''}\n\n"
                f"以下是论文中与问题相关的原文片段：\n\n{context_text}\n\n"
                f"要求：\n"
                f"1. 基于以上原文片段回答问题，不要编造内容\n"
                f"2. 每引用一个观点必须在末尾标注来源编号，如 [1]、[2]\n"
                f"3. 如果原文片段不足以回答问题，请如实说明"
            )
            has_answer = True
            suggestions = []
        else:
            context_text = ""
            citations_data = []

            suggestions = [
                "仅基于当前论文回答",
                "在当前 Project 中继续检索",
                "查找相关最新论文",
            ]

            system_prompt = (
                f"你是一个学术论文助手。用户正在阅读论文：{paper.title}\n"
                f"用户的问题是：{message}\n\n"
                f"注意：在论文中未找到与问题直接相关的内容。请如实告知用户，"
                f"并根据论文标题、摘要等基本信息给出有限程度的背景说明，"
                f"不要编造论文中不存在的信息。"
            )
            has_answer = False

    return {
        "system_prompt": system_prompt,
        "citations": citations_data,
        "has_answer": has_answer,
        "suggestions": suggestions,
    }


def _build_messages(paper_id: int, db: Session, system_prompt: str) -> list[dict]:
    """Build full message list: system prompt + last 6 messages of history."""
    messages = [{"role": "system", "content": system_prompt}]
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.paper_id == paper_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(6)
        .all()
    )
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    return messages


@router.post("/papers/{paper_id}/chat", response_model=ChatResponse)
def chat_with_paper(
    paper_id: int,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chat with the paper using RAG — retrieves relevant chunks, cites sources."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.llm import LLMService
    if not LLMService.available():
        raise HTTPException(status_code=503, detail="LLM service not configured")

    # Save user message
    user_msg = ChatMessage(paper_id=paper_id, role="user", content=data.message)
    db.add(user_msg)
    db.commit()

    # Agent (auto) mode — LLM decides tools to call
    if data.mode == "auto":
        from app.services.agent import run_agent
        reply, citations = run_agent(paper, db, data.message)

        assistant_msg = ChatMessage(paper_id=paper_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()

        return ChatResponse(
            reply=reply,
            citations=citations,
            has_answer=bool(reply),
            suggestions=[],
        )

    prep = _prepare_chat(paper, db, data.mode, data.message)
    messages = _build_messages(paper_id, db, prep["system_prompt"])

    try:
        reply = LLMService.chat(messages, temperature=0.3, max_tokens=2048, feature="chat")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {str(e)}")

    # Save assistant reply
    assistant_msg = ChatMessage(paper_id=paper_id, role="assistant", content=reply)
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(
        reply=reply,
        citations=prep["citations"],
        has_answer=prep["has_answer"],
        suggestions=prep["suggestions"],
    )


def _agent_stream(paper: Paper, db: Session, message: str):
    """Streaming ReAct agent loop (SSE: status* → meta → delta* → done).

    The LLM decides which tools to call (search_paper / search_project /
    search_web / get_paper_meta / list_project_papers), the loop executes them
    and feeds results back, then the final answer streams as delta events.
    """
    from app.core.database import SessionLocal
    from app.services.llm import LLMService
    from app.services.agent import (
        AgentExecutor,
        AGENT_TOOLS,
        AGENT_SYSTEM_PROMPT,
        TOOL_LABELS,
    )

    def _chunk(text: str, size: int = 3):
        for i in range(0, len(text), size):
            yield text[i : i + size]

    try:
        executor = AgentExecutor(paper, db)
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT + f"\n\n当前论文标题：{paper.title}"},
            {"role": "user", "content": message},
        ]

        yield _sse("status", {"text": "🤔 正在分析问题..."})

        final_text = ""
        max_steps = 4
        for _step in range(max_steps):
            content_parts: list[str] = []
            tool_calls_acc: dict[int, dict] = {}

            for ev in LLMService.chat_stream(messages, tools=AGENT_TOOLS, temperature=0.3, max_tokens=2048, feature="agent"):
                c = ev.get("content")
                if c:
                    content_parts.append(c)
                tcs = ev.get("tool_calls")
                if tcs:
                    for tc in tcs:
                        idx = tc.get("index", 0)
                        acc = tool_calls_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            acc["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            acc["name"] = fn["name"]
                        if fn.get("arguments"):
                            acc["arguments"] += fn["arguments"]

            # DeepSeek emits finish_reason both "tool_calls" and a trailing "stop";
            # presence of tool_calls is the reliable signal for a tool round.
            if tool_calls_acc:
                calls = []
                for idx in sorted(tool_calls_acc):
                    tc = tool_calls_acc[idx]
                    calls.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    })

                messages.append({
                    "role": "assistant",
                    "content": "".join(content_parts) or None,
                    "tool_calls": calls,
                })

                for call in calls:
                    name = call["function"]["name"]
                    label = TOOL_LABELS.get(name, name)
                    yield _sse("status", {"text": f"{label}..."})
                    try:
                        result_str = executor.execute(name, call["function"]["arguments"])
                    except Exception as e:
                        result_str = str(e)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": result_str,
                    })
                continue

            # No tool calls → this is the final answer
            final_text = "".join(content_parts).strip()
            break

        if not final_text:
            final_text = "我未能生成有效回答，请尝试换个问法或更具体的提问。"

        yield _sse("meta", {
            "citations": [
                {
                    "page_number": c.page_number,
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                }
                for c in executor.citations
            ],
            "has_answer": True,
            "suggestions": [],
        })

        # Stream the final answer in small chunks
        for piece in _chunk(final_text):
            yield _sse("delta", {"text": piece})

        # Persist assistant message
        sdb = SessionLocal()
        msg_id = None
        try:
            assistant_msg = ChatMessage(paper_id=paper.id, role="assistant", content=final_text)
            sdb.add(assistant_msg)
            sdb.commit()
            msg_id = assistant_msg.id
        finally:
            sdb.close()

        yield _sse("done", {"message_id": msg_id, "reply": final_text})

    except Exception as e:
        yield _sse("error", {"detail": f"Agent 执行失败: {str(e)}"})


@router.post("/papers/{paper_id}/chat/stream")
def chat_with_paper_stream(
    paper_id: int,
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streaming variant of the chat endpoint (SSE).

    Modes: paper_only | project_search | web_search | auto (agent).
    Auto mode runs the Function-Calling ReAct loop.
    """
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    from app.services.llm import LLMService
    if not LLMService.available():
        raise HTTPException(status_code=503, detail="LLM service not configured")

    # Save user message before streaming
    user_msg = ChatMessage(paper_id=paper_id, role="user", content=data.message)
    db.add(user_msg)
    db.commit()

    # Agent (auto) mode — LLM decides tools to call
    if data.mode == "auto":
        return StreamingResponse(
            _agent_stream(paper, db, data.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Retrieval + prompt construction happens before the stream starts
    prep = _prepare_chat(paper, db, data.mode, data.message)
    messages = _build_messages(paper_id, db, prep["system_prompt"])

    def generate():
        from app.core.database import SessionLocal

        try:
            # 1. meta: citations & flags for the frontend
            yield _sse("meta", {
                "citations": [
                    {
                        "page_number": c.page_number,
                        "chunk_index": c.chunk_index,
                        "text": c.text,
                    }
                    for c in prep["citations"]
                ],
                "has_answer": prep["has_answer"],
                "suggestions": prep["suggestions"],
            })

            # 2. stream LLM tokens
            reply_parts: list[str] = []
            for ev in LLMService.chat_stream(messages, temperature=0.3, max_tokens=2048, feature="chat"):
                if ev["content"]:
                    reply_parts.append(ev["content"])
                    yield _sse("delta", {"text": ev["content"]})

            full_reply = "".join(reply_parts)

            # 3. persist assistant message
            sdb = SessionLocal()
            msg_id = None
            try:
                assistant_msg = ChatMessage(paper_id=paper_id, role="assistant", content=full_reply)
                sdb.add(assistant_msg)
                sdb.commit()
                msg_id = assistant_msg.id
            finally:
                sdb.close()

            # 4. done
            yield _sse("done", {"message_id": msg_id, "reply": full_reply})

        except Exception as e:
            yield _sse("error", {"detail": f"LLM request failed: {str(e)}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/papers/{paper_id}/chat", response_model=list[ChatMessageResponse])
def get_chat_history(
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get chat message history for a paper."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    return (
        db.query(ChatMessage)
        .filter(ChatMessage.paper_id == paper_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )


# ── Metadata Update ───────────────────────────────────────────────


@router.patch("/papers/{paper_id}", response_model=PaperResponse)
def update_paper_metadata(
    paper_id: int,
    data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update paper metadata fields."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    allowed_fields = {"title", "authors", "keywords", "abstract", "doi", "year"}
    for key, value in data.items():
        if key in allowed_fields:
            setattr(paper, key, value)

    db.commit()
    db.refresh(paper)
    return paper
