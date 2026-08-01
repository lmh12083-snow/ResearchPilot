from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RagEvalRun(Base):
    """One RAG evaluation run over a project's indexed papers."""

    __tablename__ = "rag_eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )  # running / completed / failed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    metrics: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class RagEvalQuestion(Base):
    """One generated test question with its retrieval + answer + judge result."""

    __tablename__ = "rag_eval_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("rag_eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id"), nullable=False
    )
    paper_title: Mapped[str] = mapped_column(String(500), nullable=False)  # denormalized for UI
    question: Mapped[str] = mapped_column(Text, nullable=False)
    gold_chunk_id: Mapped[str] = mapped_column(String(100), nullable=False)
    gold_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Retrieval
    retrieved_rank: Mapped[int] = mapped_column(Integer, nullable=True)  # 1-based; None if not retrieved
    hit: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Answer + judge
    answer: Mapped[str] = mapped_column(Text, nullable=True)
    answer_correct: Mapped[bool] = mapped_column(Boolean, nullable=True)
    faithful: Mapped[bool] = mapped_column(Boolean, nullable=True)
    judge_reasoning: Mapped[str] = mapped_column(Text, nullable=True)
