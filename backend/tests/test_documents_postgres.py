import time
from collections.abc import Iterator
from urllib.parse import quote
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, delete, update
from sqlalchemy.engine import URL

from app.core.config import Settings
from app.db.models import Document
from app.main import create_app

pytestmark = pytest.mark.database
BASE = "/api/v1/documents"
TEXT = (
    "Solar pilot handbook. The Juniper battery has a storage capacity of 20 kWh. "
    "The pilot operates in Bristol. Inspection is required every 30 days."
)


@pytest.fixture
def documents_client(postgres_url: URL) -> Iterator[TestClient]:
    config = Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
        llm_provider="mock",
        search_provider="mock",
        embedding_provider="fake",
    )
    with TestClient(create_app(config)) as client:
        yield client
        for d in client.get(BASE).json():
            client.post(f"{BASE}/{d['id']}/delete", json={})
    engine = create_engine(postgres_url)
    with engine.begin() as db:
        db.execute(delete(Document))
    engine.dispose()


def upload(client: TestClient, name: str = "pilot.txt", text: bytes = TEXT.encode()) -> str:
    response = client.post(
        f"{BASE}/upload",
        headers={"Content-Type": "application/octet-stream", "X-Filename": quote(name)},
        content=text,
    )
    assert response.status_code == 202, response.text
    return str(response.json()["id"])


def ready(client: TestClient, did: str, status: str = "ready") -> dict[str, object]:
    for _ in range(250):
        response = client.get(f"{BASE}/{did}")
        data = response.json()
        if data["status"] in {"ready", "failed"}:
            assert data["status"] == status, data
            return dict(data)
        time.sleep(0.05)
    pytest.fail("Document ingestion did not finish")


def test_real_qdrant_upload_retrieval_filters_reindex_delete(documents_client: TestClient) -> None:
    client = documents_client
    did = upload(client)
    document = ready(client, did)
    assert document["index_status"] == "indexed" and document["chunk_count"] == 1
    for method in ("semantic", "bm25", "hybrid"):
        response = client.post(
            f"{BASE}/retrieve",
            json={"question": "Juniper battery capacity", "document_ids": [did], "method": method},
        )
        assert response.status_code == 200, response.text
        assert response.json()[0]["document_id"] == did
        assert "20 kWh" in response.json()[0]["text"]
    assert (
        client.post(
            f"{BASE}/retrieve", json={"question": "Juniper battery", "document_ids": [str(uuid4())]}
        ).json()
        == []
    )
    assert (
        client.post(
            f"{BASE}/upload",
            headers={"Content-Type": "application/octet-stream", "X-Filename": "duplicate.txt"},
            content=TEXT,
        ).status_code
        == 409
    )
    assert client.post(f"{BASE}/{did}/reindex", json={}).status_code == 202
    assert ready(client, did)["chunk_count"] == 1
    assert client.post(f"{BASE}/{did}/delete", json={}).json()["status"] == "deleted"
    assert client.get(f"{BASE}/{did}").status_code == 404
    assert (
        client.post(
            f"{BASE}/retrieve", json={"question": "Juniper battery", "document_ids": [did]}
        ).json()
        == []
    )
    # Idempotent content checksum does not prevent intentional re-upload after deletion.
    new = upload(client)
    ready(client, new)


@pytest.mark.parametrize(
    "name,body,status",
    [
        ("../outside.txt", b"bad", 422),
        ("image.pdf", b"not PDF", 422),
        ("macro.exe", b"bad", 422),
        ("empty.txt", b"", 422),
        ("huge.txt", b"x" * 5_000_001, 413),
    ],
)
def test_upload_boundaries(
    documents_client: TestClient, name: str, body: bytes, status: int
) -> None:
    assert (
        documents_client.post(
            f"{BASE}/upload",
            headers={"Content-Type": "application/octet-stream", "X-Filename": quote(name)},
            content=body,
        ).status_code
        == status
    )


def test_corrupt_pdf_is_failed_not_ready(documents_client: TestClient) -> None:
    did = upload(documents_client, "broken.pdf", b"%PDF-1.7\ncorrupted")
    result = ready(documents_client, did, "failed")
    assert result["error_code"] == "invalid_document"


