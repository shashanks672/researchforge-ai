import socket
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.schemas.sessions import SessionCreate, SessionStatus


@pytest.mark.parametrize("question", ["", " " * 20, "short", "a" * 4001])
def test_session_question_validation(question: str) -> None:
    with pytest.raises(ValidationError):
        SessionCreate(question=question)


def test_clients_cannot_set_status_or_workspace() -> None:
    for field in ("status", "workspace_id", "id"):
        with pytest.raises(ValidationError):
            SessionCreate.model_validate(
                {"question": "Explain evidence grounding", field: "completed"}
            )
    with pytest.raises(ValidationError):
        SessionCreate.model_validate({"question": "Explain evidence grounding", "mode": "shell"})
    assert {value.value for value in SessionStatus} == {
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
    }


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///test.db",
        "postgresql+psycopg://user@remote.example/db",
        "postgresql+psycopg://user@localhost/db?host=remote.example",
    ],
)
def test_remote_or_non_postgres_config_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=SecretStr(url))


def test_database_not_configured_is_honest_and_health_survives() -> None:
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/config").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.get("/api/v1/research/sessions").status_code == 503
        assert (
            client.post(
                "/api/v1/research/sessions", json={"question": "Explain grounded evidence"}
            ).status_code
            == 503
        )


def test_database_exception_never_exposes_driver_details() -> None:
    app = create_app(Settings(_env_file=None, database_url=None))

    async def unavailable() -> AsyncIterator[AsyncSession]:
        raise OperationalError("SELECT secret_password", {}, Exception("database-password"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = unavailable
    with TestClient(app) as client:
        response = client.get("/api/v1/research/sessions")
        assert response.status_code == 503
        assert "database-password" not in response.text
        assert "secret_password" not in response.text


def test_mutations_reject_cross_site_origins_and_non_json() -> None:
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        response = client.post(
            "/api/v1/research/sessions",
            json={"question": "Explain provenance tracking"},
            headers={"Origin": "https://attacker.example"},
        )
        assert response.status_code == 403
        assert (
            client.post("/api/v1/research/sessions", data={"question": "untrusted"}).status_code
            == 415
        )


def test_database_url_repr_redacts_password() -> None:
    settings = Settings(
        _env_file=None, database_url=SecretStr("postgresql+psycopg://u:sensitive@localhost/db")
    )
    assert "sensitive" not in repr(settings)


def test_real_connection_failure_returns_503_without_breaking_health() -> None:
    with socket.socket() as unused_port:
        unused_port.bind(("127.0.0.1", 0))
        port = unused_port.getsockname()[1]
        # The port is reserved by this socket but has no listening database.
        settings = Settings(
            _env_file=None,
            database_url=SecretStr(f"postgresql+psycopg://test:test@127.0.0.1:{port}/unavailable"),
        )
        with TestClient(create_app(settings)) as client:
            assert client.get("/ready").status_code == 503
            assert client.get("/api/v1/research/sessions").status_code == 503
            assert client.get("/health").status_code == 200
