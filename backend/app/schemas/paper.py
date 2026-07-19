from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PaperCreate(BaseModel):
    title: str
    authors: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    doi: Optional[str] = None
    source: Optional[str] = None


class PaperResponse(BaseModel):
    id: int
    title: str
    authors: Optional[str]
    abstract: Optional[str]
    keywords: Optional[str]
    doi: Optional[str]
    source: Optional[str]
    project_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
