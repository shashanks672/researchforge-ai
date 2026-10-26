from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

LOCAL_WORKSPACE_ID = "local"


class Base(DeclarativeBase):
    pass


class ResearchSession(Base):
    __tablename__ = "research_sessions"
    __table_args__ = (
        CheckConstraint("char_length(question) BETWEEN 10 AND 4000", name="ck_session_question"),
        CheckConstraint("mode IN ('web', 'documents', 'combined')", name="ck_session_mode"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_session_status",
        ),
        Index("ix_session_workspace_history", "workspace_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint("execution_mode IN ('mock', 'local', 'live')", name="ck_run_mode"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), unique=True
    )
    worker_id: Mapped[str] = mapped_column(String(36))
    execution_mode: Mapped[str] = mapped_column(String(8))
    stage: Mapped[str] = mapped_column(String(40), server_default="accepted")
    plan: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    sources: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    investigated_queries: Mapped[list[str]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    report_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index(
            "ix_document_workspace_checksum",
            "workspace_id",
            "checksum",
            unique=True,
            postgresql_where=text("status != 'deleted'"),
        ),
        CheckConstraint(
            "status IN ('queued','processing','ready','failed','deleting','deleted')",
            name="ck_document_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(50))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    index_status: Mapped[str] = mapped_column(String(30), default="not_indexed")
    page_count: Mapped[int | None]
    chunk_count: Mapped[int] = mapped_column(default=0)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    index_collection: Mapped[str | None] = mapped_column(String(150))
    generation: Mapped[UUID] = mapped_column(default=uuid4)
    error_code: Mapped[str | None] = mapped_column(String(40))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    generation: Mapped[UUID]
    ordinal: Mapped[int]
    page: Mapped[int | None]
    heading: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), unique=True
    )
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    artifacts: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    original_draft: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    original_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    drafts: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    history: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
