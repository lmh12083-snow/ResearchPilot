from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.paper import Paper
from app.schemas.paper import PaperCreate, PaperResponse
from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/projects/{project_id}/papers", tags=["papers"])


@router.get("", response_model=list[PaperResponse])
def list_papers(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Paper).filter(Paper.project_id == project_id).all()


@router.get("/{paper_id}", response_model=PaperResponse)
def get_paper(
    project_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(
        Paper.id == paper_id, Paper.project_id == project_id
    ).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.post("", response_model=PaperResponse, status_code=status.HTTP_201_CREATED)
def create_paper(
    project_id: int,
    data: PaperCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = Paper(
        title=data.title,
        authors=data.authors,
        abstract=data.abstract,
        keywords=data.keywords,
        doi=data.doi,
        source=data.source,
        project_id=project_id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(
    project_id: int,
    paper_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    paper = db.query(Paper).filter(
        Paper.id == paper_id, Paper.project_id == project_id
    ).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    db.delete(paper)
    db.commit()
