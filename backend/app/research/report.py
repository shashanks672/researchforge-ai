import html
import re

from app.research.errors import ResearchFailure
from app.research.schemas import DraftReport, EvidenceSource, GroundedStatement, ResearchPlan
from app.research.sufficiency import EvidenceSufficiencyResult


def escape(value: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", html.escape(" ".join(value.split())))


def validate_citations(report: DraftReport, sources: list[EvidenceSource]) -> None:
    known = {source.source_id for source in sources}
    statements = [
        *report.executive_summary,
        *report.findings,
        *report.comparisons,
        report.conclusion,
    ]
    if any(not set(statement.source_ids).issubset(known) for statement in statements):
        raise ResearchFailure("invalid_output")


def render_report(
    report: DraftReport,
    plan: ResearchPlan,
    sources: list[EvidenceSource],
    warnings: list[str],
    mock: bool,
    sufficiency: list[EvidenceSufficiencyResult] | None = None,
) -> str:
    validate_citations(report, sources)

    def statement(item: GroundedStatement) -> str:
        return (
            escape(item.text) + " " + " ".join(f"[{sid}]" for sid in dict.fromkeys(item.source_ids))
        )

    parts = [f"# {escape(report.title)}"]
    if mock:
        parts += [
            "> MOCK DEMONSTRATION — mock writer; web fixtures are synthetic, "
            "document passages are actual uploads. No factual verification."
        ]
    if sufficiency and all(item.status == "INSUFFICIENT" for item in sufficiency) and sources:
        parts += [
            "## Retrieved passages (not assessed as answers)",
            *[f"- [{source.source_id}] {escape(source.excerpt)}" for source in sources],
        ]
    parts += [
        "## Executive summary",
        *[statement(s) for s in report.executive_summary],
        "## Research objective",
        escape(report.objective),
        "## Answerability and evidence sufficiency",
        "Evidence statuses describe coverage; they are not confidence scores.",
        *[
            f"- {item.question_id} — {item.status}: {escape(item.question_text)} "
            + (
                f"Evidence: {', '.join(item.supporting_evidence_ids)}. "
                if item.supporting_evidence_ids
                else ""
            )
            + (
                f"Missing: {escape('; '.join(item.missing_information))}. "
                if item.missing_information
                else ""
            )
            + escape(item.explanation)
            for item in (sufficiency or [])
        ],
        *(
            ["Insufficient evidence was found in the selected sources to answer reliably."]
            if sufficiency and all(item.status == "INSUFFICIENT" for item in sufficiency)
            else []
        ),
        "## Methodology",
        f"A bounded LangGraph workflow planned {len(plan.subquestions)} subquestions "
        f"and collected {len(sources)} sources. "
        "Citations link to collected passages; their presence does not prove a claim is true.",
        "## Main findings",
        *[statement(s) for s in report.findings],
        "## Comparative analysis",
        *(
            [statement(s) for s in report.comparisons]
            or ["The collected evidence does not justify a comparative conclusion."]
        ),
        "## Limitations",
        *[f"- {escape(item)}" for item in [*report.limitations, *warnings]],
        "- Publication dates are not asserted unless independently verified; "
        "retrieval times are not publication dates.",
        (
            "- Evidence support assessments are reported separately; they do not "
            "establish absolute truth."
        ),
        "## Conclusion",
        statement(report.conclusion),
        "## References",
    ]
    for source in sources:
        parts.append(f"[{source.source_id}]: {source.url}")
        source_label = {
            "document": "document passage",
            "mock": "synthetic fixture",
            "web": "web source",
        }[source.source_type]
        if source.source_type == "document":
            parts.append(
                f"Document {escape(source.title)}; page {source.page or 'not available'}; "
                f"chunk {source.chunk_id}; immutable evidence snapshot."
            )
        parts.append(
            f"- [{source.source_id}] {escape(source.title)} "
            f"— retrieved {source.retrieved_at.isoformat()} "
            f"({source_label})."
        )
    return "\n\n".join(parts) + "\n"
