"""Focused tests for safe PostgreSQL test selection."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "researchforge_test_database_runner", ROOT / "scripts/test_database.py"
)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_runner_uses_full_suite_when_no_collection_path_is_given() -> None:
    assert RUNNER.pytest_collection_arguments(["-q", "-m", "database"]) == ["backend/tests"]


def test_runner_does_not_add_full_suite_to_exact_test_selector() -> None:
    selector = (
        "backend/tests/test_execution_postgres.py::"
        "test_async_persistence_inspection_awaits_session_get"
    )
    assert RUNNER.pytest_collection_arguments([selector]) == []


def test_runner_does_not_add_full_suite_to_explicit_file_path() -> None:
    assert RUNNER.pytest_collection_arguments(["backend/tests/test_system.py"]) == []
