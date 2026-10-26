from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.research import ResearchMode


class SessionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionCreate(BaseModel):
    """Save research intent. Execution and document attachment are later phases."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=10, max_length=4000)
    mode: ResearchMode = ResearchMode.WEB
    document_ids: list[UUID] = Field(default_factory=list, max_length=30)


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_ids: list[UUID] = Field(default_factory=list)
    question: str
    mode: ResearchMode
    status: SessionStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
    error_message: str | None


class SessionPage(BaseModel):
    items: list[SessionRead]
    total: int
    limit: int
    offset: int
    has_more: bool
