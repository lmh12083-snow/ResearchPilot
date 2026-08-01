from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EvalRunCreate(BaseModel):
    project_id: int
    sample_size: int = Field(default=5, ge=1, le=20)  # questions sampled per paper


class EvalMetrics(BaseModel):
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float
    answer_accuracy: float
    faithfulness: float


class EvalRunResponse(BaseModel):
    id: int
    project_id: int
    status: str
    progress: int
    question_count: int
    sample_size: int
    metrics: Optional[EvalMetrics] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvalQuestionResponse(BaseModel):
    id: int
    paper_id: int
    paper_title: str
    question: str
    gold_chunk_id: str
    gold_text: str
    retrieved_rank: Optional[int] = None
    hit: Optional[bool] = None
    answer: Optional[str] = None
    answer_correct: Optional[bool] = None
    faithful: Optional[bool] = None
    judge_reasoning: Optional[str] = None

    model_config = {"from_attributes": True}
