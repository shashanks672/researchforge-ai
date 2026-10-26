"""Evidence support assessments, not truth certification. Mock policy deliberately abstains."""

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.research.budget import RunBudget
from app.research.errors import ResearchFailure
from app.research.providers import LLMProvider, account_usage
from app.research.schemas import DraftReport, EvidenceSource
from app.research.verification_schemas import (
    Assessment,
    Claim,
    ClaimEligibility,
    Contradiction,
    EvidenceMatch,
    ExtractedClaim,
    Extraction,
    Judgment,
    PossibleConflict,
    Verdict,
    VerificationSnapshot,
)

_OPINION = re.compile(
    r"\b(best|worst|beautiful|wonderful|fascinating|boring|amazing|prefer|should)\b", re.I
)
_QUESTION = re.compile(
    r"^(?:who|what|when|where|why|how|which|can|could|do|does|did|is|are|was|were)\b", re.I
)
_INSTRUCTION = re.compile(
    r"^(?:please\s+)?(?:explain|describe|compare|summarize|show|tell|list|identify|analyze|analyse)\b",
    re.I,
)
_OPEN_PREFIX = re.compile(
    r"^(?:(?:in addition|additionally|moreover|however|therefore|although|because|"
    r"for example),?\s+)?",
    re.I,
)
_CONTEXT_START = re.compile(r"^(?:it|this|that|they|these|those|he|she|they)\b", re.I)
_TRAILING_OPEN = re.compile(
    r"\b(?:a|an|the|and|or|but|of|to|for|with|from|by|because|although|which|that|who|has|have|had|is|are|was|were|be|been|being|can|could|will|would|may|might|must|should|does|do|did)$",
    re.I,
)
_COMMON_FINITE_VERBS = {
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "can",
    "could",
    "will",
    "would",
    "may",
    "might",
    "must",
    "states",
    "shows",
    "means",
    "includes",
    "contains",
    "uses",
    "requires",
    "provides",
    "regulates",
    "defines",
    "covers",
    "protects",
    "allows",
    "prohibits",
    "took",
    "takes",
    "supports",
    "reports",
    "found",
    "finds",
    "demonstrates",
    "indicates",
    "suggests",
    "stores",
    "holds",
    "produces",
    "carries",
    "operates",
    "occurred",
    "happened",
    "increased",
    "decreased",
    "equals",
    "weighs",
    "measures",
    "costs",
    "begins",
    "ends",
    "applies",
    "differs",
    "conflicts",
    "contradicts",
    "published",
    "occur",
    "exist",
    "remain",
}


def claim_eligibility(text: str) -> tuple[ClaimEligibility, str]:
    """Conservative structural gate; this classifies checkability, not truth."""
    value = text.strip().strip('"“”')
    if not value:
        return "INCOMPLETE_FRAGMENT", "The extracted text is empty."
    parts = sentences(value)
    if len(parts) > 1:
        checks = [claim_eligibility(part) for part in parts]
        for category in (
            "INCOMPLETE_FRAGMENT",
            "QUESTION_OR_INSTRUCTION",
            "NON_FACTUAL_STATEMENT",
            "INSUFFICIENT_CONTEXT",
        ):
            reason = next((why for found, why in checks if found == category), None)
            if reason:
                return category, f"At least one sentence needs review: {reason}"[:400]
        return (
            "VERIFIABLE_CLAIM",
            "Each sentence is a complete declarative proposition; evidence still "
            "determines its verdict.",
        )
    if "?" in value or _QUESTION.match(value):
        return "QUESTION_OR_INSTRUCTION", "Questions do not assert a proposition to verify."
    if _INSTRUCTION.match(value):
        return "QUESTION_OR_INSTRUCTION", "Instructions are not factual propositions."
    if _OPINION.search(value):
        return (
            "NON_FACTUAL_STATEMENT",
            "Subjective or normative wording is not objectively checkable.",
        )

    body = _OPEN_PREFIX.sub("", value).strip()
    words = re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", body.casefold())
    if not words or _TRAILING_OPEN.search(" ".join(words)):
        return "INCOMPLETE_FRAGMENT", "The text ends before its proposition is complete."
    if _CONTEXT_START.match(body):
        return (
            "INSUFFICIENT_CONTEXT",
            "A leading pronoun needs an explicit antecedent to identify its subject.",
        )
    has_verb = any(
        word in _COMMON_FINITE_VERBS
        or word.endswith(("ed", "izes", "ises", "ates", "fies"))
        or (
            len(word) > 4
            and word.endswith("s")
            and word not in {"research", "news", "series", "species"}
        )
        for word in words[1:]
    )
    if not has_verb:
        return "INCOMPLETE_FRAGMENT", "No finite predicate was found in the extracted text."
    if re.match(r"^(?:and|but|or|although|because|which|that)\b", body, re.I):
        return "INCOMPLETE_FRAGMENT", "The text begins with a dependent clause or continuation."
    return (
        "VERIFIABLE_CLAIM",
        "A complete declarative proposition is present; evidence still determines its verdict.",
    )


