import asyncio
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, delete, insert, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import ResearchRun, ResearchSession, VerificationRun
from app.documents.service import Documents
from app.main import create_app
from app.research.budget import RunBudget
from app.research.errors import ResearchFailure
from app.research.providers import (
    FetchedPage,
    LLMResult,
    MockLLM,
    MockSearch,
    SearchHit,
    SearchProvider,
)
from app.research.schemas import (
    DraftReport,
    EvidenceSource,
    GroundedStatement,
    ResearchPlan,
    Subquestion,
)
from app.research.sufficiency import (
    EvidenceQuote,
    EvidenceSufficiencyDecision,
    EvidenceSufficiencyResult,
    FactAssessment,
)
from app.research.supervisor import ResearchSupervisor
from app.research.workflow import Checkpoint, ResearchState, run_workflow
from tests.conftest import migration_config

pytestmark = pytest.mark.database
BASE = "/api/v1/research/sessions"
SYNTHETIC_WEB_URL = "https://fixtures.example.invalid/kilowatt-hour"
SYNTHETIC_WEB_EXCERPT = (
    "Synthetic training note: The workshop's energy ledger uses kilowatt-hours (kWh) "
    "to record total electrical energy consumed during each test cycle. "
    "This example was written for testing and does not quote an external source."
)
SYNTHETIC_WEB_SENTENCE = (
    "Synthetic training note: The workshop's energy ledger uses kilowatt-hours (kWh) "
    "to record total electrical energy consumed during each test cycle."
)
JUNIPER_CAPACITY = "The Juniper battery has a rated capacity of 12 kWh."


class SyntheticWebFixture:
    """Serve original synthetic evidence; this fixture never performs HTTP."""

    def __init__(self) -> None:
        self.search_calls = 0
        self.fetch_calls = 0

    async def search(self, query: str) -> list[SearchHit]:
        self.search_calls += 1
        return [SearchHit("Synthetic kilowatt-hour note", SYNTHETIC_WEB_URL)]

    async def fetch(self, url: str) -> FetchedPage:
        assert url == SYNTHETIC_WEB_URL
        self.fetch_calls += 1
        return FetchedPage(url, SYNTHETIC_WEB_EXCERPT)


class GroundedFixtureLLM(MockLLM):
    """Deterministic structured outputs for persistence and provenance integration tests."""

    async def plan(self, question: str) -> LLMResult[ResearchPlan]:
        combined = question.startswith("Mode: combined;")
        subquestions = (
            [
                Subquestion(
                    question="What rated capacity does the Juniper document state?",
                    search_query="Juniper battery rated capacity",
                ),
                Subquestion(
                    question="What quantity does a kilowatt-hour measure?",
                    search_query="kilowatt-hour energy definition",
                ),
            ]
            if combined
            else [
                Subquestion(
                    question="What kind of quantity does a kilowatt-hour measure?",
                    search_query="kilowatt-hour energy definition",
                )
            ]
        )
        return LLMResult(
            ResearchPlan(
                objective="Answer the question using saved evidence.",
                scope="Use only the selected document and synthetic web test evidence.",
                subquestions=subquestions,
            )
        )

    async def assess_sufficiency(
        self, question_id: str, question: str, sources: list[EvidenceSource]
    ) -> LLMResult[EvidenceSufficiencyDecision]:
        source = next(
            item
            for item in sources
            if item.source_type == ("document" if "rated capacity" in question else "web")
        )
        is_document = source.source_type == "document"
        quote = JUNIPER_CAPACITY if is_document else SYNTHETIC_WEB_SENTENCE
        fact = (
            FactAssessment(
                fact="The Juniper battery has a rated capacity of 12 kWh.",
                entity="Juniper battery",
                property="rated capacity",
                value="12",
                unit="kWh",
                time_period="",
                scope="",
                negation="",
                status="SUPPORTED",
                evidence=[EvidenceQuote(source_id=source.source_id, quote=quote)],
            )
            if is_document
            else FactAssessment(
                fact="A kilowatt-hour measures energy.",
                entity="kilowatt-hour",
                property="measured quantity",
                value="energy",
                unit="",
                time_period="",
                scope="",
                negation="",
                status="SUPPORTED",
                evidence=[EvidenceQuote(source_id=source.source_id, quote=quote)],
            )
        )
        return LLMResult(
            EvidenceSufficiencyDecision(
                question_id=question_id,
                status="SUFFICIENT",
                supporting_evidence_ids=[source.source_id],
                missing_information=[],
                explanation="The saved passage directly states the requested fact.",
                fact_assessments=[fact],
            )
        )

    async def write_grounded(
        self,
        question: str,
        plan: ResearchPlan,
        sources: list[EvidenceSource],
        sufficiency: list[EvidenceSufficiencyResult],
    ) -> LLMResult[DraftReport]:
        statements = []
        for source in sources:
            if source.source_type == "document" and JUNIPER_CAPACITY in source.excerpt:
                statements.append(
                    GroundedStatement(
                        text=JUNIPER_CAPACITY,
                        source_ids=[source.source_id],
                    )
                )
            elif source.source_type == "web" and SYNTHETIC_WEB_SENTENCE in source.excerpt:
                statements.append(
                    GroundedStatement(
                        text=SYNTHETIC_WEB_SENTENCE,
                        source_ids=[source.source_id],
                    )
                )
        if not statements:
            raise AssertionError("The fixture writer did not receive both required evidence facts")
        return LLMResult(
            DraftReport(
                title="Deterministic offline evidence report",
                executive_summary=statements,
                objective=plan.objective,
                findings=statements,
                comparisons=[],
                limitations=["This report is generated by a deterministic offline test fixture."],
                conclusion=statements[-1],
            )
        )


