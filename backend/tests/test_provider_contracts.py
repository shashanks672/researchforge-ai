import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from openai import APIStatusError
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.research.budget import RunBudget
from app.research.errors import InvalidProviderOutput, ResearchFailure, TransientProviderError
from app.research.providers import (
    BraveSearch,
    LLMResult,
    MockLLM,
    OllamaLLM,
    OpenAILLM,
    WikipediaSearch,
    account_usage,
)
from app.research.schemas import EvidenceSource, ResearchPlan, Subquestion
from app.research.sufficiency import (
    EvidenceQuote,
    EvidenceSufficiencyDecision,
    FactAssessment,
)
from app.research.verification_schemas import Extraction


def hosted_settings() -> Settings:
    # Contract tests replace network methods before calling them. These are fake keys.
    return Settings(
        _env_file=None,
        llm_provider="openai",
        search_provider="brave",
        llm_model="gpt-4.1-mini",
        openai_api_key=SecretStr("sk-test-never-real"),
        brave_api_key=SecretStr("test-never-real-key"),
        live_calls_approved=True,
        input_usd_per_million=1,
        output_usd_per_million=2,
        search_usd_per_request=0.002,
    )


def ollama_settings(**values: object) -> Settings:
    return Settings.model_validate(
        {
            "_env_file": None,
            "llm_provider": "ollama",
            "search_provider": "disabled",
            "ollama_model": "qwen3:8b",
            **values,
        }
    )


def test_research_plan_accepts_one_focused_subquestion() -> None:
    plan = ResearchPlan(
        objective="Find the rated capacity.",
        scope="Use only the requested battery fact.",
        subquestions=[
            Subquestion(
                question="What is the rated capacity?",
                search_query="rated battery capacity",
            )
        ],
    )
    assert len(plan.subquestions) == 1


def test_hosted_plan_uses_strict_allowlisted_function_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        plan = (await MockLLM().plan("Explain evidence provenance")).value
        provider = OpenAILLM(hosted_settings())
        mocked = AsyncMock(
            return_value=SimpleNamespace(
                status="completed",
                output=[
                    SimpleNamespace(
                        type="function_call", name="submit_plan", arguments=plan.model_dump_json()
                    )
                ],
                usage=SimpleNamespace(input_tokens=100, output_tokens=40),
            )
        )
        monkeypatch.setattr(provider.client.responses, "create", mocked)
        try:
            result = await provider.plan("Explain evidence provenance")
            assert result.value == plan and result.input_tokens == 100
            kwargs = mocked.call_args.kwargs
            assert kwargs["tools"][0]["name"] == "submit_plan"
            assert kwargs["tools"][0]["strict"] is True
            assert kwargs["parallel_tool_calls"] is False and kwargs["store"] is False
            assert kwargs["max_output_tokens"] == 1500
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_hosted_invalid_plan_is_rejected_without_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        provider = OpenAILLM(hosted_settings())
        mocked = AsyncMock(
            return_value=SimpleNamespace(
                status="completed",
                output=[
                    SimpleNamespace(
                        type="function_call", name="submit_plan", arguments='{"objective":"bad"}'
                    )
                ],
                usage=None,
            )
        )
        monkeypatch.setattr(provider.client.responses, "create", mocked)
        try:
            with pytest.raises(ResearchFailure, match="invalid_output"):
                await provider.plan("Explain evidence provenance")
            assert mocked.call_count == 1
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_usage_cost_is_only_estimated_with_prices_and_complete_usage() -> None:
    budget = RunBudget(hosted_settings())
    plan = ResearchPlan.model_construct(objective="test", scope="test", subquestions=[])
    account_usage(budget, LLMResult(plan, input_tokens=1000, output_tokens=500))
    assert budget.usage.estimated_cost_usd == 0.002
    with pytest.raises(ResearchFailure, match="provider_error"):
        account_usage(budget, LLMResult(plan, usage_available=False))
    assert budget.usage.estimated_cost_usd is None


