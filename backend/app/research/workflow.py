from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict, cast
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError

from app.core.config import Settings
from app.documents.service import Documents
from app.research.budget import RunBudget
from app.research.errors import InvalidProviderOutput, ResearchFailure
from app.research.providers import (
    FetchedPage,
    LLMProvider,
    LLMResult,
    SearchHit,
    SearchProvider,
    account_usage,
)
from app.research.report import escape, render_report
from app.research.schemas import (
    DraftReport,
    EvidenceSource,
    GroundedStatement,
    ResearchPlan,
    Subquestion,
)
from app.research.sufficiency import (
    EvidenceSufficiencyDecision,
    EvidenceSufficiencyResult,
    evaluated_result,
    insufficient_result,
)
from app.research.verification import verify
from app.research.verification_schemas import VerificationSnapshot
from app.research.web import content_hash, normalize_url, relevant_excerpt


class ResearchState(TypedDict):
    question: str
    plan: ResearchPlan | None
    sources: list[EvidenceSource]
    investigated_queries: list[str]
    warnings: list[str]
    report: DraftReport | None
    markdown: str | None
    original_report: DraftReport | None
    original_markdown: str | None
    verification: VerificationSnapshot | None
    verification_history: list[VerificationSnapshot]
    draft_history: list[DraftReport]
    iteration: int
    followup_searches: int
    sufficiency: list[EvidenceSufficiencyResult]
    followup_added_evidence: bool


Checkpoint = Callable[[str, ResearchState], Awaitable[None]]