def test_document_only_research_actual_passage_and_citations(documents_client: TestClient) -> None:
    client = documents_client
    did = upload(client)
    ready(client, did)
    response = client.post(
        "/api/v1/research/sessions",
        json={
            "question": "What is the Juniper battery capacity?",
            "mode": "documents",
            "document_ids": [did],
        },
    )
    sid = response.json()["id"]
    assert (
        client.post(
            f"/api/v1/research/sessions/{sid}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    for _ in range(200):
        run = client.get(f"/api/v1/research/sessions/{sid}/run").json()
        if run["stage"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert run["stage"] == "completed", run
    assert all(s["source_type"] == "document" for s in run["sources"])
    assert run["sources"][0]["document_id"] == did
    assert "20 kWh" in run["report_markdown"]
    assert "(document passage)" in run["report_markdown"]
    assert "(web source)" not in run["report_markdown"]
    assert run["metrics"]["search_calls"] == 0 and run["metrics"]["fetch_calls"] == 0
    assert "chunk" in run["report_markdown"]


def test_document_only_unanswerable_question_completes_safe_abstention(
    documents_client: TestClient,
) -> None:
    client = documents_client
    did = upload(client)
    ready(client, did)
    response = client.post(
        "/api/v1/research/sessions",
        json={
            "question": "What is the Juniper battery's annual maintenance cost?",
            "mode": "documents",
            "document_ids": [did],
        },
    )
    sid = response.json()["id"]
    assert (
        client.post(
            f"/api/v1/research/sessions/{sid}/execute", json={"execution_mode": "mock"}
        ).status_code
        == 202
    )
    for _ in range(200):
        run = client.get(f"/api/v1/research/sessions/{sid}/run").json()
        if run["stage"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert run["stage"] == "completed", run
    assert run["execution_mode"] == "mock"
    assert "Insufficient evidence" in run["report_markdown"]
    assert "$" not in run["report_markdown"] and "USD" not in run["report_markdown"]
    verification = client.get(f"/api/v1/research/sessions/{sid}/verification").json()["artifacts"]
    assert all(item["status"] == "INSUFFICIENT" for item in verification["evidence_sufficiency"])
    assert all(verdict["status"] != "SUPPORTED" for verdict in verification["verdicts"])
    assert run["metrics"]["search_calls"] == 0


def test_qdrant_failure_is_explicit(
    documents_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(*args: object, **kwargs: object) -> None:
        raise ConnectionError("private internal failure")

    monkeypatch.setattr("app.documents.vectors.VectorStore.ensure", unavailable)
    did = upload(documents_client)
    result = ready(documents_client, did, "failed")
    assert result["index_status"] == "incomplete" and result["chunk_count"] == 0
    assert "private" not in str(result)


def test_pdf_page_citation_and_workspace_filter(
    documents_client: TestClient, postgres_url: URL
) -> None:
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for text in [
        "Juniper battery inspection is every 30 days.",
        "Juniper battery capacity is 20 kWh.",
    ]:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    did = upload(documents_client, "pages.pdf", output.getvalue())
    assert ready(documents_client, did)["page_count"] == 2
    result = documents_client.post(
        f"{BASE}/retrieve", json={"question": "Juniper battery capacity", "document_ids": [did]}
    ).json()
    assert any(r["page"] == 2 and "20 kWh" in r["text"] for r in result)
    engine = create_engine(postgres_url)
    with engine.begin() as db:
        db.execute(update(Document).where(Document.id == did).values(workspace_id="other"))
    assert documents_client.get(f"{BASE}/{did}").status_code == 404
    assert (
        documents_client.post(
            f"{BASE}/retrieve", json={"question": "Juniper", "document_ids": [did]}
        ).json()
        == []
    )
    with engine.begin() as db:
        db.execute(update(Document).where(Document.id == did).values(workspace_id="local"))
    engine.dispose()


def test_small_selected_document_set_ranks_direct_capacity_passage_first(
    documents_client: TestClient,
) -> None:
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    for text in [
        "The Juniper battery has a rated capacity of 12 kWh.",
        "The installation took place in March 2025. No annual maintenance cost is listed.",
    ]:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    output = io.BytesIO()
    writer.write(output)
    document_id = upload(documents_client, "juniper-capacity.pdf", output.getvalue())
    ready(documents_client, document_id)

    response = documents_client.post(
        f"{BASE}/retrieve",
        json={
            "question": "What is the rated capacity of the Juniper battery and what does kWh mean?",
            "document_ids": [document_id],
            "k": 5,
            "method": "hybrid",
        },
    )
    assert response.status_code == 200, response.text
    passages = response.json()
    assert passages[0]["page"] == 1
    assert "12 kWh" in passages[0]["text"]
    assert passages[1]["page"] == 2
