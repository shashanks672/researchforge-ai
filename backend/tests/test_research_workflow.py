import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.documents.schemas import Passage
from app.research.budget import RunBudget
from app.research.errors import InvalidProviderOutput, ResearchFailure
from app.research.providers import (
    DisabledSearch,
    LLMResult,
    MockLLM,
    MockSearch,
    SearchHit,
    WikipediaSearch,
    providers,
)
from app.research.schemas import DraftReport, EvidenceSource, ResearchPlan
from app.research.sufficiency import EvidenceQuote, EvidenceSufficiencyDecision, FactAssessment
from app.research.workflow import ResearchState, run_workflow


def mock_settings(**values: object) -> Settings:
    return Settings.model_validate({"llm_provider": "mock", "search_provider": "mock", **values})


def test_graph_plan_collection_citations_and_deduplication() -> None:
    async def exercise() -> None:
        settings = mock_settings()
        budget = RunBudget(settings)
        checkpoints: list[str] = []

        async def save(stage: str, state: ResearchState) -> None:
            checkpoints.append(stage)

        result = await run_workflow(
            uuid4(), "Explain source grounding", settings, MockLLM(), MockSearch(), budget, save
        )
        assert len(result["sources"]) == 2
        assert len({s.url for s in result["sources"]}) == 2
        assert result["plan"] is not None and len(result["plan"].subquestions) == 2
        assert checkpoints[0] == "planning" and checkpoints[-1] == "verification_complete"
        assert "planned" in checkpoints and "writing" in checkpoints
        assert result["markdown"] and "MOCK DEMONSTRATION" in result["markdown"]
        assert "[S1]: https://example.org/" in result["markdown"]
        assert all(s.source_type == "mock" and s.published_at is None for s in result["sources"])
        assert len(result["investigated_queries"]) == 3
        assert budget.usage.llm_calls == 7
        assert budget.usage.tool_calls == 5
        assert budget.usage.estimated_cost_usd == 0
        assert "Insufficient evidence" in result["markdown"]
        assert all(item.status == "INSUFFICIENT" for item in result["sufficiency"])

    asyncio.run(exercise())


