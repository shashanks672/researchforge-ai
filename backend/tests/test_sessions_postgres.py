from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import DateTime, create_engine, insert, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import ResearchSession
from app.main import create_app
from app.schemas.sessions import SessionCreate, SessionRead
from app.services import sessions
from tests.conftest import migration_config

pytestmark = pytest.mark.database
BASE = "/api/v1/research/sessions"


@pytest.mark.parametrize("mode", ["web", "documents", "combined"])
def test_create_and_retrieve_pending_session(db_client: TestClient, mode: str) -> None:
    response = db_client.post(
        BASE, json={"question": "  Explain retrieval grounding  ", "mode": mode}
    )
    assert response.status_code == 201
    record = response.json()
    UUID(record["id"])
    assert record["question"] == "Explain retrieval grounding"
    assert record["mode"] == mode
    assert record["status"] == "pending"
    assert record["error_message"] is None
    assert datetime.fromisoformat(record["created_at"]).utcoffset() == timedelta(0)
    assert record["created_at"] == record["updated_at"]
    assert db_client.get(response.headers["location"]).json() == record


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "short"},
        {"question": " " * 20},
        {"question": "a" * 4001},
        {"question": "Explain grounding carefully", "mode": "invalid"},
        {"question": "Explain grounding carefully", "status": "completed"},
    ],
)
def test_invalid_input_is_not_persisted(db_client: TestClient, payload: dict[str, str]) -> None:
    assert db_client.post(BASE, json=payload).status_code == 422
    assert db_client.get(BASE).json()["total"] == 0


def test_history_pagination_and_deterministic_ties(
    db_client: TestClient, postgres_url: URL
) -> None:
    engine = create_engine(postgres_url)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    ids = sorted([uuid4() for _ in range(5)], reverse=True)
    with engine.begin() as connection:
        for session_id in ids:
            connection.execute(
                insert(ResearchSession).values(
                    id=session_id,
                    workspace_id="local",
                    question="Compare evidence approaches",
                    mode="web",
                    status="pending",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
    engine.dispose()
    first = db_client.get(BASE, params={"limit": 2, "offset": 0}).json()
    second = db_client.get(BASE, params={"limit": 2, "offset": 2}).json()
    last = db_client.get(BASE, params={"limit": 2, "offset": 4}).json()
    assert first["total"] == 5 and first["has_more"]
    assert [row["id"] for row in first["items"] + second["items"] + last["items"]] == [
        str(i) for i in ids
    ]
    assert not last["has_more"]
    assert db_client.get(BASE, params={"offset": 99}).json()["items"] == []
    for params in ({"limit": 0}, {"limit": 51}, {"offset": -1}, {"offset": 10001}):
        assert db_client.get(BASE, params=params).status_code == 422


def test_unknown_and_invalid_ids(db_client: TestClient) -> None:
    assert db_client.get(f"{BASE}/{uuid4()}").status_code == 404
    assert db_client.get(f"{BASE}/not-a-uuid").status_code == 422


def test_other_workspace_is_never_returned(db_client: TestClient, postgres_url: URL) -> None:
    engine = create_engine(postgres_url)
    session_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(ResearchSession).values(
                id=session_id,
                workspace_id="someone-else",
                question="Private workspace question",
                mode="web",
                status="pending",
            )
        )
    engine.dispose()
    assert db_client.get(BASE).json()["total"] == 0
    assert db_client.get(f"{BASE}/{session_id}").status_code == 404


def test_session_survives_new_application_instance(
    db_client: TestClient, postgres_url: URL
) -> None:
    record = db_client.post(BASE, json={"question": "Does this session survive restart?"}).json()
    settings = Settings(
        _env_file=None, database_url=SecretStr(postgres_url.render_as_string(hide_password=False))
    )
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f"{BASE}/{record['id']}").json() == record
        assert restarted.get("/ready").status_code == 200


def test_status_domain_in_real_database(db_client: TestClient, postgres_url: URL) -> None:
    engine = create_engine(postgres_url)
    statuses = ["pending", "running", "completed", "failed", "cancelled"]
    with engine.begin() as connection:
        for status in statuses:
            connection.execute(
                insert(ResearchSession).values(
                    id=uuid4(),
                    workspace_id="local",
                    question=f"Stored status contract: {status}",
                    mode="web",
                    status=status,
                )
            )
    engine.dispose()
    assert {row["status"] for row in db_client.get(BASE).json()["items"]} == set(statuses)


def test_migration_round_trip_preserves_unrelated_tables(postgres_url: URL) -> None:
    config = migration_config(postgres_url)
    engine = create_engine(postgres_url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE phase1_unrelated (value text)"))
        connection.execute(text("INSERT INTO phase1_unrelated VALUES ('keep me')"))
    try:
        command.downgrade(config, "base")
        assert "research_sessions" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT value FROM phase1_unrelated")) == "keep me"
        with TestClient(
            create_app(
                Settings(
                    _env_file=None,
                    database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
                )
            )
        ) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/ready").status_code == 503
        command.upgrade(config, "head")
        command.check(config)
        columns = {
            column["name"]: column for column in inspect(engine).get_columns("research_sessions")
        }
        for name in ("created_at", "updated_at"):
            column_type = columns[name]["type"]
            assert isinstance(column_type, DateTime) and column_type.timezone
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_failed_write_rolls_back_and_next_request_recovers(
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_after_flush(db: AsyncSession, payload: SessionCreate) -> SessionRead:
        db.add(ResearchSession(workspace_id="local", question=payload.question, mode="web"))
        await db.flush()
        raise OperationalError("injected write failure", {}, RuntimeError("private driver detail"))

    with monkeypatch.context() as patch:
        patch.setattr(sessions, "create_session", fail_after_flush)
        response = db_client.post(BASE, json={"question": "This transaction should roll back"})
        assert response.status_code == 503
        assert "private driver detail" not in response.text
    assert db_client.get(BASE).json()["total"] == 0
    assert (
        db_client.post(BASE, json={"question": "This transaction should persist"}).status_code
        == 201
    )


def test_database_itself_rejects_invalid_status(postgres_url: URL) -> None:
    engine = create_engine(postgres_url)
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                insert(ResearchSession).values(
                    id=uuid4(),
                    workspace_id="local",
                    question="Database enforces valid statuses",
                    mode="web",
                    status="imaginary",
                )
            )
    finally:
        engine.dispose()
