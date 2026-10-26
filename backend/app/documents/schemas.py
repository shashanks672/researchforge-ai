from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    checksum: str
    status: str
    index_status: str
    page_count: int | None
    chunk_count: int
    embedding_model: str | None
    error_code: str | None
    uploaded_at: AwareDatetime


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=4000)
    document_ids: list[UUID] = Field(default_factory=list, max_length=30)
    k: int = Field(default=5, ge=1, le=10)
    method: str = Field(default="hybrid", pattern="^(hybrid|semantic|bm25)$")


class Passage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None
    heading: str | None
    text: str
    checksum: str
    score: float
    semantic_score: float | None = None
    keyword_score: float | None = None
