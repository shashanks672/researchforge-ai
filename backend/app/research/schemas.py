from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class Subquestion(StrictModel):
    question: str = Field(min_length=10, max_length=300)
    search_query: str = Field(min_length=3, max_length=200)


class ResearchPlan(StrictModel):
    objective: str = Field(min_length=10, max_length=800)
    scope: str = Field(min_length=10, max_length=800)
    subquestions: list[Subquestion] = Field(min_length=1, max_length=5)


class EvidenceSource(StrictModel):
    source_id: str = Field(pattern=r"^S[1-8]$")
    session_id: UUID
    source_type: Literal["web", "mock", "document"]
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    page: int | None = None
    heading: str | None = None
    retrieval_score: float | None = None
    text_truncated: bool = False
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(max_length=2048)
    retrieved_at: AwareDatetime
    published_at: AwareDatetime | None = None
    excerpt: str = Field(min_length=1, max_length=1500)
    content_sha256: str
    search_query: str


class GroundedStatement(StrictModel):
    text: str = Field(min_length=10, max_length=1200)
    source_ids: list[str] = Field(max_length=5)


class DraftReport(StrictModel):
    title: str = Field(min_length=5, max_length=200)
    executive_summary: list[GroundedStatement] = Field(min_length=1, max_length=3)
    objective: str = Field(min_length=10, max_length=800)
    findings: list[GroundedStatement] = Field(min_length=1, max_length=8)
    comparisons: list[GroundedStatement] = Field(max_length=5)
    limitations: list[str] = Field(min_length=1, max_length=8)
    conclusion: GroundedStatement


class Usage(StrictModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usage_complete: bool = True
    tool_calls: int = 0
    search_calls: int = 0
    fetch_calls: int = 0
    external_request_attempts: int = 0
    external_search_attempts: int = 0
    article_fetch_attempts: int = 0
    estimated_cost_usd: float | None = None
    estimated_search_cost_usd: float = 0
    estimated_llm_cost_usd: float = 0
    reserved_llm_cost_usd: float = 0
    reserved_tokens: int = 0
    elapsed_ms: int = 0
    model_inference_ms: int = 0
    model_load_ms: int = 0
    model_tokens_per_second: float | None = None


class ExecuteRequest(StrictModel):
    execution_mode: Literal["mock", "local", "live"]


class RunRead(StrictModel):
    id: UUID
    session_id: UUID
    execution_mode: Literal["mock", "local", "live"]
    stage: str
    plan: ResearchPlan | None
    sources: list[EvidenceSource]
    investigated_queries: list[str]
    warnings: list[str]
    report_markdown: str | None
    metrics: Usage
    error_code: str | None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
