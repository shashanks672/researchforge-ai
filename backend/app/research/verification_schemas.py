from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from app.research.schemas import StrictModel
from app.research.sufficiency import EvidenceSufficiencyResult

Status = Literal["SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE", "NOT_EVALUATED"]
ClaimEligibility = Literal[
    "VERIFIABLE_CLAIM",
    "INCOMPLETE_FRAGMENT",
    "NON_FACTUAL_STATEMENT",
    "QUESTION_OR_INSTRUCTION",
    "INSUFFICIENT_CONTEXT",
]


class ExtractedClaim(StrictModel):
    text: str = Field(min_length=3, max_length=1200)
    location: str = Field(max_length=80)
    source_ids: list[str] = Field(max_length=5)
    checkable: bool
    important: bool


class Extraction(StrictModel):
    claims: list[ExtractedClaim] = Field(min_length=1, max_length=24)


class Claim(ExtractedClaim):
    claim_id: str
    eligibility: ClaimEligibility
    eligibility_reason: str = Field(max_length=400)
    reconstructed_claim: str | None = Field(default=None, max_length=1200)


class EvidenceMatch(StrictModel):
    source_id: str
    quote: str = Field(min_length=1, max_length=1500)
    role: Literal["support", "conflict", "context"]


class Judgment(StrictModel):
    claim_id: str
    status: Status
    matches: list[EvidenceMatch] = Field(max_length=8)
    explanation: str = Field(min_length=10, max_length=1000)


class PossibleConflict(StrictModel):
    first_source_id: str
    second_source_id: str
    first_statement: str = Field(max_length=1500)
    second_statement: str = Field(max_length=1500)
    reason: str = Field(min_length=10, max_length=800)
    context_caveat: str = Field(min_length=10, max_length=800)


class Assessment(StrictModel):
    verdicts: list[Judgment] = Field(min_length=1, max_length=24)
    contradictions: list[PossibleConflict] = Field(max_length=12)


class Verdict(Judgment):
    method: str
    evaluated_at: AwareDatetime


class Contradiction(PossibleConflict):
    first_observed_at: AwareDatetime
    second_observed_at: AwareDatetime
    first_published_at: AwareDatetime | None = None
    second_published_at: AwareDatetime | None = None


class VerificationSnapshot(StrictModel):
    id: UUID
    session_id: UUID
    status: Literal["running", "completed", "failed"]
    execution_mode: Literal["mock", "local", "live"]
    method: str
    iteration: int = Field(ge=0, le=2)
    claims: list[Claim]
    verdicts: list[Verdict]
    contradictions: list[Contradiction]
    candidates: dict[str, list[str]]
    activities: list[str]
    evidence_sufficiency: list[EvidenceSufficiencyResult] = Field(default_factory=list)
    error_code: str | None = None
    evaluated_at: AwareDatetime
