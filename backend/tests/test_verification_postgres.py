import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import URL

from app.db.models import Document, ResearchSession, VerificationRun
from app.research.providers import LLMResult, MockLLM, MockSearch
from app.research.schemas import EvidenceSource
from app.research.verification_schemas import Assessment, Claim
from tests.test_documents_postgres import documents_client, ready, upload
from tests.test_execution_postgres import BASE, research_client, save, wait_finished

pytestmark = pytest.mark.database
# Imported fixtures deliberately retain their original setup/teardown.
__all__ = ["documents_client", "research_client"]


def test_verification_persisted_with_original_and_revised_drafts(
    research_client: TestClient, postgres_url: URL
) -> None:
    sid = save(research_client)
    assert (
        research_client.post(f"{BASE}/{sid}/execute", json={"execution_mode": "mock"}).status_code
        == 202
    )
    assert wait_finished(research_client, sid)["status"] == "completed"
    stored = research_client.get(f"{BASE}/{sid}/verification").json()
    assert stored["status"] == "completed" and stored["original_markdown"]
    assert len(stored["drafts"]) == 2 and len(stored["history"]) == 2
    assert "Unresolved support" not in stored["original_markdown"]
    assert stored["artifacts"]["execution_mode"] == "mock"
    assert {v["status"] for v in stored["artifacts"]["verdicts"]} <= {
        "INSUFFICIENT_EVIDENCE",
        "NOT_EVALUATED",
    }
    assert len(stored["artifacts"]["evidence_sufficiency"]) == 2
    assert {item["status"] for item in stored["artifacts"]["evidence_sufficiency"]} == {
        "INSUFFICIENT"
    }
    engine = create_engine(postgres_url)
    with engine.begin() as db:
        row = db.execute(
            select(VerificationRun.status).where(VerificationRun.session_id == sid)
        ).scalar_one()
        assert row == "completed"
        db.execute(
            update(ResearchSession).where(ResearchSession.id == sid).values(workspace_id="other")
        )
    assert research_client.get(f"{BASE}/{sid}/verification").status_code == 404
    with engine.begin() as db:
        db.execute(
            update(ResearchSession).where(ResearchSession.id == sid).values(workspace_id="local")
        )
    engine.dispose()


def test_mandatory_verification_failure_preserves_draft_not_success(
    research_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken(MockLLM):
        async def assess_claims(
            self, claims: list[Claim], sources: list[EvidenceSource]
        ) -> LLMResult[Assessment]:
            raise RuntimeError("private-provider-error")

    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda settings, budget=None: (Broken(), MockSearch())
    )
    sid = save(research_client)
    research_client.post(f"{BASE}/{sid}/execute", json={"execution_mode": "mock"})
    assert wait_finished(research_client, sid)["status"] == "failed"
    stored = research_client.get(f"{BASE}/{sid}/verification").json()
    assert stored["status"] == "failed" and stored["error_code"] == "verification_failed"
    assert stored["original_markdown"] and stored["drafts"]
    assert research_client.get(f"{BASE}/{sid}/report").status_code == 404
    assert "private-provider" not in str(stored)


def test_real_document_conflicts_surface_and_no_web_calls(documents_client: TestClient) -> None:
    first = upload(documents_client, "capacity-a.txt", b"The Juniper battery stores 20 kWh.")
    ready(documents_client, first)
    second = upload(documents_client, "capacity-b.txt", b"The Juniper battery stores 10 kWh.")
    ready(documents_client, second)
    client = documents_client
    sid = client.post(
        BASE,
        json={
            "question": "What does the Juniper battery store?",
            "mode": "documents",
            "document_ids": [first, second],
        },
    ).json()["id"]
    client.post(f"{BASE}/{sid}/execute", json={"execution_mode": "mock"})
    assert wait_finished(client, sid)["status"] == "completed"
    data = client.get(f"{BASE}/{sid}/verification").json()
    assert data["artifacts"]["contradictions"]
    assert all(v["status"] != "SUPPORTED" for v in data["artifacts"]["verdicts"])
    run = client.get(f"{BASE}/{sid}/run").json()
    assert len(run["sources"]) == 2 and run["metrics"]["search_calls"] == 0
    assert data["artifacts"]["iteration"] == 1


def test_stale_document_evidence_cannot_finalize(
    documents_client: TestClient, postgres_url: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    did = upload(documents_client)
    ready(documents_client, did)

    class Stale(MockLLM):
        async def assess_claims(
            self, claims: list[Claim], sources: list[EvidenceSource]
        ) -> LLMResult[Assessment]:
            engine = create_engine(postgres_url)
            with engine.begin() as db:
                db.execute(update(Document).where(Document.id == did).values(status="failed"))
            engine.dispose()
            return await super().assess_claims(claims, sources)

    monkeypatch.setattr(
        "app.research.supervisor.providers", lambda settings, budget=None: (Stale(), MockSearch())
    )
    sid = documents_client.post(
        BASE,
        json={
            "question": "What is Juniper battery capacity?",
            "mode": "documents",
            "document_ids": [did],
        },
    ).json()["id"]
    documents_client.post(f"{BASE}/{sid}/execute", json={"execution_mode": "mock"})
    assert wait_finished(documents_client, sid)["status"] == "failed"
    assert documents_client.get(f"{BASE}/{sid}/verification").json()["status"] == "failed"
