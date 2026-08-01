from datetime import datetime, timezone

from sqlalchemy import Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Note(Base):
    """A reading annotation tied to a paper (optionally a selected excerpt)."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )

    anchor_text: Mapped[str] = mapped_column(Text, nullable=True)  # selected excerpt
    content: Mapped[str] = mapped_column(Text, nullable=True)      # user's own note
    tags: Mapped[str] = mapped_column(Text, nullable=True)         # JSON array
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)   # LLM key points

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
