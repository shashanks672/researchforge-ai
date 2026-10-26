"""Run PostgreSQL tests in a new disposable database; never reset the development DB."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings


def main() -> int:
    configured = get_settings().database_url
    if configured is None:
        raise SystemExit("Configure RF_DATABASE_URL and start PostgreSQL first")
    base = make_url(configured.get_secret_value())
    # PostgreSQL's SQL identifier escaping is separate from value parameterization.
    name = f"rf_test_{uuid4().hex}"
    with psycopg.connect(
        host=base.host,
        port=base.port or 5432,
        user=base.username,
        password=base.password,
        dbname=base.database,
        autocommit=True,
        connect_timeout=3,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        print(f"Created disposable database {name}", flush=True)
        temporary = tempfile.mkdtemp(prefix="researchforge-test-")
        namespace = f"rf_test_{uuid4().hex}"
        try:
            environment = os.environ.copy()
            environment["RF_STORAGE_ROOT"] = temporary
            environment["RF_EMBEDDING_PROVIDER"] = "fake"
            environment["RF_QDRANT_NAMESPACE"] = namespace
            # Offline tests never inherit enabled live providers from the caller.
            environment["RF_LLM_PROVIDER"] = "disabled"
            environment["RF_SEARCH_PROVIDER"] = "disabled"
            environment["RF_LIVE_CALLS_APPROVED"] = "false"
            environment["LANGSMITH_TRACING"] = "false"
            environment["LANGCHAIN_TRACING_V2"] = "false"
            environment["RF_TEST_DATABASE_URL"] = base.set(
                database=name
            ).render_as_string(hide_password=False)
            arguments = sys.argv[1:]
            if arguments and arguments[0] == "--browser":
                environment["RF_LLM_PROVIDER"] = "mock"
                environment["RF_SEARCH_PROVIDER"] = "mock"
                environment["RF_LIVE_CALLS_APPROVED"] = "false"
                environment["RF_DATABASE_URL"] = environment["RF_TEST_DATABASE_URL"]
                environment["NEXT_TELEMETRY_DISABLED"] = "1"
                subprocess.run(
                    [
                        str(ROOT / "backend/.venv/bin/alembic"),
                        "-c",
                        "backend/alembic.ini",
                        "upgrade",
                        "head",
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=True,
                )
                return subprocess.run(
                    ["npm", "run", "test:e2e", "--", *arguments[1:]],
                    cwd=ROOT / "frontend",
                    env=environment,
                    check=False,
                ).returncode
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-c",
                    "backend/pyproject.toml",
                    *pytest_collection_arguments(arguments),
                    *arguments,
                ],
                cwd=ROOT,
                env=environment,
                check=False,
            )
            return result.returncode
        finally:
            shutil.rmtree(temporary)
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:6333/collections", timeout=3
                ) as response:
                    collections = json.load(response)["result"]["collections"]
                for collection in collections:
                    if collection["name"].startswith(namespace + "_"):
                        request = urllib.request.Request(
                            f"http://127.0.0.1:6333/collections/{collection['name']}",
                            method="DELETE",
                        )
                        with urllib.request.urlopen(request, timeout=3):
                            pass
            except OSError:
                pass
            # Only the unique database created above is removed; never an existing database.
            admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )
            print(f"Removed disposable database {name}", flush=True)


def pytest_collection_arguments(arguments: list[str]) -> list[str]:
    """Use the full suite by default, but don't broaden an explicit selector."""
    has_explicit_path = any(
        argument.endswith(".py")
        or "::" in argument
        or argument.startswith("backend/tests/")
        for argument in arguments
    )
    return [] if has_explicit_path else ["backend/tests"]


if __name__ == "__main__":
    raise SystemExit(main())
