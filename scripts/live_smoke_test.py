#!/usr/bin/env python3
"""Local-only preflight and separately approved, budget-bounded live smoke test."""

from __future__ import annotations

import argparse
import json
import sys
import time
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pydantic import ValidationError

if TYPE_CHECKING:
    from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_QUESTION = "Compare two established approaches to retrieval-augmented generation using publicly available sources."


def local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("The API target must be an HTTP loopback address")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError(
            "The API target cannot contain credentials, query, or fragment"
        )
    return value.rstrip("/")


def request_json(
    url: str, method: str = "GET", payload: dict[str, object] | None = None
) -> dict[str, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urlopen(request, timeout=4) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise TypeError("Unexpected local API response")
    return value


def cost_ceiling_estimate(settings: Settings) -> float | None:
    prices = (
        settings.input_usd_per_million,
        settings.output_usd_per_million,
        settings.search_usd_per_request,
    )
    if any(price is None for price in prices):
        return None
    input_price, output_price, search_price = (
        float(price) for price in prices if price is not None
    )
    # Conservative token-cost bound uses the highest supplied per-token rate times the
    # total token cap. Provider billing and operator-supplied rates can still differ.
    return (
        settings.max_total_tokens * max(input_price, output_price) / 1_000_000
        + (settings.max_search_queries + settings.max_followup_searches) * search_price
    )


def diagnostics(
    settings: Settings, base: str
) -> tuple[dict[str, object], dict[str, object] | None]:
    checks: dict[str, object] = {
        "target": base,
        "target_loopback_only": True,
        "llm_provider": settings.llm_provider,
        "search_provider": settings.search_provider,
        "execution_mode": settings.execution_mode,
        "openai_key_present": settings.openai_api_key is not None,
        "brave_key_present": settings.brave_api_key is not None,
        "live_calls_approved": settings.live_calls_approved,
        "model": settings.llm_model,
        "max_output_tokens_per_request": settings.llm_max_output_tokens,
        "max_search_requests": settings.max_search_queries
        + settings.max_followup_searches,
        "max_tool_calls": settings.max_tool_calls,
        "max_llm_requests": settings.max_llm_calls,
        "max_total_tokens": settings.max_total_tokens,
        "max_estimated_cost_usd": settings.max_estimated_cost_usd,
        "estimated_worst_case_cost_usd": cost_ceiling_estimate(settings),
        "provider_timeout_seconds": settings.provider_timeout_seconds,
        "run_timeout_seconds": settings.run_timeout_seconds,
        "cost_rates_configured": cost_ceiling_estimate(settings) is not None,
        "one_research_task_limit": True,
        "credential_values_printed": False,
        "provider_requests_made": False,
    }
    server = None
    try:
        ready = request_json(f"{base}/ready")
        config = request_json(f"{base}/api/v1/config")
        server = {"ready": ready.get("status") == "ready", "config": config}
        checks["local_persistence_ready"] = server["ready"]
        checks["local_server_execution_mode"] = config.get("execution_mode")
        expected = {
            "execution_mode": settings.execution_mode,
            "llm_provider": settings.llm_provider,
            "search_provider": settings.search_provider,
            "model": settings.llm_model,
            "live_calls_approved": settings.live_calls_approved,
            "max_search_requests": settings.max_search_queries
            + settings.max_followup_searches,
            "max_tool_calls": settings.max_tool_calls,
            "max_llm_requests": settings.max_llm_calls,
            "max_output_tokens_per_request": settings.llm_max_output_tokens,
            "max_total_tokens": settings.max_total_tokens,
            "max_estimated_cost_usd": settings.max_estimated_cost_usd,
            "provider_timeout_seconds": settings.provider_timeout_seconds,
            "run_timeout_seconds": settings.run_timeout_seconds,
            "cost_rates_configured": cost_ceiling_estimate(settings) is not None,
        }
        checks["server_config_matches_local_settings"] = all(
            config.get(key) == value for key, value in expected.items()
        )
    except (URLError, HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        checks["local_persistence_ready"] = False
        checks["local_server_execution_mode"] = None
        checks["server_config_matches_local_settings"] = False
    checks["ready"] = all(
        [
            settings.execution_mode == "live",
            settings.llm_provider == "openai",
            settings.search_provider == "brave",
            settings.openai_api_key is not None,
            settings.brave_api_key is not None,
            settings.live_calls_approved,
            cost_ceiling_estimate(settings) is not None,
            (cost_ceiling_estimate(settings) or float("inf"))
            <= settings.max_estimated_cost_usd,
            checks["local_persistence_ready"],
            checks["server_config_matches_local_settings"],
        ]
    )
    return checks, server


def execute(
    settings: Settings, base: str, question: str, max_cost: float, wall_timeout: int
) -> int:
    checks, server = diagnostics(settings, base)
    if not checks["ready"]:
        print(json.dumps({"status": "blocked", "preflight": checks}, indent=2))
        return 2
    assert server is not None
    if max_cost != settings.max_estimated_cost_usd:
        print(
            "Blocked: the command ceiling must exactly match the server's configured per-run cap."
        )
        return 2
    if wall_timeout > settings.run_timeout_seconds:
        print(
            "Blocked: requested wall timeout exceeds the server's configured run timeout."
        )
        return 2

    try:
        session = request_json(
            f"{base}/api/v1/research/sessions",
            "POST",
            {"question": question, "mode": "web", "document_ids": []},
        )
        session_id = str(session["id"])
        request_json(
            f"{base}/api/v1/research/sessions/{session_id}/execute",
            "POST",
            {"execution_mode": "live"},
        )
        deadline = time.monotonic() + wall_timeout
        while time.monotonic() < deadline:
            run = request_json(f"{base}/api/v1/research/sessions/{session_id}/run")
            stage = run.get("stage")
            if stage in {"completed", "failed", "cancelled"}:
                metrics = run.get("metrics", {})
                print(
                    json.dumps(
                        {
                            "status": stage,
                            "session_id": session_id,
                            "stage": stage,
                            "metrics": metrics,
                            "error_code": run.get("error_code"),
                        },
                        indent=2,
                    )
                )
                return 0 if stage == "completed" else 1
            time.sleep(2)
        try:
            request_json(
                f"{base}/api/v1/research/sessions/{session_id}/cancel", "POST", {}
            )
        except (URLError, HTTPError, TimeoutError, ValueError):
            pass
        print(
            json.dumps(
                {
                    "status": "timeout",
                    "session_id": session_id,
                    "cancellation_requested": True,
                },
                indent=2,
            )
        )
        return 1
    except (URLError, HTTPError, TimeoutError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {"status": "failed", "failure_type": type(exc).__name__}, indent=2
            )
        )
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect configuration; no provider calls",
    )
    actions.add_argument(
        "--execute", action="store_true", help="Run one explicitly approved live task"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--approve-live-spend", action="store_true")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--wall-timeout-seconds", type=int, default=120)
    args = parser.parse_args()
    try:
        base = local_url(args.base_url)
        settings_class = cast(Any, import_module("app.core.config").Settings)
        settings = settings_class()
    except (ValueError, ValidationError) as exc:
        print(
            json.dumps(
                {"status": "invalid_configuration", "reason": str(exc)}, indent=2
            )
        )
        return 2

    if args.dry_run:
        checks, _ = diagnostics(settings, base)
        print(
            json.dumps(
                {
                    "status": "ready" if checks["ready"] else "blocked",
                    "preflight": checks,
                },
                indent=2,
            )
        )
        return 0 if checks["ready"] else 2
    if not args.approve_live_spend or args.max_cost_usd is None:
        print("Blocked: --execute requires --approve-live-spend and --max-cost-usd.")
        return 2
    if not 10 <= len(args.question) <= 500 or args.wall_timeout_seconds < 5:
        print(
            "Blocked: question must be 10–500 characters and timeout at least 5 seconds."
        )
        return 2
    return execute(
        settings, base, args.question, args.max_cost_usd, args.wall_timeout_seconds
    )


if __name__ == "__main__":
    raise SystemExit(main())
