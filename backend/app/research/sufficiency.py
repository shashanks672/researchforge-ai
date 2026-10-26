"""Evidence sufficiency contracts and fail-closed validation."""

import unicodedata
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, Field

from app.research.schemas import EvidenceSource, StrictModel

SufficiencyStatus = Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "CONFLICTING"]
FactStatus = Literal["SUPPORTED", "MISSING", "CONFLICTING"]


class EvidenceQuote(StrictModel):
    source_id: str = Field(pattern=r"^S[1-8]$")
    quote: str = Field(min_length=1, max_length=1500)


class FactAssessment(StrictModel):
    fact: str = Field(min_length=3, max_length=300)
    entity: str = Field(max_length=120)
    property: str = Field(max_length=120)
    value: str = Field(max_length=120)
    unit: str = Field(max_length=80)
    time_period: str = Field(max_length=120)
    scope: str = Field(max_length=160)
    negation: str = Field(max_length=120)
    status: FactStatus
    evidence: list[EvidenceQuote] = Field(max_length=8)


def normalize_quote(value: str) -> str:
    """Normalize Unicode compatibility forms and whitespace; preserve case and wording."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


class EvidenceSufficiencyDecision(StrictModel):
    question_id: str = Field(pattern=r"^Q[1-5]$")
    status: SufficiencyStatus
    supporting_evidence_ids: list[str] = Field(max_length=8)
    missing_information: list[str] = Field(max_length=8)
    explanation: str = Field(min_length=10, max_length=1000)
    fact_assessments: list[FactAssessment] = Field(min_length=1, max_length=8)


def status_from_facts(facts: list[FactAssessment]) -> SufficiencyStatus:
    statuses = {fact.status for fact in facts}
    if "CONFLICTING" in statuses:
        return "CONFLICTING"
    if statuses == {"SUPPORTED"}:
        return "SUFFICIENT"
    if statuses == {"MISSING"}:
        return "INSUFFICIENT"
    if "SUPPORTED" in statuses and "MISSING" in statuses:
        return "PARTIAL"
    raise ValueError("fact assessments do not determine an overall decision")


def normalize_decision_aggregate(
    decision: EvidenceSufficiencyDecision,
) -> EvidenceSufficiencyDecision:
    """Derive redundant summary fields from the validated fact-level assessments."""
    status = status_from_facts(decision.fact_assessments)
    missing = [fact.fact for fact in decision.fact_assessments if fact.status == "MISSING"]
    evidence_ids = sorted(
        {quote.source_id for fact in decision.fact_assessments for quote in fact.evidence}
    )
    updates: dict[str, object] = {
        "status": status,
        "missing_information": missing,
        "supporting_evidence_ids": evidence_ids,
    }
    if decision.status != status:
        updates["explanation"] = (
            f"Overall status was derived as {status} from the fact-level assessments because "
            "the model's summary status disagreed with those assessments."
        )
    elif decision.missing_information != missing:
        updates["explanation"] = (
            "Missing information was derived from fact assessments marked MISSING. "
            "The fact-level evidence decisions are retained."
        )
    return decision.model_copy(update=updates)


class EvidenceSufficiencyResult(EvidenceSufficiencyDecision):
    question_text: str = Field(min_length=5, max_length=800)
    sufficient: bool
    evaluator_version: str = "evidence-sufficiency-v1"
    evaluated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    def validate_consistency(self, known: set[str] | list[EvidenceSource]) -> None:
        if isinstance(known, list):
            source_map = {source.source_id: source for source in known}
            known_ids = set(source_map)
        else:
            source_map = {}
            known_ids = known
        if self.sufficient != (self.status == "SUFFICIENT"):
            raise ValueError("sufficient must be true only for SUFFICIENT status")
        if not set(self.supporting_evidence_ids).issubset(known_ids):
            raise ValueError("sufficiency result refers to unknown evidence")
        if (
            self.status in {"SUFFICIENT", "PARTIAL", "CONFLICTING"}
            and not self.supporting_evidence_ids
        ):
            raise ValueError("non-insufficient result requires evidence IDs")
        if self.status == "INSUFFICIENT" and not self.missing_information:
            raise ValueError("insufficient result must identify missing information")
        assessed_ids: set[str] = set()
        fact_signatures: set[tuple[str, ...]] = set()
        for fact in self.fact_assessments:
            signature = tuple(
                normalize_quote(getattr(fact, field)).casefold()
                for field in (
                    "fact",
                    "entity",
                    "property",
                    "value",
                    "unit",
                    "time_period",
                    "scope",
                    "negation",
                )
            )
            if signature in fact_signatures:
                raise ValueError("fact assessments must not duplicate a requested fact")
            fact_signatures.add(signature)
            if fact.status == "MISSING" and fact.evidence:
                raise ValueError("missing facts cannot have supporting quotes")
            if fact.status in {"SUPPORTED", "CONFLICTING"} and not fact.evidence:
                raise ValueError("supported facts require evidence quotes")
            if (
                fact.status == "CONFLICTING"
                and len({match.source_id for match in fact.evidence}) < 2
            ):
                raise ValueError("conflicting facts require quotes from separate sources")
            for match in fact.evidence:
                source = source_map.get(match.source_id)
                if source is not None and normalize_quote(match.quote) not in normalize_quote(
                    source.excerpt
                ):
                    raise ValueError("supporting quote is not present in the cited source")
                assessed_ids.add(match.source_id)
        if assessed_ids != set(self.supporting_evidence_ids):
            raise ValueError("supporting evidence IDs must match the fact-level quotes")
        expected_status = status_from_facts(self.fact_assessments)
        if self.status != expected_status:
            raise ValueError("decision status does not match fact-level evidence statuses")


def insufficient_result(
    question_id: str, question: str, known: list[EvidenceSource]
) -> EvidenceSufficiencyResult:
    """Deterministic mock policy: fixtures cannot establish answerability."""
    return evaluated_result(insufficient_decision(question_id, known), question)


def insufficient_decision(
    question_id: str, known: list[EvidenceSource]
) -> EvidenceSufficiencyDecision:
    return EvidenceSufficiencyDecision(
        question_id=question_id,
        status="INSUFFICIENT",
        supporting_evidence_ids=[],
        missing_information=[
            "Evidence that directly answers this question has not been evaluated."
        ],
        explanation=(
            f"The mock evaluator does not treat {len(known)} retrieved passage(s) as proof "
            "that the requested information is supported."
        ),
        fact_assessments=[
            FactAssessment(
                fact="Requested information was not evaluated by the mock provider.",
                entity="",
                property="",
                value="",
                unit="",
                time_period="",
                scope="",
                negation="",
                status="MISSING",
                evidence=[],
            )
        ],
    )


def evaluated_result(
    decision: EvidenceSufficiencyDecision, question: str
) -> EvidenceSufficiencyResult:
    return EvidenceSufficiencyResult(
        **decision.model_dump(),
        question_text=question,
        sufficient=decision.status == "SUFFICIENT",
    )
