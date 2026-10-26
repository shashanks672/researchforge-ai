"""Verify durable storage across actual Uvicorn process termination and restart."""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from sqlalchemy.engine import URL

pytestmark = pytest.mark.database


def request_json(url: str, payload: dict[str, str] | None = None) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=2) as response:
        result: dict[str, object] = json.load(response)
        return result


@contextmanager
def api_process(url: URL) -> Iterator[str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment["RF_DATABASE_URL"] = url.render_as_string(hide_password=False)
    environment["RF_APP_ENV"] = "test"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    origin = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if request_json(f"{origin}/ready")["status"] == "ready":
                    break
            except (URLError, TimeoutError, ConnectionError):
                if process.poll() is not None:
                    pytest.fail("Owned Uvicorn test process exited before readiness")
                time.sleep(0.05)
        else:
            pytest.fail("Owned Uvicorn test process did not become ready")
        yield origin
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_session_survives_real_process_restart(postgres_url: URL) -> None:
    with api_process(postgres_url) as origin:
        record = request_json(
            f"{origin}/api/v1/research/sessions",
            {
                "question": "Does the record survive stopping the API process?",
                "mode": "web",
            },
        )
    # The first server is now stopped; the second has a new engine and connection pool.
    with api_process(postgres_url) as origin:
        recovered = request_json(f"{origin}/api/v1/research/sessions/{record['id']}")
        assert recovered == record
        assert recovered["status"] == "pending"
