import enum
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaperStatus(str, enum.Enum):
    UPLOADING = "UPLOADING"   # 文件上传中 / arXiv 下载中
    PENDING = "PENDING"       # 排队待处理
    PARSING = "PARSING"       # PDF 解析中
    CHUNKING = "CHUNKING"     # 文本分块中
    EMBEDDING = "EMBEDDING"   # 向量化中
    INDEXING = "INDEXING"     # 写入向量库
    COMPLETED = "COMPLETED"   # 完成
    FAILED = "FAILED"         # 失败


class PaperSource(str, enum.Enum):
    UPLOAD = "upload"
    ARXIV = "arxiv"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # File info
    file_name: Mapped[str] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=True)

    # Source
    source_type: Mapped[PaperSource] = mapped_column(
        SAEnum(PaperSource, name="paper_source"),
        nullable=False,
        default=PaperSource.UPLOAD,
    )
    arxiv_id: Mapped[str] = mapped_column(String(50), nullable=True)

    # Parsed text (output of PR 2)
    parsed_text_path: Mapped[str] = mapped_column(String(500), nullable=True)

    # Chunk count (output of PR 3)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=True)

    # Processing state
    status: Mapped[PaperStatus] = mapped_column(
        SAEnum(PaperStatus, name="paper_status"),
        nullable=False,
        default=PaperStatus.UPLOADING,
    )
    processing_progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # Metadata
    authors: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array
    keywords: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array
    abstract: Mapped[str] = mapped_column(Text, nullable=True)
    doi: Mapped[str] = mapped_column(String(500), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
