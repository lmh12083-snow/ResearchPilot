from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RecentPaper(BaseModel):
    id: int
    title: str
    project_id: int
    project_name: str
    status: str
    created_at: datetime


class RecentProject(BaseModel):
    id: int
    name: str
    paper_count: int
    created_at: datetime


class DashboardResponse(BaseModel):
    project_count: int
    paper_count: int
    recent_papers: list[RecentPaper]
    recent_projects: list[RecentProject]