def test_extraction_schema_keeps_strict_required_output_fields() -> None:
    schema = Extraction.model_json_schema()
    claim_schema = schema["$defs"]["ExtractedClaim"]
    assert set(claim_schema["required"]) == set(claim_schema["properties"])
    assert "eligibility" not in claim_schema["properties"]
    assert "eligibility_reason" not in claim_schema["properties"]


def test_brave_query_and_header_contract_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        provider = BraveSearch(hosted_settings())
        payload = {
            "web": {"results": [{"title": "Contract fixture", "url": "https://example.org/paper"}]}
        }
        mocked = AsyncMock(
            return_value=(
                "https://api.search.brave.com/",
                json.dumps(payload).encode(),
                "application/json",
            )
        )
        monkeypatch.setattr(provider.http, "get", mocked)
        hits = await provider.search("source grounding")
        assert len(hits) == 1 and hits[0].url == "https://example.org/paper"
        assert "q=source+grounding" in mocked.call_args.args[0]
        assert mocked.call_args.kwargs["redirects"] == 0

    asyncio.run(exercise())


def test_sufficiency_output_is_structured_and_source_ids_are_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        provider = OpenAILLM(hosted_settings())
        schema = EvidenceSufficiencyDecision.model_json_schema()
        assert set(schema["required"]) == set(schema["properties"])
        assert not {"evaluator_version", "evaluated_at", "question_text", "sufficient"} & set(
            schema["properties"]
        )
        expected = EvidenceSufficiencyDecision(
            question_id="Q1",
            status="INSUFFICIENT",
            supporting_evidence_ids=[],
            missing_information=["capacity"],
            explanation="The evidence does not provide a capacity value.",
            fact_assessments=[
                FactAssessment(
                    fact="Battery capacity",
                    entity="battery",
                    property="capacity",
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
        mocked = AsyncMock(
            return_value=SimpleNamespace(
                status="completed",
                output_parsed=expected,
                usage=SimpleNamespace(input_tokens=40, output_tokens=20),
            )
        )
        monkeypatch.setattr(provider.client.responses, "parse", mocked)
        try:
            result = await provider.assess_sufficiency(
                "Q1", "What capacity does the battery have?", []
            )
            assert result.value.status == "INSUFFICIENT"
            assert result.value.missing_information == ["Battery capacity"]
            assert result.input_tokens == 40
            assert "keyword overlap" in mocked.call_args.kwargs["instructions"]
            data = json.loads(mocked.call_args.kwargs["input"])
            assert data["question_id"] == "Q1" and data["untrusted_evidence"] == []
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_sufficiency_keeps_exact_quote_check_fail_closed() -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=0)
        provider = OllamaLLM(settings)
        source = EvidenceSource(
            source_id="S1",
            session_id=uuid4(),
            source_type="web",
            title="Unit definition",
            url="https://example.org/unit",
            retrieved_at=datetime.now(UTC),
            excerpt="One kilowatt-hour is equal to 3.6 MJ of energy.",
            content_sha256="a" * 64,
            search_query="kilowatt-hour definition",
        )
        malformed_quote = EvidenceSufficiencyDecision(
            question_id="Q1",
            status="SUFFICIENT",
            supporting_evidence_ids=["S1"],
            missing_information=[],
            explanation="The source identifies the unit and its energy conversion.",
            fact_assessments=[
                FactAssessment(
                    fact="Energy conversion",
                    entity="kilowatt-hour",
                    property="energy equivalent",
                    value="3.6 megajoules",
                    unit="MJ",
                    time_period="",
                    scope="",
                    negation="",
                    status="SUPPORTED",
                    evidence=[EvidenceQuote(source_id="S1", quote="3.6 megajoules")],
                )
            ],
        )

        async def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert "character-for-character" in payload["messages"][0]["content"]
            return httpx.Response(
                200,
                json={
                    "message": {"content": malformed_quote.model_dump_json()},
                    "prompt_eval_count": 100,
                    "eval_count": 50,
                    "done_reason": "stop",
                },
            )

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url=settings.ollama_url
        )
        try:
            with pytest.raises(ResearchFailure, match="exact_quote_invalid"):
                await provider.assess_sufficiency("Q1", "What is the energy equivalent?", [source])
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_sufficiency_repair_rejects_paraphrase_then_accepts_exact_span() -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=0)
        provider = OllamaLLM(settings)
        excerpt = (
            "Synthetic training note: The workshop's energy ledger uses kilowatt-hours "
            "(kWh) to record total electrical energy consumed during each test cycle."
        )
        exact_quote = "to record total electrical energy consumed during each test cycle."
        source = EvidenceSource(
            source_id="S1",
            session_id=uuid4(),
            source_type="web",
            title="Synthetic kilowatt-hour note",
            url="https://example.org/unit",
            retrieved_at=datetime.now(UTC),
            excerpt=excerpt,
            content_sha256="b" * 64,
            search_query="kilowatt-hour definition",
        )

        def decision(quote: str) -> EvidenceSufficiencyDecision:
            return EvidenceSufficiencyDecision(
                question_id="Q1",
                status="SUFFICIENT",
                supporting_evidence_ids=["S1"],
                missing_information=[],
                explanation="The cited passage directly defines the energy unit.",
                fact_assessments=[
                    FactAssessment(
                        fact="A kilowatt-hour is a unit of energy.",
                        entity="kilowatt-hour",
                        property="quantity measured",
                        value="energy",
                        unit="",
                        time_period="",
                        scope="general definition",
                        negation="",
                        status="SUPPORTED",
                        evidence=[EvidenceQuote(source_id="S1", quote=quote)],
                    )
                ],
            )

        responses = [
            decision("The device's energy use is tracked in kilowatt-hours."),
            decision(exact_quote),
        ]
        instructions: list[str] = []

        async def respond(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            instructions.append(payload["messages"][0]["content"])
            output = responses.pop(0)
            return httpx.Response(
                200,
                json={
                    "message": {"content": output.model_dump_json()},
                    "prompt_eval_count": 100,
                    "eval_count": 50,
                    "done_reason": "stop",
                },
            )

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url=settings.ollama_url,
            trust_env=False,
        )
        try:
            with pytest.raises(InvalidProviderOutput, match="exact_quote_invalid"):
                await provider.assess_sufficiency(
                    "Q1", "What is a kilowatt-hour, and what quantity does it measure?", [source]
                )
            repaired = await provider.repair_sufficiency(
                "Q1", "What is a kilowatt-hour, and what quantity does it measure?", [source]
            )
            assert len(instructions) == 2
            assert "character-for-character" in instructions[0]
            assert "bounded repair attempt" in instructions[1]
            assert repaired.value.supporting_evidence_ids == ["S1"]
            assert repaired.value.fact_assessments[0].evidence[0].quote == exact_quote
            assert exact_quote in excerpt
            assert not responses
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_structured_output_uses_only_loopback_and_reports_usage() -> None:
    async def exercise() -> None:
        settings = ollama_settings()
        provider = OllamaLLM(settings)
        expected = (await MockLLM().plan("Explain evidence provenance")).value

        async def respond(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "127.0.0.1" and request.url.port == 11434
            payload = json.loads(request.content)
            assert request.url.path == "/api/chat"
            assert payload["model"] == "qwen3:8b"
            assert payload["format"] == ResearchPlan.model_json_schema()
            assert payload["stream"] is False
            assert payload["think"] is False
            assert payload["options"]["num_ctx"] == settings.ollama_context_tokens
            return httpx.Response(
                200,
                json={
                    "message": {"content": expected.model_dump_json()},
                    "prompt_eval_count": 43,
                    "eval_count": 27,
                    "eval_duration": 900_000_000,
                    "load_duration": 100_000_000,
                    "done_reason": "stop",
                },
            )

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url=settings.ollama_url,
            trust_env=False,
        )
        try:
            result = await provider.plan("Explain evidence provenance")
            assert result.value == expected
            assert result.input_tokens == 43 and result.output_tokens == 27
            assert result.inference_ms == 900 and result.model_load_ms == 100
            assert result.tokens_per_second == 30
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_sufficiency_derives_evidence_ids_from_verified_quotes() -> None:
    async def exercise() -> None:
        settings = ollama_settings()
        provider = OllamaLLM(settings)
        excerpt = "The reservoir holds 12 million litres."
        source = EvidenceSource(
            source_id="S1",
            session_id=uuid4(),
            source_type="document",
            title="Reservoir facts",
            url="",
            retrieved_at=datetime.now(UTC),
            excerpt=excerpt,
            content_sha256="a" * 64,
            search_query="reservoir capacity",
        )
        decision = EvidenceSufficiencyDecision(
            question_id="Q1",
            status="INSUFFICIENT",
            supporting_evidence_ids=[],
            missing_information=["reservoir capacity"],
            explanation=(
                "The passage states the reservoir capacity. The summary fields are inconsistent."
            ),
            fact_assessments=[
                FactAssessment(
                    fact="Reservoir capacity is 12 million litres.",
                    entity="reservoir",
                    property="capacity",
                    value="12 million",
                    unit="litres",
                    time_period="",
                    scope="",
                    negation="",
                    status="SUPPORTED",
                    evidence=[EvidenceQuote(source_id="S1", quote=excerpt)],
                )
            ],
        )

        async def respond(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "message": {"content": decision.model_dump_json()},
                    "prompt_eval_count": 10,
                    "eval_count": 20,
                    "done_reason": "stop",
                },
            )

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url=settings.ollama_url,
            trust_env=False,
        )
        try:
            result = await provider.assess_sufficiency(
                "Q1", "What is the reservoir capacity?", [source]
            )
            assert result.value.status == "SUFFICIENT"
            assert result.value.missing_information == []
            assert result.value.supporting_evidence_ids == ["S1"]
            assert result.value.fact_assessments[0].evidence[0].quote == excerpt
            assert "derived as SUFFICIENT" in result.value.explanation
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_invalid_structured_output_gets_only_budgeted_retry() -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=1)
        provider = OllamaLLM(settings)
        count = 0

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            return httpx.Response(200, json={"message": {"content": "not json"}})

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url=settings.ollama_url
        )
        budget = RunBudget(settings)
        try:
            with pytest.raises(ResearchFailure, match="invalid_json"):
                await budget.invoke(lambda: provider.plan("Explain evidence provenance"), "llm")
            assert count == 2
            assert budget.usage.llm_calls == 2
            assert budget.usage.reserved_tokens == 0
            assert budget.usage.reserved_llm_cost_usd == 0
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_distinguishes_schema_truncation_and_context_failures() -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=0)
        provider = OllamaLLM(settings)
        responses = [
            httpx.Response(
                200,
                json={
                    "message": {"content": '{"objective":"valid json but incomplete"}'},
                    "done_reason": "stop",
                },
            ),
            httpx.Response(
                200,
                json={
                    "message": {"content": '{"objective":"Valid", "scope":"x", "subquestions":[]}'},
                    "done_reason": "length",
                },
            ),
        ]
        requests = 0

        async def respond(request: httpx.Request) -> httpx.Response:
            nonlocal requests
            requests += 1
            return responses.pop(0)

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url=settings.ollama_url
        )
        try:
            with pytest.raises(InvalidProviderOutput, match="schema_mismatch"):
                await provider.plan("Explain evidence provenance")
            with pytest.raises(ResearchFailure, match="output_truncated"):
                await provider.plan("Explain evidence provenance")
            with pytest.raises(ResearchFailure, match="context_length_exceeded"):
                await provider.plan("x" * (settings.max_context_chars + 1))
            assert requests == 2  # The local context guard rejects before HTTP.
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_http_failure_logs_safe_status_without_response_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=0)
        provider = OllamaLLM(settings)

        async def respond(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "127.0.0.1"
            return httpx.Response(500, text="private source text must not be logged")

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(respond), base_url=settings.ollama_url
        )
        try:
            with (
                caplog.at_level("WARNING", logger="researchforge.ollama"),
                pytest.raises(TransientProviderError, match="provider_http_error"),
            ):
                await provider.plan("Explain evidence provenance")
            record = next(item for item in caplog.records if item.message == "ollama_http_error")
            assert record.__dict__["provider_stage"] == "ResearchPlan"
            assert record.__dict__["model_id"] == "qwen3:8b"
            assert record.__dict__["http_status"] == 500
            assert record.__dict__["provider_category"] == "provider_transient"
            assert record.__dict__["duration_ms"] >= 0
            assert "private source text" not in record.getMessage()
            assert "private source text" not in caplog.text
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_ollama_connection_failure_is_distinct_from_missing_model() -> None:
    async def exercise() -> None:
        settings = ollama_settings(provider_retries=0)
        provider = OllamaLLM(settings)

        async def disconnected(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("private connection detail", request=request)

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(disconnected), base_url=settings.ollama_url
        )
        try:
            with pytest.raises(ResearchFailure, match="provider_connection_failed"):
                await provider.plan("Explain evidence provenance")
        finally:
            await provider.close()

        provider = OllamaLLM(settings)

        async def missing_model(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, text="private model detail")

        provider.client = httpx.AsyncClient(
            transport=httpx.MockTransport(missing_model), base_url=settings.ollama_url
        )
        try:
            with pytest.raises(ResearchFailure, match="model_unavailable"):
                await provider.plan("Explain evidence provenance")
        finally:
            await provider.close()

    asyncio.run(exercise())


