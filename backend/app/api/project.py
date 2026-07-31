from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.project import Project
from app.models.paper import Paper
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/projects", tags=["projects"])


def _attach_paper_count(projects: list[Project], db: Session) -> list[dict]:
    """Attach paper_count to each project."""
    ids = [p.id for p in projects]
    counts: dict[int, int] = dict(
        db.query(Paper.project_id, func.count(Paper.id))
        .filter(Paper.project_id.in_(ids))
        .group_by(Paper.project_id)
        .all()
    )
    result = []
    for p in projects:
        d = p.__dict__.copy()
        d["paper_count"] = counts.get(p.id, 0)
        result.append(d)
    return result


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(Project).filter(Project.user_id == current_user.id).all()
    return _attach_paper_count(rows, db)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = project.__dict__.copy()
    result["paper_count"] = db.query(func.count(Paper.id)).filter(
        Paper.project_id == project.id
    ).scalar()
    return result


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        name=data.name,
        description=data.description,
        user_id=current_user.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {**project.__dict__, "paper_count": 0}


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description

    db.commit()
    db.refresh(project)
    result = project.__dict__.copy()
    result["paper_count"] = db.query(func.count(Paper.id)).filter(
        Paper.project_id == project.id
    ).scalar()
    return result


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(
        Project.id == project_id, Project.user_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
