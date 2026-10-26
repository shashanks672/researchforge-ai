from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(
        create_app(Settings(_env_file=None, app_env="test", database_url=None))
    ) as connection:
        yield connection


def test_health_and_request_headers(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "researchforge-api", "version": "0.1.0"}
    UUID(response.headers["x-request-id"])
    assert response.headers["x-content-type-options"] == "nosniff"


def test_public_config_reports_uploads_and_inactive_research(client: TestClient) -> None:
    assert client.get("/api/v1/config").json() == {
        "app_name": "ResearchForge AI",
        "phase": 7,
        "access_mode": "single-user-local",
        "research_enabled": False,
        "uploads_enabled": True,
        "llm_provider": "disabled",
        "search_provider": "disabled",
        "free_search_enabled": False,
        "sessions_enabled": True,
        "execution_mode": "disabled",
        "model": None,
        "live_calls_approved": False,
        "max_search_requests": 6,
        "max_tool_calls": 18,
        "max_llm_requests": 16,
        "max_output_tokens_per_request": 1500,
        "max_total_tokens": 24000,
        "max_estimated_cost_usd": 0.25,
        "provider_timeout_seconds": 15.0,
        "ollama_context_tokens": 0,
        "max_concurrent_model_requests": 1,
        "run_timeout_seconds": 120.0,
        "ollama_timeout_seconds": 0.0,
        "cost_rates_configured": False,
    }


def test_untrusted_host_rejected(client: TestClient) -> None:
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400


def test_only_explicit_local_origin_allowed(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = client.get("/health", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://example.com",
        "http://localhost:3000/path",
        "http://localhost:3000?x=1",
        "http://user@localhost:3000",
    ],
)
def test_nonlocal_cors_configuration_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cors_origins=[origin])


def test_production_mode_is_not_yet_supported() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"app_env": "production"})


def test_search_budget_can_be_limited_to_one_request() -> None:
    settings = Settings(
        _env_file=None,
        max_search_queries=1,
        max_followup_searches=0,
        provider_retries=0,
    )
    assert settings.max_search_queries + settings.max_followup_searches == 1
    assert settings.provider_retries == 0


def test_no_pretend_research_endpoint(client: TestClient) -> None:
    response = client.post("/api/v1/research", json={"question": "Why use evidence?"})
    assert response.status_code == 404