def test_wikipedia_search_is_opt_in_bounded_and_deduplicates_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        settings = ollama_settings(
            search_provider="wikipedia",
            free_search_enabled=True,
            public_search_contact="mailto:research@example.invalid",
        )
        provider = WikipediaSearch(settings)

        async def wikipedia_response(
            url: str,
            headers: dict[str, str] | None = None,
            redirects: int = 0,
        ) -> tuple[str, bytes, str]:
            if "w/api.php" in url:
                return (
                    "https://en.wikipedia.org/w/api.php",
                    json.dumps(
                        {
                            "query": {
                                "search": [
                                    {"title": "Solar power"},
                                    {"title": "Solar power"},
                                    {"title": "Photovoltaics"},
                                ]
                            }
                        }
                    ).encode(),
                    "application/json",
                )
            return (
                url,
                b"<html><body><p>Solar power is generated from sunlight. "
                b"This fixture passes source validation.</p></body></html>",
                "text/html",
            )

        monkeypatch.setattr(provider, "MIN_INTERVAL_SECONDS", 0)
        mocked = AsyncMock(side_effect=wikipedia_response)
        monkeypatch.setattr(provider.http, "get", mocked)
        hits = await provider.search("solar panels")
        assert [item.title for item in hits] == ["Solar power", "Photovoltaics"]
        assert all(item.url.startswith("https://en.wikipedia.org/wiki/") for item in hits)
        assert "format=json" in mocked.call_args.args[0]
        assert "mailto:research@example.invalid" in mocked.call_args.args[1]["User-Agent"]
        assert "srlimit=5" in mocked.call_args.args[0]
        assert mocked.call_args.kwargs["redirects"] == 0
        fetched = await provider.fetch(hits[0].url)
        assert fetched.url == hits[0].url
        assert "generated from sunlight" in fetched.text
        page_call = mocked.call_args_list[1]
        assert "mailto:research@example.invalid" in page_call.args[1]["User-Agent"]
        assert page_call.kwargs["redirects"] == 0

    asyncio.run(exercise())


