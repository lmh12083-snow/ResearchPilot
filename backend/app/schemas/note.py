from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NoteCreate(BaseModel):
    paper_id: int
    anchor_text: Optional[str] = None
    content: Optional[str] = None
    tags: list[str] = []
    summarize: bool = False  # AI-summarize the anchor text on create


class NoteUpdate(BaseModel):
    anchor_text: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = None


class NoteResponse(BaseModel):
    id: int
    paper_id: int
    project_id: int
    anchor_text: Optional[str] = None
    content: Optional[str] = None
    tags: list[str] = []
    ai_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