async def run_workflow(
    session_id: UUID,
    question: str,
    settings: Settings,
    llm: LLMProvider,
    search: SearchProvider,
    budget: RunBudget,
    checkpoint: Checkpoint,
    mode: str = "web",
    documents: Documents | None = None,
    document_ids: list[UUID] | None = None,
) -> ResearchState:
    if not llm.structured_output or not llm.tool_calling:
        raise ResearchFailure("provider_error")

    async def plan_node(state: ResearchState) -> dict[str, object]:
        await checkpoint("planning", state)
        planning_question = (
            state["question"]
            if mode == "web"
            else f"Mode: {mode}; use indexed document passages. Question: {state['question']}"
        )
        result = await budget.invoke(lambda: llm.plan(planning_question), "llm")
        try:
            plan = ResearchPlan.model_validate(account_usage(budget, result))
        except ValidationError as exc:
            raise ResearchFailure("invalid_output") from exc
        state["plan"] = plan
        await checkpoint("planned", state)
        return {"plan": plan}

    async def collect_node(state: ResearchState) -> dict[str, object]:
        assert state["plan"] is not None
        if mode in {"documents", "combined"}:
            if documents is None:
                raise ResearchFailure("no_evidence")
            passages = await documents.retrieve(
                state["question"],
                document_ids or [],
                min(settings.retrieval_k, settings.max_sources),
            )
            if mode == "combined":
                # Request a broad candidate set, then use the strongest lexical match
                # first and reserve one source slot for web evidence.
                passages = sorted(
                    passages,
                    key=lambda passage: (
                        passage.keyword_score is None,
                        -(passage.keyword_score or 0.0),
                        -passage.score,
                    ),
                )[: max(1, settings.max_sources - 1)]
            for passage in passages:
                state["sources"].append(
                    EvidenceSource(
                        source_id=f"S{len(state['sources']) + 1}",
                        session_id=session_id,
                        source_type="document",
                        title=passage.filename,
                        url=f"http://127.0.0.1:3000/#document-{passage.document_id}",
                        retrieved_at=datetime.now(UTC),
                        excerpt=passage.text,
                        content_sha256=passage.checksum,
                        search_query=state["question"][:200],
                        document_id=passage.document_id,
                        chunk_id=passage.chunk_id,
                        page=passage.page,
                        heading=passage.heading,
                        retrieval_score=passage.score,
                    )
                )
            if not passages:
                state["warnings"].append(
                    "No ready document evidence; combined mode used only web evidence."
                )
            await checkpoint("documents_retrieved", state)
            if mode == "documents":
                return {"sources": state["sources"], "warnings": state["warnings"]}
        seen_urls: set[str] = set()
        seen_content: set[str] = set()
        query_limit = settings.max_search_queries
        if settings.search_provider in {"wikipedia", "brave"}:
            query_limit = min(query_limit, settings.max_external_search_requests)
        queries = list(dict.fromkeys(s.search_query for s in state["plan"].subquestions))[
            :query_limit
        ]
        if len(queries) < len(state["plan"].subquestions):
            state["warnings"].append("The query limit or deduplication reduced planned searches.")
        for query in queries:
            if len(state["sources"]) >= settings.max_sources:
                state["warnings"].append("The source limit left remaining searches unperformed.")
                break
            if budget.usage.tool_calls >= settings.max_tool_calls:
                state["warnings"].append("The tool-call budget limited evidence collection.")
                break
            try:

                async def perform_search(value: str = query) -> list[SearchHit]:
                    return await search.search(value)

                hits = await budget.invoke(perform_search, "search")
                state["investigated_queries"].append(query)
            except ResearchFailure as exc:
                if str(exc) == "request_budget_exceeded":
                    raise
                state["warnings"].append("A search query failed; no search results were invented.")
                continue
            for hit in hits[:5]:
                if (
                    len(state["sources"]) >= settings.max_sources
                    or budget.usage.tool_calls >= settings.max_tool_calls
                ):
                    break
                try:
                    url = normalize_url(hit.url)
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    async def perform_fetch(value: str = url) -> FetchedPage:
                        return await search.fetch(value)

                    fetched = await budget.invoke(perform_fetch, "fetch")
                    final, text = fetched.url, fetched.text
                    if fetched.truncated:
                        state["warnings"].append(
                            "An article passage was truncated at the configured text limit."
                        )
                    final = normalize_url(final)
                    digest = content_hash(text)
                    if (
                        len(text) < 40
                        or digest in seen_content
                        or (final != url and final in seen_urls)
                    ):
                        continue
                    seen_urls.add(final)
                    seen_content.add(digest)
                    state["sources"].append(
                        EvidenceSource(
                            source_id=f"S{len(state['sources']) + 1}",
                            session_id=session_id,
                            source_type="mock" if settings.search_provider == "mock" else "web",
                            title=hit.title[:300] or "Untitled source",
                            url=final,
                            retrieved_at=datetime.now(UTC),
                            excerpt=relevant_excerpt(text, query),
                            content_sha256=digest,
                            search_query=query,
                            text_truncated=fetched.truncated,
                        )
                    )
                    await checkpoint("collecting", state)
                except ResearchFailure as exc:
                    if str(exc) == "request_budget_exceeded":
                        raise
                    state["warnings"].append(
                        "An unsafe, inaccessible or unsupported source was excluded."
                    )
            await checkpoint("collected", state)
        return {
            "sources": state["sources"],
            "warnings": state["warnings"],
            "investigated_queries": state["investigated_queries"],
        }

    async def insufficient_node(state: ResearchState) -> dict[str, object]:
        plan = state["plan"]
        assert plan is not None
        if any(warning.startswith("A search query failed") for warning in state["warnings"]):
            await checkpoint("insufficient_evidence", state)
            raise ResearchFailure("no_evidence")
        now = datetime.now(UTC)
        results = [
            insufficient_result(f"Q{index}", item.question, [])
            for index, item in enumerate(plan.subquestions, 1)
        ]
        safe_text = "Insufficient evidence was found in the selected sources to answer reliably."
        abstention = GroundedStatement(text=safe_text, source_ids=[])
        report = DraftReport(
            title="Research findings: no evidence available",
            executive_summary=[abstention],
            objective=state["question"],
            findings=[abstention],
            comparisons=[],
            limitations=["No usable evidence was collected; no answer is provided."],
            conclusion=abstention,
        )
        verification = VerificationSnapshot(
            id=uuid4(),
            session_id=session_id,
            status="completed",
            execution_mode=settings.execution_mode,
            method="no-evidence-abstention-v1",
            iteration=0,
            claims=[],
            verdicts=[],
            contradictions=[],
            candidates={},
            activities=[
                "Claim support assessment skipped because no factual answer was generated."
            ],
            evidence_sufficiency=results,
            evaluated_at=now,
        )
        state["sufficiency"] = results
        state["verification"] = verification
        state["verification_history"].append(verification.model_copy(deep=True))
        state["report"] = report
        state["original_report"] = report.model_copy(deep=True)
        state["draft_history"].append(report.model_copy(deep=True))
        state["markdown"] = (
            render_report(
                report, plan, [], state["warnings"], settings.execution_mode == "mock", results
            )
            + "\n## Evidence support assessment\n\nNo factual answer was generated or assessed.\n"
        )
        state["original_markdown"] = state["markdown"]
        state["warnings"].extend(
            f"Evidence sufficiency {item.question_id}: INSUFFICIENT." for item in results
        )
        await checkpoint("insufficient_evidence", state)
        return {
            "sufficiency": results,
            "verification": verification,
            "verification_history": state["verification_history"],
            "report": report,
            "original_report": state["original_report"],
            "original_markdown": state["original_markdown"],
            "markdown": state["markdown"],
            "draft_history": state["draft_history"],
            "warnings": state["warnings"],
        }

    async def sufficiency_node(state: ResearchState) -> dict[str, object]:
        plan = state["plan"]
        assert plan is not None
        await checkpoint("assessing_sufficiency", state)
        results = []

        async def assess(item: Subquestion, question_id: str) -> EvidenceSufficiencyResult:
            repair_after_invalid = False

            async def call_sufficiency() -> LLMResult[EvidenceSufficiencyDecision]:
                nonlocal repair_after_invalid
                try:
                    if repair_after_invalid:
                        repair = getattr(llm, "repair_sufficiency", None)
                        if repair is not None:
                            repair_call = cast(
                                Callable[
                                    [str, str, list[EvidenceSource]],
                                    Awaitable[LLMResult[EvidenceSufficiencyDecision]],
                                ],
                                repair,
                            )
                            return await repair_call(question_id, item.question, state["sources"])
                    return await llm.assess_sufficiency(
                        question_id, item.question, state["sources"]
                    )
                except InvalidProviderOutput:
                    repair_after_invalid = True
                    raise

            result = await budget.invoke(
                call_sufficiency,
                "llm",
            )
            decision = account_usage(budget, result)
            return evaluated_result(decision, item.question)

        for index, item in enumerate(plan.subquestions, 1):
            evaluated = await assess(item, f"Q{index}")
            try:
                evaluated.validate_consistency(state["sources"])
            except ValueError as exc:
                raise ResearchFailure("invalid_output") from exc
            if evaluated.question_id != f"Q{index}" or evaluated.question_text != item.question:
                raise ResearchFailure("invalid_output")
            results.append(evaluated)
        state["sufficiency"] = results
        state["warnings"] = [
            warning
            for warning in state["warnings"]
            if not warning.startswith("Evidence sufficiency Q")
        ]
        state["warnings"].extend(
            f"Evidence sufficiency {item.question_id}: {item.status}."
            for item in results
            if item.status != "SUFFICIENT"
        )
        await checkpoint("evidence_assessed", state)
        return {"sufficiency": results}

    async def write_node(state: ResearchState) -> dict[str, object]:
        plan = state["plan"]
        assert plan is not None
        await checkpoint("writing", state)
        if state["sufficiency"] and all(
            item.status == "INSUFFICIENT" for item in state["sufficiency"]
        ):
            safe_text = (
                "Insufficient evidence was found in the selected sources to answer reliably."
            )
            abstention = GroundedStatement(text=safe_text, source_ids=[])
            report = DraftReport(
                title="Research findings: evidence insufficient",
                executive_summary=[abstention],
                objective=plan.objective,
                findings=[abstention],
                comparisons=[],
                limitations=[
                    "No answer is provided because the evidence review found no supported response."
                ],
                conclusion=abstention,
            )
        else:
            result = await budget.invoke(
                lambda: llm.write_grounded(
                    state["question"], plan, state["sources"], state["sufficiency"]
                ),
                "llm",
            )
            try:
                report = DraftReport.model_validate(account_usage(budget, result))
            except ValidationError as exc:
                raise ResearchFailure("invalid_output") from exc
        markdown = render_report(
            report,
            plan,
            state["sources"],
            state["warnings"],
            settings.execution_mode == "mock",
            state["sufficiency"],
        )
        state["report"] = report
        state["markdown"] = markdown
        if state["original_report"] is None:
            state["original_report"] = report.model_copy(deep=True)
            state["original_markdown"] = markdown
        state["draft_history"].append(report.model_copy(deep=True))
        await checkpoint("written", state)
        return {
            "report": report,
            "markdown": markdown,
            "original_report": state["original_report"],
            "original_markdown": state["original_markdown"],
            "draft_history": state["draft_history"],
        }

    async def verify_node(state: ResearchState) -> dict[str, object]:
        report = state["report"]
        assert report is not None
        await checkpoint("verifying_claims", state)
        try:
            if (
                mode == "documents"
                and settings.execution_mode == "local"
                and state["sufficiency"]
                and all(item.status == "INSUFFICIENT" for item in state["sufficiency"])
            ):
                result = VerificationSnapshot(
                    id=uuid4(),
                    session_id=session_id,
                    status="completed",
                    execution_mode=settings.execution_mode,
                    method="insufficient-evidence-abstention-v1",
                    iteration=state["iteration"],
                    claims=[],
                    verdicts=[],
                    contradictions=[],
                    candidates={},
                    activities=[
                        "Claim extraction and verification skipped because no factual answer "
                        "was generated."
                    ],
                    evidence_sufficiency=list(state["sufficiency"]),
                    evaluated_at=datetime.now(UTC),
                )
            else:
                result = await verify(
                    report,
                    state["sources"],
                    session_id,
                    llm,
                    budget,
                    state["iteration"],
                    state["verification"],
                )
        except ResearchFailure:
            raise
        except Exception as exc:
            raise ResearchFailure("verification_failed") from exc
        state["verification"] = result
        result.evidence_sufficiency = list(state["sufficiency"])
        state["verification_history"].append(result.model_copy(deep=True))
        await checkpoint("claims_assessed", state)
        return {"verification": result, "verification_history": state["verification_history"]}

    def needs_followup(state: ResearchState) -> str:
        assessment = state["verification"]
        assert assessment is not None
        important = {c.claim_id for c in assessment.claims if c.important and c.checkable}
        gaps = any(
            v.claim_id in important and v.status in {"INSUFFICIENT_EVIDENCE", "CONTRADICTED"}
            for v in assessment.verdicts
        )
        return (
            "followup"
            if gaps and state["iteration"] < settings.max_verification_iterations
            else "finalize"
        )

    async def followup_node(state: ResearchState) -> dict[str, object]:
        assessment = state["verification"]
        assert assessment is not None
        state["iteration"] += 1
        source_count_before = len(state["sources"])
        await checkpoint("followup_research", state)
        gap_ids = {
            v.claim_id
            for v in assessment.verdicts
            if v.status in {"INSUFFICIENT_EVIDENCE", "CONTRADICTED"}
        }
        gaps = [c for c in assessment.claims if c.important and c.claim_id in gap_ids][:2]
        known_hashes = {source.content_sha256 for source in state["sources"]}
        known_urls = {source.url for source in state["sources"]}
        for claim in gaps:
            query = claim.text[:200]
            if mode in {"documents", "combined"} and documents is not None:
                passages = await documents.retrieve(query, document_ids or [], settings.retrieval_k)
                assessment.activities.append(
                    f"Iteration {state['iteration']}: document retrieval for {claim.claim_id}; "
                    f"{len(passages)} candidates."
                )
                for passage in passages:
                    if (
                        len(state["sources"]) >= settings.max_sources
                        or passage.checksum in known_hashes
                    ):
                        continue
                    known_hashes.add(passage.checksum)
                    state["sources"].append(
                        EvidenceSource(
                            source_id=f"S{len(state['sources']) + 1}",
                            session_id=session_id,
                            source_type="document",
                            title=passage.filename,
                            url=f"http://127.0.0.1:3000/#document-{passage.document_id}",
                            retrieved_at=datetime.now(UTC),
                            excerpt=passage.text,
                            content_sha256=passage.checksum,
                            search_query=query,
                            document_id=passage.document_id,
                            chunk_id=passage.chunk_id,
                            page=passage.page,
                            retrieval_score=passage.score,
                        )
                    )
            if (
                mode in {"web", "combined"}
                and state["followup_searches"] < settings.max_followup_searches
            ):
                state["followup_searches"] += 1
                try:

                    async def targeted_search(value: str = query) -> list[SearchHit]:
                        return await search.search(value)

                    hits = await budget.invoke(targeted_search, "search")
                    state["investigated_queries"].append(query)
                    assessment.activities.append(
                        f"Iteration {state['iteration']}: targeted web search for {claim.claim_id}."
                    )
                    for hit in hits[:3]:
                        if len(state["sources"]) >= settings.max_sources:
                            break
                        url = normalize_url(hit.url)
                        if url in known_urls:
                            continue
                        known_urls.add(url)

                        async def targeted_fetch(value: str = url) -> FetchedPage:
                            return await search.fetch(value)

                        fetched = await budget.invoke(targeted_fetch, "fetch")
                        final, text = fetched.url, fetched.text
                        if fetched.truncated:
                            state["warnings"].append(
                                "An article passage was truncated at the configured text limit."
                            )
                        final, digest = normalize_url(final), content_hash(text)
                        if len(text) < 40 or digest in known_hashes:
                            continue
                        known_hashes.add(digest)
                        state["sources"].append(
                            EvidenceSource(
                                source_id=f"S{len(state['sources']) + 1}",
                                session_id=session_id,
                                source_type="mock" if settings.search_provider == "mock" else "web",
                                title=hit.title[:300] or "Untitled",
                                url=final,
                                retrieved_at=datetime.now(UTC),
                                excerpt=relevant_excerpt(text, query),
                                content_sha256=digest,
                                search_query=query,
                                text_truncated=fetched.truncated,
                            )
                        )
                except ResearchFailure as exc:
                    if str(exc) == "request_budget_exceeded":
                        raise
                    assessment.activities.append(
                        "Follow-up evidence unavailable or budget exhausted; no evidence invented."
                    )
        # Qualify gaps while retaining contrary evidence and the original wording.
        report = state["report"]
        assert report is not None
        revised = report.model_copy(deep=True)
        gaps_by_location = {c.location for c in assessment.claims if c.claim_id in gap_ids}
        for section in ("executive_summary", "findings", "comparisons"):
            for i, statement in enumerate(getattr(revised, section)):
                if f"{section}:{i}" in gaps_by_location and not statement.text.startswith(
                    "Unresolved support: "
                ):
                    statement.text = "Unresolved support: " + statement.text[:1170]
        if "conclusion:0" in gaps_by_location and not revised.conclusion.text.startswith(
            "Unresolved support: "
        ):
            revised.conclusion.text = "Unresolved support: " + revised.conclusion.text[:1170]
        if len(revised.limitations) < 8:
            revised.limitations.append(
                "Evidence gaps or possible contradictions remain; qualified sections "
                "are not established findings."
            )
        state["report"] = revised
        state["draft_history"].append(revised.model_copy(deep=True))
        await checkpoint("revised_draft", state)
        state["followup_added_evidence"] = len(state["sources"]) > source_count_before
        return {
            "report": revised,
            "sources": state["sources"],
            "iteration": state["iteration"],
            "followup_searches": state["followup_searches"],
            "verification": assessment,
            "draft_history": state["draft_history"],
            "investigated_queries": state["investigated_queries"],
            "followup_added_evidence": state["followup_added_evidence"],
        }

    async def finalize_node(state: ResearchState) -> dict[str, object]:
        assessment, report, plan = state["verification"], state["report"], state["plan"]
        assert assessment is not None and report is not None and plan is not None
        assessment.status = "completed"
        markdown = render_report(
            report,
            plan,
            state["sources"],
            state["warnings"],
            settings.execution_mode == "mock",
            state["sufficiency"],
        )
        markdown += "\n## Evidence support assessment\n\n"
        markdown += (
            "MOCK procedure outputs; no evaluated real-world verification quality.\n\n"
            if settings.execution_mode == "mock"
            else "Model assessment of collected evidence; not absolute truth.\n\n"
        )
        for verdict in assessment.verdicts:
            claim = next(c for c in assessment.claims if c.claim_id == verdict.claim_id)
            markdown += (
                f"- {claim.claim_id} ({escape(claim.location)}): "
                f"{escape(claim.text)} — {verdict.status}\n"
            )
            markdown += f"  Method: {escape(verdict.method)}; {verdict.evaluated_at.isoformat()}\n"
            markdown += f"  {escape(verdict.explanation)}\n"
            for match in verdict.matches:
                markdown += f"  [{match.source_id}] {match.role}: {escape(match.quote)}\n"
        markdown += (
            f"\nPossible conflicts: {len(assessment.contradictions)}. "
            + f"Follow-up iterations: {state['iteration']}.\n"
        )
        for conflict in assessment.contradictions:
            markdown += f"\n[{conflict.first_source_id}] {escape(conflict.first_statement)} vs "
            markdown += f"[{conflict.second_source_id}] {escape(conflict.second_statement)}\n"
            markdown += escape(conflict.reason) + " " + escape(conflict.context_caveat) + "\n"
        for activity in assessment.activities:
            markdown += "\n- " + escape(activity)
        state["markdown"] = markdown
        await checkpoint("verification_complete", state)
        return {"markdown": markdown, "verification": assessment}

    graph = StateGraph(ResearchState)
    graph.add_node("plan", plan_node)
    graph.add_node("collect", collect_node)
    graph.add_node("assess_sufficiency", sufficiency_node)
    graph.add_node("insufficient", insufficient_node)
    graph.add_node("write", write_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "collect")
    graph.add_conditional_edges(
        "collect", lambda state: "assess_sufficiency" if state["sources"] else "insufficient"
    )
    graph.add_edge("assess_sufficiency", "write")
    graph.add_node("verify", verify_node)
    graph.add_node("followup", followup_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge("write", "verify")
    graph.add_conditional_edges("verify", needs_followup)
    graph.add_conditional_edges(
        "followup",
        lambda state: "assess_sufficiency" if state["followup_added_evidence"] else "verify",
    )
    graph.add_edge("finalize", END)
    graph.add_edge("insufficient", END)
    initial: ResearchState = {
        "question": question,
        "plan": None,
        "sources": [],
        "investigated_queries": [],
        "warnings": [],
        "report": None,
        "markdown": None,
        "original_report": None,
        "original_markdown": None,
        "verification": None,
        "verification_history": [],
        "draft_history": [],
        "iteration": 0,
        "followup_searches": 0,
        "sufficiency": [],
        "followup_added_evidence": False,
    }
    # Never inherit ambient LangSmith tracing or send research data to telemetry.
    with tracing_context(enabled=False):
        result = await graph.compile().ainvoke(initial, config={"recursion_limit": 16})
    return cast(ResearchState, result)