def paragraphs(report: DraftReport) -> dict[str, tuple[str, list[str]]]:
    result = {
        f"{section}:{i}": (item.text, item.source_ids)
        for section in ("executive_summary", "findings", "comparisons")
        for i, item in enumerate(getattr(report, section))
    }
    result["conclusion:0"] = (report.conclusion.text, report.conclusion.source_ids)
    return result


def normalized(text: str) -> str:
    return " ".join(text.casefold().split()).strip(" .;:!?")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])|\n+", text) if s.strip()]


def mock_extract(report: DraftReport) -> Extraction:
    claims = []
    for location, (text, ids) in paragraphs(report).items():
        value = text.removeprefix("Document passage (mock extractive draft): ")
        for sentence in sentences(value):
            eligibility, _ = claim_eligibility(sentence)
            claims.append(
                ExtractedClaim(
                    text=sentence,
                    location=location,
                    source_ids=ids,
                    checkable=eligibility == "VERIFIABLE_CLAIM",
                    important=True,
                )
            )
    if len(claims) > 24:
        claims = [
            ExtractedClaim(
                text=text,
                location=loc,
                source_ids=ids,
                checkable=claim_eligibility(text)[0] == "VERIFIABLE_CLAIM",
                important=True,
            )
            for loc, (text, ids) in paragraphs(report).items()
        ]
    return Extraction(claims=claims)


def numeric_relation(text: str) -> tuple[str, str, str] | None:
    # Deliberately narrow controlled-fixture grammar: all nonnumeric context and units
    # must agree. Dates, extra context, paraphrases and compound numbers abstain.
    value = normalized(text)
    match = re.fullmatch(
        r"([a-z][a-z ]{2,120}?) (\d+(?:\.\d+)?) (kwh|kilowatts|litres|days|passengers)", value
    )
    return (match[1], match[2], match[3]) if match else None


def injection(text: str) -> bool:
    return bool(
        re.search(
            (
                "ignore (?:all |previous |prior )?instructions|disregard .*instructions|"
                "system (?:prompt|message)|reveal .{0,40}"
                "(?:secrets?|api keys?|credentials?|tokens?)|"
                "mark .{0,30}supported|override|(?:call|run|execute|invoke) .{0,30}tools?|"
                "(?:fake|fabricated) citations?|rewrite (?:the )?(?:final )?report"
            ),
            text,
            re.I,
        )
    )


def mock_assess(claims: list[Claim], sources: list[EvidenceSource]) -> Assessment:
    verdicts = []
    conflicts: list[PossibleConflict] = []
    for claim in claims:
        support, contrary = [], []
        target = numeric_relation(claim.text)
        for source in sources:
            if injection(source.excerpt):
                continue
            for sentence in sentences(source.excerpt):
                same = normalized(sentence) == normalized(claim.text)
                relation = numeric_relation(sentence)
                mismatch = bool(
                    target
                    and relation
                    and target[0] == relation[0]
                    and target[2] == relation[2]
                    and target[1] != relation[1]
                )
                negation = normalized(sentence).replace(" is not ", " is ") == normalized(
                    claim.text
                ) and " is not " in normalized(sentence)
                if same:
                    support.append(
                        EvidenceMatch(source_id=source.source_id, quote=sentence, role="support")
                    )
                elif mismatch or negation:
                    contrary.append(
                        EvidenceMatch(source_id=source.source_id, quote=sentence, role="conflict")
                    )
        if not claim.checkable:
            status = "NOT_EVALUATED"
        elif (
            not claim.source_ids
            or not set(claim.source_ids).issubset({s.source_id for s in sources})
            or support
            and contrary
        ):
            status = "INSUFFICIENT_EVIDENCE"
        elif contrary:
            status = "CONTRADICTED"
        elif support:
            status = "SUPPORTED"
        else:
            status = "INSUFFICIENT_EVIDENCE"
        verdicts.append(
            Judgment(
                claim_id=claim.claim_id,
                status=status,
                matches=(support + contrary)[:8],
                explanation=(
                    "MOCK exact-sentence/controlled-relation procedure. Conflicting, "
                    "uncited, ambiguous or unmatched claims abstain; no semantic or "
                    "real-world truth guarantee."
                ),
            )
        )
    # Search every source pair, including evidence not cited in the draft.
    for i, first in enumerate(sources):
        for second in sources[i + 1 :]:
            if injection(first.excerpt) or injection(second.excerpt):
                continue
            for a in sentences(first.excerpt):
                for b in sentences(second.excerpt):
                    ar, br = numeric_relation(a), numeric_relation(b)
                    if (
                        ar
                        and br
                        and ar[0] == br[0]
                        and ar[2] == br[2]
                        and ar[1] != br[1]
                        and len(conflicts) < 12
                    ):
                        conflicts.append(
                            PossibleConflict(
                                first_source_id=first.source_id,
                                second_source_id=second.source_id,
                                first_statement=a,
                                second_statement=b,
                                reason=(
                                    "Different values for the same controlled relation and unit."
                                ),
                                context_caveat=(
                                    "Possible conflict only; contexts or time periods may differ. "
                                    "Recency does not determine reliability."
                                ),
                            )
                        )
    return Assessment(verdicts=verdicts, contradictions=conflicts)


