from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.project import Project
from app.models.paper import Paper
from app.api.auth import get_current_user
from app.models.user import User
from app.schemas.dashboard import DashboardResponse, RecentPaper, RecentProject

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Counts
    project_count = (
        db.query(func.count(Project.id))
        .filter(Project.user_id == current_user.id)
        .scalar()
    )
    paper_count = (
        db.query(func.count(Paper.id))
        .join(Project, Paper.project_id == Project.id)
        .filter(Project.user_id == current_user.id)
        .scalar()
    )

    # Recent papers (last 5)
    recent_paper_rows = (
        db.query(Paper, Project.name)
        .join(Project, Paper.project_id == Project.id)
        .filter(Project.user_id == current_user.id)
        .order_by(Paper.created_at.desc())
        .limit(5)
        .all()
    )
    recent_papers = [
        RecentPaper(
            id=p.id,
            title=p.title,
            project_id=p.project_id,
            project_name=project_name,
            status=p.status.value,
            created_at=p.created_at,
        )
        for p, project_name in recent_paper_rows
    ]

    # Recent projects (last 5)
    project_rows = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
        .limit(5)
        .all()
    )
    project_ids = [p.id for p in project_rows]
    paper_counts = dict(
        db.query(Paper.project_id, func.count(Paper.id))
        .filter(Paper.project_id.in_(project_ids))
        .group_by(Paper.project_id)
        .all()
    ) if project_ids else {}

    recent_projects = [
        RecentProject(
            id=p.id,
            name=p.name,
            paper_count=paper_counts.get(p.id, 0),
            created_at=p.created_at,
        )
        for p in project_rows
    ]

    return DashboardResponse(
        project_count=project_count or 0,
        paper_count=paper_count or 0,
        recent_papers=recent_papers,
        recent_projects=recent_projects,
    )