def test_local_provider_rejects_non_loopback_endpoints_and_unapproved_search() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        ollama_settings(ollama_url="http://0.0.0.0:11434")
    with pytest.raises(ValidationError, match="FREE_SEARCH_ENABLED"):
        ollama_settings(search_provider="wikipedia")


@pytest.mark.parametrize(
    ("contact", "expected"),
    [
        ("example@gmail.com", "mailto:example@gmail.com"),
        ("mailto:example@gmail.com", "mailto:example@gmail.com"),
        ("https://example.org/contact", "https://example.org/contact"),
    ],
)
def test_wikipedia_contact_accepts_and_normalizes_supported_inputs(
    contact: str, expected: str
) -> None:
    settings = Settings(_env_file=None, public_search_contact=contact)
    assert settings.public_search_contact == expected


@pytest.mark.parametrize(
    "contact",
    [
        "mailto:not-an-email",
        "http://contact.example.org",
        "https://user:password@example.org/contact",
        "mailto:person@example.org\r\nX-Injected: yes",
    ],
)
def test_wikipedia_contact_requires_safe_https_url_or_mailto(contact: str) -> None:
    with pytest.raises(ValidationError, match="Public search contact"):
        Settings(
            _env_file=None,
            llm_provider="ollama",
            search_provider="wikipedia",
            free_search_enabled=True,
            public_search_contact=contact,
        )