def candidates(claim: Claim, sources: list[EvidenceSource]) -> list[str]:
    words = set(re.findall(r"\w+", claim.text.casefold()))
    # Lexical ranking selects candidates only. It never assigns support.
    scored = sorted(
        sources,
        key=lambda s: (
            -len(words.intersection(re.findall(r"\w+", s.excerpt.casefold()))),
            s.source_id,
        ),
    )
    return [s.source_id for s in scored[:8]]


async def verify(
    report: DraftReport,
    sources: list[EvidenceSource],
    session_id: UUID,
    llm: LLMProvider,
    budget: RunBudget,
    iteration: int,
    previous: VerificationSnapshot | None = None,
) -> VerificationSnapshot:
    if any(s.session_id != session_id for s in sources) or len(
        {s.source_id for s in sources}
    ) != len(sources):
        raise ResearchFailure("verification_failed")
    extraction = Extraction.model_validate(
        account_usage(budget, await budget.invoke(lambda: llm.extract_claims(report), "llm"))
    )
    locations = paragraphs(report)
    if {c.location for c in extraction.claims} != set(locations):
        raise ResearchFailure("verification_failed")
    claims = []
    for i, item in enumerate(extraction.claims, 1):
        text, ids = locations[item.location]
        if normalized(item.text) not in normalized(text) or set(item.source_ids) != set(ids):
            raise ResearchFailure("verification_failed")
        eligibility, reason = claim_eligibility(item.text)
        eligible_item = item.model_copy(
            update={"checkable": item.checkable and eligibility == "VERIFIABLE_CLAIM"}
        )
        claims.append(
            Claim(
                **eligible_item.model_dump(),
                claim_id=f"C{i}",
                eligibility=eligibility,
                eligibility_reason=reason,
            )
        )
    matched = {c.claim_id: candidates(c, sources) for c in claims}
    result = Assessment.model_validate(
        account_usage(
            budget, await budget.invoke(lambda: llm.assess_claims(claims, sources), "llm")
        )
    )
    if sorted(v.claim_id for v in result.verdicts) != sorted(c.claim_id for c in claims):
        raise ResearchFailure("verification_failed")
    known, claim_map = {s.source_id: s for s in sources}, {c.claim_id: c for c in claims}
    now = datetime.now(UTC)
    method = (
        "mock-literal-relations-v1"
        if budget.settings.execution_mode == "mock"
        else f"llm-evidence-support-v1:{budget.settings.llm_model}"
    )
    verdicts = []
    for judgment in result.verdicts:
        claim = claim_map[judgment.claim_id]
        for match in judgment.matches:
            if (
                match.source_id not in known
                or match.source_id not in matched[claim.claim_id]
                or match.quote not in known[match.source_id].excerpt
            ):
                raise ResearchFailure("verification_failed")
        status = judgment.status
        explanation = judgment.explanation
        cited_support = any(
            match.role == "support" and match.source_id in claim.source_ids
            for match in judgment.matches
        )
        if not claim.checkable:
            status = "NOT_EVALUATED"
        elif status == "SUPPORTED" and (
            not claim.source_ids
            or not set(claim.source_ids).issubset(known)
            or not cited_support
            or any(m.role == "conflict" for m in judgment.matches)
        ):
            status = "INSUFFICIENT_EVIDENCE"
            explanation = (
                explanation[:840] + " The report's cited passage did not provide validated support."
            )
        elif status == "CONTRADICTED" and not any(m.role == "conflict" for m in judgment.matches):
            status = "INSUFFICIENT_EVIDENCE"
            explanation = explanation[:840] + " No directly conflicting passage was validated."
        verdicts.append(
            Verdict(
                **{
                    **judgment.model_dump(),
                    "status": status,
                    "explanation": explanation,
                },
                method=method,
                evaluated_at=now,
            )
        )
    contradictions = []
    for conflict in result.contradictions:
        a, b = known.get(conflict.first_source_id), known.get(conflict.second_source_id)
        if (
            a is None
            or b is None
            or a.source_id == b.source_id
            or conflict.first_statement not in a.excerpt
            or conflict.second_statement not in b.excerpt
        ):
            raise ResearchFailure("verification_failed")
        contradictions.append(
            Contradiction(
                **conflict.model_dump(),
                first_observed_at=a.retrieved_at,
                second_observed_at=b.retrieved_at,
                first_published_at=a.published_at,
                second_published_at=b.published_at,
            )
        )
    return VerificationSnapshot(
        id=previous.id if previous else uuid4(),
        session_id=session_id,
        status="running",
        execution_mode=budget.settings.execution_mode,
        method=method,
        iteration=iteration,
        claims=claims,
        verdicts=verdicts,
        contradictions=contradictions,
        candidates=matched,
        activities=list(previous.activities) if previous else [],
        evaluated_at=now,
    )