def settings(url: URL) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(url.render_as_string(hide_password=False)),
        llm_provider="mock",
        search_provider="mock",
    )


@pytest.fixture
def research_client(postgres_url: URL) -> Iterator[TestClient]:
    engine = create_engine(postgres_url)
    with engine.begin() as db:
        db.execute(delete(ResearchSession))
    engine.dispose()
    with TestClient(create_app(settings(postgres_url))) as client:
        yield client


def save(client: TestClient, mode: str = "web") -> str:
    response = client.post(
        BASE, json={"question": "How does source-grounded research work?", "mode": mode}
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def wait_finished(client: TestClient, session_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response: dict[str, object] = client.get(f"{BASE}/{session_id}").json()
        if response["status"] in {"completed", "failed", "cancelled"}:
            return response
        time.sleep(0.02)
    pytest.fail("Research did not reach a terminal state")


def test_mock_run_persists_plan_sources_report_and_metrics(
    research_client: TestClient, postgres_url: URL
) -> None:
    session_id = save(research_client)
    response = research_client.post(f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"})
    assert response.status_code == 202
    assert wait_finished(research_client, session_id)["status"] == "completed"
    run = research_client.get(f"{BASE}/{session_id}/run").json()
    assert run["stage"] == "completed" and run["execution_mode"] == "mock"
    assert len(run["plan"]["subquestions"]) == 2 and len(run["sources"]) == 2
    assert all(
        source["session_id"] == session_id and source["source_type"] == "mock"
        for source in run["sources"]
    )
    assert run["metrics"]["llm_calls"] == 7 and run["metrics"]["tool_calls"] == 5
    assert run["metrics"]["estimated_cost_usd"] == 0
    exported = research_client.get(f"{BASE}/{session_id}/report")
    assert exported.status_code == 200 and "MOCK DEMONSTRATION" in exported.text
    assert "text/markdown" in exported.headers["content-type"]
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 409
    )
    engine = create_engine(postgres_url)
    with engine.connect() as db:
        assert len(db.execute(select(ResearchRun.id)).all()) == 1
    engine.dispose()


def test_async_persistence_inspection_awaits_session_get(
    research_client: TestClient, postgres_url: URL
) -> None:
    session_id = save(research_client)
    response = research_client.post(f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"})
    assert response.status_code == 202
    assert wait_finished(research_client, session_id)["status"] == "completed"

    async def inspect_persisted_run() -> None:
        async_url = postgres_url.set(drivername="postgresql+psycopg")
        engine = create_async_engine(async_url, hide_parameters=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                session = await db.get(ResearchSession, UUID(session_id))
                run = await db.scalar(
                    select(ResearchRun).where(ResearchRun.session_id == UUID(session_id))
                )
                verification = await db.scalar(
                    select(VerificationRun).where(VerificationRun.session_id == UUID(session_id))
                )
                assert session is not None and session.status == "completed"
                assert run is not None and run.stage == "completed"
                assert run.execution_mode == "mock" and run.report_markdown
                assert verification is not None and verification.status == "completed"
        finally:
            await engine.dispose()

    asyncio.run(inspect_persisted_run())


def test_external_request_budget_failure_is_persisted_and_visible(
    research_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ExhaustedSearch:
        def __init__(self, budget: RunBudget) -> None:
            self.budget = budget

        async def search(self, query: str) -> list[SearchHit]:
            await self.budget.reserve_external_request("search")
            # Simulate an additional request inside this run; it must fail before HTTP.
            await self.budget.reserve_external_request("search")
            return []

        async def fetch(self, url: str) -> FetchedPage:
            raise AssertionError("fetch must not run after the budget error")

    monkeypatch.setattr(
        "app.research.supervisor.providers",
        lambda config, budget=None: (MockLLM(), ExhaustedSearch(budget)),
    )
    session_id = save(research_client)
    response = research_client.post(f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"})
    assert response.status_code == 202
    session = wait_finished(research_client, session_id)
    assert session["status"] == "failed"
    assert isinstance(session["error_message"], str)
    assert "external request limit" in session["error_message"]
    run = research_client.get(f"{BASE}/{session_id}/run").json()
    assert run["error_code"] == "request_budget_exceeded"
    assert run["metrics"]["external_request_attempts"] == 1
    assert run["metrics"]["external_search_attempts"] == 1


def test_disabled_execution_never_changes_pending_state(db_client: TestClient) -> None:
    session_id = save(db_client)
    assert (
        db_client.post(f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}).status_code
        == 503
    )
    assert db_client.get(f"{BASE}/{session_id}").json()["status"] == "pending"


def test_document_execution_never_changes_pending_state(research_client: TestClient) -> None:
    for mode in ("documents",):
        session_id = save(research_client, mode)
        assert (
            research_client.post(
                f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
            ).status_code
            == 422
        )
        assert research_client.get(f"{BASE}/{session_id}").json()["status"] == "pending"


def test_empty_evidence_fails_without_completed_report(
    research_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenSearch(MockSearch):
        async def search(self, query: str) -> list[SearchHit]:
            raise ResearchFailure("provider_error")

    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda config, budget=None: (MockLLM(), BrokenSearch())
    )
    session_id = save(research_client)
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    assert wait_finished(research_client, session_id)["status"] == "failed"
    run = research_client.get(f"{BASE}/{session_id}/run").json()
    assert run["plan"] is not None and run["error_code"] == "no_evidence"
    assert run["report_markdown"] is None and run["warnings"]
    assert research_client.get(f"{BASE}/{session_id}/report").status_code == 404


@pytest.mark.parametrize("mode", ["web", "combined"])
def test_synthetic_web_workflows_persist_provenance_and_verified_reports(
    research_client: TestClient,
    mode: str,
    postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise synthetic web evidence through the real API, graph, verifier, and PostgreSQL."""
    from app.research.report import escape

    if mode == "combined":
        pdf = Path(__file__).parent / "fixtures" / "phase7-local-demo.pdf"
        uploaded = research_client.post(
            "/api/v1/documents/upload",
            headers={
                "Content-Type": "application/octet-stream",
                "X-Filename": "phase7-local-demo.pdf",
            },
            content=pdf.read_bytes(),
        )
        assert uploaded.status_code == 202, uploaded.text
        document_id = str(uploaded.json()["id"])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            document = research_client.get(f"/api/v1/documents/{document_id}").json()
            if document["status"] in {"ready", "failed"}:
                break
            time.sleep(0.02)
        assert document["status"] == "ready", document
        document_ids = [document_id]
        question = (
            "According to my Juniper battery document, what is its rated capacity, "
            "and what does a kilowatt-hour measure?"
        )
    else:
        document_ids = []
        question = "What is a kilowatt-hour, and what quantity does it measure?"

    app = cast(FastAPI, research_client.app)
    supervisor = cast(ResearchSupervisor, app.state.research)
    supervisor.settings = supervisor.settings.model_copy(
        update={
            "search_provider": "disabled",
            "max_sources": 3,
            "max_search_queries": 1,
            "max_tool_calls": 3,
            "max_verification_iterations": 0,
            "max_followup_searches": 0,
            "provider_retries": 0,
            "max_external_retries": 0,
        }
    )
    search = SyntheticWebFixture()
    monkeypatch.setattr(
        "app.research.supervisor.providers",
        lambda config, budget=None: (GroundedFixtureLLM(), search),
    )

    stages: list[str] = []
    original_run_workflow = run_workflow

    async def trace_stages(
        session_id: UUID,
        prompt: str,
        config: Settings,
        llm: MockLLM,
        search_provider: SearchProvider,
        budget: RunBudget,
        checkpoint: Checkpoint,
        run_mode: str = "web",
        documents: Documents | None = None,
        selected_ids: list[UUID] | None = None,
    ) -> ResearchState:
        async def record(stage: str, state: ResearchState) -> None:
            stages.append(stage)
            await checkpoint(stage, state)

        return await original_run_workflow(
            session_id,
            prompt,
            config,
            llm,
            search_provider,
            budget,
            record,
            run_mode,
            documents,
            selected_ids,
        )

    monkeypatch.setattr("app.research.supervisor.run_workflow", trace_stages)
    session_response = research_client.post(
        BASE,
        json={"question": question, "mode": mode, "document_ids": document_ids},
    )
    assert session_response.status_code == 201, session_response.text
    session_id = str(session_response.json()["id"])
    submitted = research_client.post(
        f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
    )
    assert submitted.status_code == 202, submitted.text
    assert wait_finished(research_client, session_id)["status"] == "completed"

    run = research_client.get(f"{BASE}/{session_id}/run").json()
    verification_response = research_client.get(f"{BASE}/{session_id}/verification")
    verification = verification_response.json()
    report_response = research_client.get(f"{BASE}/{session_id}/report")
    assert report_response.status_code == 200
    assert run["execution_mode"] == "mock" and run["stage"] == "completed"
    assert run["session_id"] == session_id
    assert all(source["session_id"] == session_id for source in run["sources"])
    expected_stages = [
        "planning",
        "collected",
        "evidence_assessed",
        "written",
        "claims_assessed",
        "verification_complete",
    ]
    assert [stage for stage in stages if stage in expected_stages] == expected_stages
    assert search.search_calls == 1 and search.fetch_calls == 1
    assert run["metrics"]["external_request_attempts"] == 0

    source_by_id = {source["source_id"]: source for source in run["sources"]}
    web_source = next(source for source in run["sources"] if source["source_type"] == "web")
    assert web_source["title"] == "Synthetic kilowatt-hour note"
    assert web_source["url"] == SYNTHETIC_WEB_URL
    assert "Synthetic training note:" in web_source["excerpt"]
    assert SYNTHETIC_WEB_SENTENCE in web_source["excerpt"]
    if mode == "combined":
        document_source = next(
            source
            for source in run["sources"]
            if source["source_type"] == "document" and source["page"] == 1
        )
        assert document_source["title"] == "phase7-local-demo.pdf"
        assert JUNIPER_CAPACITY in document_source["excerpt"]
        assert document_source["document_id"] == document_id
        assert escape(JUNIPER_CAPACITY) in run["report_markdown"]
    assert escape(SYNTHETIC_WEB_SENTENCE) in run["report_markdown"]
    engine = create_engine(postgres_url)
    with engine.connect() as db:
        report = db.execute(
            select(ResearchRun.report_json).where(ResearchRun.session_id == UUID(session_id))
        ).scalar_one()
    engine.dispose()
    assert report is not None
    report_data = report
    executive_summary = cast(list[dict[str, object]], report_data["executive_summary"])
    findings = cast(list[dict[str, object]], report_data["findings"])
    claim_sources = [
        source_id
        for statement in [*executive_summary, *findings]
        for source_id in cast(list[str], statement.get("source_ids", []))
    ]
    assert source_by_id and all(source_id in source_by_id for source_id in claim_sources)
    assert verification_response.status_code == 200
    assert verification["status"] == "completed"
    assert verification["artifacts"]["execution_mode"] == "mock"
    assert verification["artifacts"]["evidence_sufficiency"]
    assert all(
        item["status"] == "SUFFICIENT" for item in verification["artifacts"]["evidence_sufficiency"]
    )
    assert all(
        verdict["status"] == "SUPPORTED" for verdict in verification["artifacts"]["verdicts"]
    ), verification["artifacts"]["verdicts"]


def test_running_cancellation_cannot_be_overwritten_by_completion(
    research_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowLLM(MockLLM):
        async def plan(self, question: str) -> LLMResult[ResearchPlan]:
            await asyncio.sleep(10)
            return await super().plan(question)

    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda config, budget=None: (SlowLLM(), MockSearch())
    )
    session_id = save(research_client)
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 409
    )
    assert research_client.post(f"{BASE}/{session_id}/cancel", json={}).status_code == 200
    assert wait_finished(research_client, session_id)["status"] == "cancelled"
    assert research_client.get(f"{BASE}/{session_id}/run").json()["stage"] == "cancelled"
    assert research_client.get(f"{BASE}/{session_id}/report").status_code == 404


def test_unknown_execution_and_mode_mismatch(research_client: TestClient) -> None:
    assert (
        research_client.post(
            f"{BASE}/{uuid4()}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 404
    )
    session_id = save(research_client)
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "live"}
        ).status_code
        == 409
    )
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"model": "arbitrary"}
        ).status_code
        == 422
    )


def test_overall_deadline_marks_run_failed(
    research_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SlowLLM(MockLLM):
        async def plan(self, question: str) -> LLMResult[ResearchPlan]:
            await asyncio.sleep(10)
            return await super().plan(question)

    supervisor = cast(ResearchSupervisor, cast(FastAPI, research_client.app).state.research)
    supervisor.settings = supervisor.settings.model_copy(update={"run_timeout_seconds": 0.02})
    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda config, budget=None: (SlowLLM(), MockSearch())
    )
    session_id = save(research_client)
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    assert wait_finished(research_client, session_id)["status"] == "failed"
    run = research_client.get(f"{BASE}/{session_id}/run").json()
    assert run["error_code"] == "run_timeout" and run["report_markdown"] is None


def test_second_worker_cannot_interrupt_or_execute_active_run(
    research_client: TestClient,
    postgres_url: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowLLM(MockLLM):
        async def plan(self, question: str) -> LLMResult[ResearchPlan]:
            await asyncio.sleep(10)
            return await super().plan(question)

    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda config, budget=None: (SlowLLM(), MockSearch())
    )
    session_id = save(research_client)
    assert (
        research_client.post(
            f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    with TestClient(create_app(settings(postgres_url))) as second:
        assert (
            second.post(f"{BASE}/{session_id}/execute", json={"execution_mode": "mock"}).status_code
            == 503
        )
        assert second.get(f"{BASE}/{session_id}").json()["status"] == "running"
    assert research_client.post(f"{BASE}/{session_id}/cancel", json={}).status_code == 200


def test_restart_marks_stranded_run_failed_without_replay(postgres_url: URL) -> None:
    engine = create_engine(postgres_url)
    session_id = uuid4()
    with engine.begin() as db:
        db.execute(delete(ResearchSession))
        db.execute(
            insert(ResearchSession).values(
                id=session_id,
                workspace_id="local",
                question="Interrupted research must not be replayed",
                mode="web",
                status="running",
            )
        )
        db.execute(
            insert(ResearchRun).values(
                id=uuid4(),
                session_id=session_id,
                worker_id=str(uuid4()),
                execution_mode="mock",
                stage="planned",
                sources=[],
                warnings=[],
                investigated_queries=[],
                metrics={},
                provider_model="mock-v1",
                prompt_version="web-baseline-v1",
            )
        )
    with TestClient(create_app(settings(postgres_url))) as restarted:
        assert restarted.get(f"{BASE}/{session_id}").json()["status"] == "failed"
        assert restarted.get(f"{BASE}/{session_id}/run").json()["error_code"] == "interrupted"
    engine.dispose()


def test_phase2_migration_preserves_existing_session(postgres_url: URL) -> None:
    config = migration_config(postgres_url)
    engine = create_engine(postgres_url)
    with engine.begin() as db:
        db.execute(delete(ResearchSession))
    command.downgrade(config, "0001_sessions")
    session_id = uuid4()
    try:
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO research_sessions(id,workspace_id,question,mode,status) "
                    "VALUES (:id,'local','A Phase 1 session must survive migration',"
                    "'web','pending')"
                ),
                {"id": session_id},
            )
        command.upgrade(config, "head")
        with TestClient(create_app(settings(postgres_url))) as client:
            assert (
                client.get(f"{BASE}/{session_id}").json()["question"]
                == "A Phase 1 session must survive migration"
            )
            assert client.get("/ready").status_code == 200
        command.check(config)
    finally:
        command.upgrade(config, "head")
        engine.dispose()
