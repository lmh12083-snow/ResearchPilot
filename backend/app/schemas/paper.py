from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.paper import PaperStatus, PaperSource


class PaperCreate(BaseModel):
    title: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    source_type: PaperSource = PaperSource.UPLOAD
    arxiv_id: Optional[str] = None


class ArxivImportRequest(BaseModel):
    project_id: int
    arxiv_id: str


class PaperStatusResponse(BaseModel):
    id: int
    project_id: int
    title: str
    status: PaperStatus
    processing_progress: int
    source_type: PaperSource
    arxiv_id: Optional[str] = None
    page_count: Optional[int] = None
    file_size: Optional[int] = None
    error_message: Optional[str] = None
    parsed_text_path: Optional[str] = None
    chunk_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaperResponse(BaseModel):
    id: int
    project_id: int
    title: str
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    source_type: PaperSource
    arxiv_id: Optional[str] = None
    authors: Optional[str] = None
    keywords: Optional[str] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    year: Optional[int] = None
    status: PaperStatus
    processing_progress: int = 0
    error_message: Optional[str] = None
    parsed_text_path: Optional[str] = None
    chunk_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Search ─────────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str
    project_id: Optional[int] = None
    paper_id: Optional[int] = None
    top_k: int = 10

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be empty")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def clamp_top_k(cls, v: int) -> int:
        return max(1, min(v, 50))


class SearchResultItem(BaseModel):
    chunk_id: str
    text: str
    paper_id: int
    paper_title: str
    page_number: Optional[int] = None
    chunk_index: int
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResultItem]


# ── Paper Content ──────────────────────────────────────────────


class PaperContentResponse(BaseModel):
    id: int
    project_id: int
    title: str
    text: str
    page_count: Optional[int] = None
    chunk_count: Optional[int] = None
    status: PaperStatus


# ── Analysis ──────────────────────────────────────────────


class AnalysisResponse(BaseModel):
    abstract: Optional[str] = None
    innovation: Optional[str] = None
    methods: Optional[str] = None
    experiments: Optional[str] = None
    limitations: Optional[str] = None
    related_work: Optional[str] = None
    one_sentence: Optional[str] = None
    pros_cons: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────


class Citation(BaseModel):
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    text: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatRequest(BaseModel):
    message: str
    mode: str = "paper_only"  # paper_only | project_search | web_search | auto


class ChatResponse(BaseModel):
    reply: str
    citations: list[Citation] = []
    has_answer: bool = True
    suggestions: list[str] = []


# ── Compare ──────────────────────────────────────────────────


class CompareRequest(BaseModel):
    paper_ids: list[int]


class CompareResponse(BaseModel):
    overview: Optional[str] = None
    similarities: Optional[str] = None
    method_differences: Optional[str] = None
    experiment_differences: Optional[str] = None
    conclusion_differences: Optional[str] = None
    strengths_weaknesses: Optional[str] = None
    final_verdict: Optional[str] = None
