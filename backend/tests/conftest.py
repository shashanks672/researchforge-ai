import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.db.models import ResearchSession
from app.main import create_app


def migration_config(url: URL) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    return config


@pytest.fixture(scope="session")
def postgres_url() -> URL:
    url = os.environ.get("RF_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Run scripts/test_database.py for isolated real-PostgreSQL tests")
    parsed = make_url(url)
    if not parsed.database or not parsed.database.startswith("rf_test_"):
        pytest.fail("Database tests only operate on freshly created rf_test_* databases")
    command.upgrade(migration_config(parsed), "head")
    return parsed


@pytest.fixture
def db_client(postgres_url: URL) -> Iterator[TestClient]:
    engine = create_engine(postgres_url, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(delete(ResearchSession))
    engine.dispose()
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
        )
    )
    with TestClient(app) as client:
        yield client