@pytest.mark.parametrize("contact", ["not-an-email", "person@localhost", "http://example.org"])
def test_wikipedia_contact_errors_are_helpful_without_echoing_input(contact: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, public_search_contact=contact)
    message = str(error.value)
    assert "Enter an email address" in message
    assert contact not in message


def test_live_cost_budget_blocks_before_provider_dispatch() -> None:
    async def exercise() -> None:
        settings = hosted_settings().model_copy(update={"max_estimated_cost_usd": 0.001})
        budget = RunBudget(settings)
        dispatched = False

        async def operation() -> str:
            nonlocal dispatched
            dispatched = True
            return "unexpected"

        with pytest.raises(ResearchFailure, match="budget_exceeded"):
            await budget.invoke(operation, "llm")
        assert not dispatched
        assert budget.usage.llm_calls == 0

    asyncio.run(exercise())


def test_live_search_unit_cost_is_reserved_before_dispatch() -> None:
    async def exercise() -> None:
        settings = hosted_settings().model_copy(update={"max_estimated_cost_usd": 0.001})
        budget = RunBudget(settings)
        dispatched = False

        async def operation() -> str:
            nonlocal dispatched
            dispatched = True
            return "result"

        with pytest.raises(ResearchFailure, match="budget_exceeded"):
            await budget.invoke(operation, "search")
        assert not dispatched
        assert budget.usage.search_calls == 1

    asyncio.run(exercise())


