import json
import threading

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.rag_eval import RagEvalRun, RagEvalQuestion
from app.api.auth import get_current_user
from app.schemas.eval import (
    EvalRunCreate,
    EvalRunResponse,
    EvalQuestionResponse,
    EvalMetrics,
)

router = APIRouter(prefix="/eval", tags=["eval"])


def _parse_metrics(run: RagEvalRun) -> EvalMetrics | None:
    if not run.metrics:
        return None
    try:
        return EvalMetrics.model_validate(json.loads(run.metrics))
    except Exception:
        return None


def _run_response(run: RagEvalRun) -> EvalRunResponse:
    # Build explicitly: `metrics` is a JSON string on the ORM model and must be
    # parsed into a structured EvalMetrics before validation.
    return EvalRunResponse(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        progress=run.progress,
        question_count=run.question_count,
        sample_size=run.sample_size,
        metrics=_parse_metrics(run),
        error_message=run.error_message,
        duration_seconds=run.duration_seconds,
        created_at=run.created_at,
    )


@router.post("/runs", response_model=EvalRunResponse, status_code=status.HTTP_201_CREATED)
def create_eval_run(
    data: EvalRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create an eval run; the pipeline executes in a background thread."""
    project = (
        db.query(Project)
        .filter(Project.id == data.project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run = RagEvalRun(
        user_id=current_user.id,
        project_id=data.project_id,
        status="running",
        sample_size=data.sample_size,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    from app.services.rag_eval import run_eval_job

    threading.Thread(target=run_eval_job, args=(run.id,), daemon=True).start()
    return _run_response(run)


@router.get("/runs", response_model=list[EvalRunResponse])
def list_eval_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = (
        db.query(RagEvalRun)
        .filter(RagEvalRun.user_id == current_user.id)
        .order_by(RagEvalRun.created_at.desc())
        .all()
    )
    return [_run_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
def get_eval_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _get_owned_run(db, current_user, run_id)
    return _run_response(run)


@router.get("/runs/{run_id}/questions", response_model=list[EvalQuestionResponse])
def list_eval_questions(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_run(db, current_user, run_id)
    return (
        db.query(RagEvalQuestion)
        .filter(RagEvalQuestion.run_id == run_id)
        .order_by(RagEvalQuestion.id.asc())
        .all()
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_200_OK)
def delete_eval_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _get_owned_run(db, current_user, run_id)
    db.query(RagEvalQuestion).filter(RagEvalQuestion.run_id == run.id).delete(
        synchronize_session=False
    )
    db.delete(run)
    db.commit()
    return {"message": "Evaluation run deleted"}


def _get_owned_run(db: Session, current_user: User, run_id: int) -> RagEvalRun:
    run = (
        db.query(RagEvalRun)
        .filter(RagEvalRun.id == run_id, RagEvalRun.user_id == current_user.id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run
