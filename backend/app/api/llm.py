"""LLM usage stats endpoints — token/cost observability."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.llm_usage import LLMUsage
from app.models.user import User

router = APIRouter(prefix="/llm", tags=["llm"])


class FeatureStat(BaseModel):
    feature: str
    calls: int
    total_tokens: int


class LLMStatsResponse(BaseModel):
    today_calls: int
    today_tokens: int
    total_calls: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    by_feature: list[FeatureStat]


@router.get("/stats", response_model=LLMStatsResponse)
def get_llm_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate LLM token usage. Global (system-wide), auth-gated."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    def _scalar(q):
        return q.scalar() or 0

    today_calls = _scalar(
        db.query(func.count(LLMUsage.id)).filter(LLMUsage.created_at >= today_start)
    )
    today_tokens = _scalar(
        db.query(func.sum(LLMUsage.total_tokens)).filter(LLMUsage.created_at >= today_start)
    )
    total_calls = _scalar(db.query(func.count(LLMUsage.id)))
    total_tokens = _scalar(db.query(func.sum(LLMUsage.total_tokens)))
    prompt_tokens = _scalar(db.query(func.sum(LLMUsage.prompt_tokens)))
    completion_tokens = _scalar(db.query(func.sum(LLMUsage.completion_tokens)))

    rows = (
        db.query(LLMUsage.feature, func.count(LLMUsage.id), func.sum(LLMUsage.total_tokens))
        .group_by(LLMUsage.feature)
        .all()
    )
    by_feature = [
        FeatureStat(feature=feat, calls=calls, total_tokens=tokens or 0)
        for feat, calls, tokens in rows
    ]

    return LLMStatsResponse(
        today_calls=today_calls,
        today_tokens=today_tokens,
        total_calls=total_calls,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        by_feature=by_feature,
    )