def test_failed_live_attempt_reserves_cost_before_any_retry() -> None:
    async def exercise() -> None:
        settings = hosted_settings().model_copy(
            update={"provider_retries": 1, "max_estimated_cost_usd": 0.01}
        )
        budget = RunBudget(settings)
        calls = 0

        async def operation() -> str:
            nonlocal calls
            calls += 1
            raise TransientProviderError("provider_transient")

        with pytest.raises(ResearchFailure, match="budget_exceeded"):
            await budget.invoke(operation, "llm")
        assert calls == 1
        assert budget.usage.reserved_llm_cost_usd == pytest.approx(0.007)

    asyncio.run(exercise())


def test_provider_status_errors_are_classified_without_exposing_response_bodies() -> None:
    rate_limit = APIStatusError(
        "rate limited",
        response=httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com")),
        body={"secret": "never-log"},
    )
    with pytest.raises(ResearchFailure, match="provider_transient"):
        OpenAILLM.translate_error(rate_limit)
    denied = APIStatusError(
        "unauthorized",
        response=httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com")),
        body={"secret": "never-log"},
    )
    with pytest.raises(ResearchFailure, match="provider_error") as error:
        OpenAILLM.translate_error(denied)
    assert "never-log" not in str(error.value)


def test_brave_empty_and_malformed_responses_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        provider = BraveSearch(hosted_settings())
        mocked = AsyncMock(
            return_value=(
                "https://api.search.brave.com/",
                b'{"web":{"results":[]}}',
                "application/json",
            )
        )
        monkeypatch.setattr(provider.http, "get", mocked)
        assert await provider.search("nothing found") == []
        mocked.return_value = ("https://api.search.brave.com/", b"not-json", "application/json")
        with pytest.raises(ResearchFailure, match="provider_error"):
            await provider.search("malformed result")

    asyncio.run(exercise())


def test_unexpected_token_usage_fails_closed() -> None:
    budget = RunBudget(hosted_settings())
    settings = budget.settings.model_copy(update={"max_total_tokens": 1000})
    budget = RunBudget(settings)
    plan = ResearchPlan.model_construct(objective="test", scope="test", subquestions=[])
    with pytest.raises(ResearchFailure, match="budget_exceeded"):
        account_usage(budget, LLMResult(plan, input_tokens=1001, output_tokens=0))