def test_invalid_sufficiency_response_gets_one_repair_attempt() -> None:
    class RepairableLLM(MockLLM):
        invalid_calls = 0
        repair_calls = 0

        async def assess_sufficiency(
            self, question_id: str, question: str, sources: list[EvidenceSource]
        ) -> LLMResult[EvidenceSufficiencyDecision]:
            self.invalid_calls += 1
            raise InvalidProviderOutput("invalid_output")

        async def repair_sufficiency(
            self, question_id: str, question: str, sources: list[EvidenceSource]
        ) -> LLMResult[EvidenceSufficiencyDecision]:
            self.repair_calls += 1
            return await super().assess_sufficiency(question_id, question, sources)

    async def exercise() -> None:
        settings = mock_settings(provider_retries=1)
        budget = RunBudget(settings)
        llm = RepairableLLM()

        async def save(stage: str, state: ResearchState) -> None:
            pass

        result = await run_workflow(
            uuid4(),
            "Explain source grounding",
            settings,
            llm,
            MockSearch(),
            budget,
            save,
        )
        assert len(result["sufficiency"]) == 2
        assert llm.invalid_calls == 2
        assert llm.repair_calls == 2
        assert budget.usage.llm_calls == 9

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["web", "combined"])
def test_wikipedia_web_modes_preserve_real_source_provenance_offline(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the Wikipedia adapter and full graph without public requests."""

    class OnePassage:
        async def retrieve(
            self, question: str, document_ids: list[object], k: int
        ) -> list[Passage]:
            if mode == "combined":
                assert k == 3
                document_id = document_ids[0]
                # Simulate hybrid retrieval putting a weaker page first. The workflow
                # should rank the stronger lexical match among the retrieved candidates.
                return [
                    Passage(
                        chunk_id=uuid4(),
                        document_id=document_id,
                        filename="phase7-local-demo.pdf",
                        page=2,
                        heading="Maintenance",
                        text="The battery was installed in March 2025.",
                        checksum="c" * 64,
                        score=0.95,
                        keyword_score=0.4,
                    ),
                    Passage(
                        chunk_id=uuid4(),
                        document_id=document_id,
                        filename="phase7-local-demo.pdf",
                        page=1,
                        heading="Specifications",
                        text="The Juniper battery has a rated capacity of 12 kWh.",
                        checksum="d" * 64,
                        score=0.7,
                        keyword_score=4.0,
                    ),
                ]
            return [
                Passage(
                    chunk_id=uuid4(),
                    document_id=document_ids[0],
                    filename="selected-research.txt",
                    page=2,
                    heading="Findings",
                    text="The selected study reports its method and limitations in this passage.",
                    checksum="b" * 64,
                    score=0.91,
                )
            ]

    async def exercise() -> None:
        settings = Settings.model_validate(
            {
                "llm_provider": "ollama",
                "search_provider": "wikipedia",
                "free_search_enabled": True,
                "public_search_contact": "mailto:offline-test@example.invalid",
                "max_sources": 3,
                "max_verification_iterations": 0,
                "max_followup_searches": 0,
            }
        )
        llm_provider, search = providers(settings)
        assert isinstance(search, WikipediaSearch)
        await llm_provider.close()
        monkeypatch.setattr(WikipediaSearch, "MIN_INTERVAL_SECONDS", 0)

        async def offline_wikipedia_response(
            url: str,
            headers: dict[str, str] | None = None,
            redirects: int = 0,
        ) -> tuple[str, bytes, str]:
            if "w/api.php" in url:
                return (
                    "https://en.wikipedia.org/w/api.php",
                    json.dumps({"query": {"search": [{"title": "Solar power"}]}}).encode(),
                    "application/json",
                )
            return (
                url,
                b"<html><body><p>Solar power is the conversion of sunlight into "
                b"electricity or heat. This public reference passage is provided "
                b"only by an offline test fixture.</p></body></html>",
                "text/html",
            )

        search.http.get = offline_wikipedia_response  # type: ignore[method-assign]
        budget = RunBudget(settings)

        async def save(stage: str, state: ResearchState) -> None:
            pass

        document_id = uuid4()
        result = await run_workflow(
            uuid4(),
            (
                "What is the Juniper battery's rated capacity, and what does a kilowatt-hour mean?"
                if mode == "combined"
                else "How does solar power convert sunlight into electricity?"
            ),
            settings,
            MockLLM(),
            search,
            budget,
            save,
            mode=mode,
            documents=OnePassage() if mode == "combined" else None,  # type: ignore[arg-type]
            document_ids=[document_id] if mode == "combined" else [],
        )
        sources = result["sources"]
        web_sources = [source for source in sources if source.source_type == "web"]
        assert len(web_sources) == 1
        assert web_sources[0].url == "https://en.wikipedia.org/wiki/Solar_power"
        assert "public reference passage" in web_sources[0].excerpt
        assert len(web_sources[0].content_sha256) == 64
        assert web_sources[0].search_query
        if mode == "web":
            assert len(sources) == 1
        else:
            doc_sources = [source for source in sources if source.source_type == "document"]
            assert any(source.page == 1 and "12 kWh" in source.excerpt for source in doc_sources)
            assert any(source.source_type == "web" for source in sources)
        assert budget.usage.search_calls >= 1
        assert budget.usage.fetch_calls >= 1
        assert result["markdown"]
        assert "Insufficient evidence" in result["markdown"]

    asyncio.run(exercise())


def test_disabled_local_search_fails_closed_without_mock_substitution() -> None:
    async def exercise() -> None:
        settings = Settings.model_validate(
            {
                "llm_provider": "ollama",
                "search_provider": "disabled",
                "max_verification_iterations": 0,
            }
        )
        llm, search = providers(settings)
        assert isinstance(search, DisabledSearch)
        await llm.close()
        budget = RunBudget(settings)

        async def save(stage: str, state: ResearchState) -> None:
            pass

        with pytest.raises(ResearchFailure, match="no_evidence"):
            await run_workflow(
                uuid4(),
                "What does the public evidence say about this topic?",
                settings,
                MockLLM(),
                search,
                budget,
                save,
                mode="web",
            )
        assert budget.usage.search_calls > 0
        assert budget.usage.fetch_calls == 0

    asyncio.run(exercise())


def test_local_document_abstention_skips_claim_models() -> None:
    class OnePassage:
        async def retrieve(
            self, question: str, document_ids: list[object], k: int
        ) -> list[Passage]:
            return [
                Passage(
                    chunk_id=uuid4(),
                    document_id=uuid4(),
                    filename="fixture.txt",
                    page=1,
                    heading=None,
                    text="The device was installed in 2025. No price is listed.",
                    checksum="a" * 64,
                    score=0.9,
                )
            ]

    async def exercise() -> None:
        settings = Settings.model_validate(
            {"llm_provider": "ollama", "search_provider": "disabled"}
        )
        budget = RunBudget(settings)

        async def save(stage: str, state: ResearchState) -> None:
            pass

        result = await run_workflow(
            uuid4(),
            "What is the device's annual service cost?",
            settings,
            MockLLM(),
            MockSearch(),
            budget,
            save,
            mode="documents",
            documents=OnePassage(),  # type: ignore[arg-type]
            document_ids=[uuid4()],
        )
        verification = result["verification"]
        assert verification is not None and verification.claims == []
        assert verification.verdicts == [] and verification.contradictions == []
        assert verification.activities == [
            "Claim extraction and verification skipped because no factual answer was generated."
        ]
        assert "Insufficient evidence" in (result["markdown"] or "")
        assert budget.usage.llm_calls == 3  # planning and two sufficiency questions only

    asyncio.run(exercise())


def test_invalid_constructed_plan_is_revalidated() -> None:
    class InvalidLLM(MockLLM):
        async def plan(self, question: str) -> LLMResult[ResearchPlan]:
            return LLMResult(
                ResearchPlan.model_construct(objective="bad", scope="", subquestions=[])
            )

    async def exercise() -> None:
        async def save(stage: str, state: ResearchState) -> None:
            pass

        with pytest.raises(ResearchFailure, match="invalid_output"):
            await run_workflow(
                uuid4(),
                "Explain evidence grounding",
                mock_settings(),
                InvalidLLM(),
                MockSearch(),
                RunBudget(mock_settings()),
                save,
            )

    asyncio.run(exercise())


def test_empty_evidence_returns_explicit_abstention_without_writer() -> None:
    class EmptySearch(MockSearch):
        async def search(self, query: str) -> list[SearchHit]:
            return []

    class NoWriter(MockLLM):
        async def write(
            self, question: str, plan: ResearchPlan, sources: list[EvidenceSource]
        ) -> LLMResult[DraftReport]:
            raise AssertionError("Writer must never run without evidence")

    async def exercise() -> None:
        stages: list[str] = []

        async def save(stage: str, state: ResearchState) -> None:
            stages.append(stage)

        result = await run_workflow(
            uuid4(),
            "Explain evidence grounding",
            mock_settings(),
            NoWriter(),
            EmptySearch(),
            RunBudget(mock_settings()),
            save,
        )
        assert stages[-1] == "insufficient_evidence"
        assert result["report"] is not None
        assert result["markdown"] and "Insufficient evidence" in result["markdown"]
        assert result["verification"] is not None
        assert result["verification"].claims == []

    asyncio.run(exercise())


def test_unknown_citations_fail_the_mandatory_writer_stage() -> None:
    class BadCitations(MockLLM):
        async def assess_sufficiency(
            self, question_id: str, question: str, sources: list[EvidenceSource]
        ) -> LLMResult[EvidenceSufficiencyDecision]:
            return LLMResult(
                EvidenceSufficiencyDecision(
                    question_id=question_id,
                    status="PARTIAL",
                    supporting_evidence_ids=[sources[0].source_id],
                    missing_information=["a remaining detail"],
                    explanation="The passage supports only one requested element.",
                    fact_assessments=[
                        FactAssessment(
                            fact="A supported detail",
                            entity="",
                            property="detail",
                            value="",
                            unit="",
                            time_period="",
                            scope="",
                            negation="",
                            status="SUPPORTED",
                            evidence=[
                                EvidenceQuote(
                                    source_id=sources[0].source_id,
                                    quote=sources[0].excerpt[:30],
                                )
                            ],
                        ),
                        FactAssessment(
                            fact="A remaining detail",
                            entity="",
                            property="detail",
                            value="",
                            unit="",
                            time_period="",
                            scope="",
                            negation="",
                            status="MISSING",
                            evidence=[],
                        ),
                    ],
                )
            )

        async def write(
            self, question: str, plan: ResearchPlan, sources: list[EvidenceSource]
        ) -> LLMResult[DraftReport]:
            result = await super().write(question, plan, sources)
            result.value.findings[0].source_ids = ["invented-source"]
            return result

    async def exercise() -> None:
        async def save(stage: str, state: ResearchState) -> None:
            pass

        with pytest.raises(ResearchFailure, match="invalid_output"):
            await run_workflow(
                uuid4(),
                "Explain evidence grounding",
                mock_settings(),
                BadCitations(),
                MockSearch(),
                RunBudget(mock_settings()),
                save,
            )

    asyncio.run(exercise())


def test_budget_retains_partial_evidence_with_explicit_limitation() -> None:
    async def exercise() -> None:
        settings = mock_settings(max_tool_calls=2)
        budget = RunBudget(settings)

        async def save(stage: str, state: ResearchState) -> None:
            pass

        result = await run_workflow(
            uuid4(), "Explain evidence grounding", settings, MockLLM(), MockSearch(), budget, save
        )
        assert budget.usage.tool_calls == 2
        assert len(result["sources"]) == 1
        assert result["warnings"]

    asyncio.run(exercise())


def test_real_timeout_retries_are_bounded() -> None:
    async def exercise() -> None:
        settings = mock_settings(provider_retries=1).model_copy(
            update={"provider_timeout_seconds": 0.01}
        )
        budget = RunBudget(settings)

        async def slow() -> None:
            await asyncio.sleep(2)

        with pytest.raises(ResearchFailure, match="provider_timeout"):
            await budget.invoke(slow, "llm")
        assert budget.usage.llm_calls == 2 and not budget.usage.usage_complete

    asyncio.run(exercise())


def test_provider_configuration_requires_explicit_pair_and_approval() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="mock", search_provider="disabled")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_provider="openai", search_provider="brave")
    hosted = Settings(
        _env_file=None,
        llm_provider="openai",
        search_provider="brave",
        llm_model="gpt-4.1-mini",
        openai_api_key=SecretStr("sk-test-never-real"),
        brave_api_key=SecretStr("test-never-real-key"),
        input_usd_per_million=1,
        output_usd_per_million=2,
        search_usd_per_request=0.002,
    )
    assert hosted.execution_mode == "disabled"
    assert hosted.model_copy(update={"live_calls_approved": True}).execution_mode == "live"
    assert "sk-test-never-real" not in repr(hosted)
    with pytest.raises(ValidationError, match="unit prices"):
        Settings(
            _env_file=None,
            llm_provider="openai",
            search_provider="brave",
            llm_model="gpt-4.1-mini",
            openai_api_key=SecretStr("sk-test-never-real"),
            brave_api_key=SecretStr("test-never-real-key"),
            live_calls_approved=True,
        )
