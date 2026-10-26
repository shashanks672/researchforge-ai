import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.config import Settings
from app.research.errors import (
    InvalidProviderOutput,
    ProviderHTTPError,
    ResearchFailure,
    TransientProviderError,
)
from app.research.schemas import Usage

T = TypeVar("T")


class GlobalRequestBudget:
    """Optional process-wide cap for a bounded, multi-run acceptance window."""

    def __init__(self, limit: int | None) -> None:
        self.limit = limit
        self.attempts = 0
        self.lock = asyncio.Lock()

    async def reserve(self) -> None:
        async with self.lock:
            if self.limit is not None and self.attempts >= self.limit:
                raise ResearchFailure("request_budget_exceeded")
            self.attempts += 1


class RunBudget:
    def __init__(
        self, settings: Settings, global_requests: GlobalRequestBudget | None = None
    ) -> None:
        self.settings = settings
        self.global_requests = global_requests or GlobalRequestBudget(None)
        self.request_lock = asyncio.Lock()
        self.usage = Usage(
            estimated_cost_usd=0 if settings.execution_mode in {"mock", "local"} else None
        )
        self.pending_llm_reservations: list[tuple[int, float]] = []

    async def reserve_external_request(self, kind: str) -> None:
        """Atomically reserve immediately before each actual outbound HTTP attempt."""
        if kind not in {"search", "fetch"}:
            raise ValueError("unknown request kind")
        async with self.request_lock:
            usage = self.usage
            if usage.external_request_attempts >= self.settings.max_external_requests_per_run:
                raise ResearchFailure("request_budget_exceeded")
            if (
                kind == "search"
                and usage.external_search_attempts >= self.settings.max_external_search_requests
            ):
                raise ResearchFailure("request_budget_exceeded")
            if (
                kind == "fetch"
                and usage.article_fetch_attempts >= self.settings.max_article_fetch_attempts
            ):
                raise ResearchFailure("request_budget_exceeded")
            await self.global_requests.reserve()
            usage.external_request_attempts += 1
            if kind == "search":
                usage.external_search_attempts += 1
            else:
                usage.article_fetch_attempts += 1

    def settle_llm_usage(self) -> None:
        if self.pending_llm_reservations:
            tokens, cost = self.pending_llm_reservations.pop(0)
            self.usage.reserved_tokens -= tokens
            self.usage.reserved_llm_cost_usd -= cost

    def release_llm_reservation(self, tokens: int) -> None:
        self.usage.reserved_tokens = max(0, self.usage.reserved_tokens - tokens)

    def tool_attempt(self, kind: str) -> None:
        if self.usage.tool_calls >= self.settings.max_tool_calls:
            raise ResearchFailure("budget_exceeded")
        self.usage.tool_calls += 1
        if kind == "search":
            self.usage.search_calls += 1
        else:
            self.usage.fetch_calls += 1

    async def invoke(self, operation: Callable[[], Awaitable[T]], kind: str) -> T:
        retry_limit = (
            self.settings.provider_retries if kind == "llm" else self.settings.max_external_retries
        )
        for attempt in range(retry_limit + 1):
            token_reservation = 0
            cost_reservation = 0.0
            if kind == "llm":
                if self.usage.llm_calls >= self.settings.max_llm_calls:
                    raise ResearchFailure("budget_exceeded")
                if (
                    self.usage.estimated_cost_usd is not None
                    and self.usage.estimated_cost_usd >= self.settings.max_estimated_cost_usd
                ):
                    raise ResearchFailure("budget_exceeded")
                token_reservation = (
                    self.settings.max_context_chars // 4 + self.settings.llm_max_output_tokens
                )
                if (
                    self.usage.input_tokens
                    + self.usage.output_tokens
                    + self.usage.reserved_tokens
                    + token_reservation
                    > self.settings.max_total_tokens
                ):
                    raise ResearchFailure("budget_exceeded")
                if self.settings.execution_mode == "live":
                    assert self.settings.input_usd_per_million is not None
                    assert self.settings.output_usd_per_million is not None
                    assert self.settings.search_usd_per_request is not None
                    cost_reservation = (
                        (self.settings.max_context_chars // 4) * self.settings.input_usd_per_million
                        + self.settings.llm_max_output_tokens * self.settings.output_usd_per_million
                    ) / 1_000_000
                    current = (
                        self.usage.estimated_search_cost_usd
                        + self.usage.estimated_llm_cost_usd
                        + self.usage.reserved_llm_cost_usd
                    )
                    if current + cost_reservation > self.settings.max_estimated_cost_usd:
                        raise ResearchFailure("budget_exceeded")
                    self.usage.reserved_llm_cost_usd += cost_reservation
                self.usage.reserved_tokens += token_reservation
                self.usage.llm_calls += 1
            else:
                self.tool_attempt(kind)
                if kind == "search" and self.settings.execution_mode == "live":
                    assert self.settings.search_usd_per_request is not None
                    projected = (
                        self.usage.estimated_search_cost_usd
                        + self.usage.estimated_llm_cost_usd
                        + self.settings.search_usd_per_request
                    )
                    if projected > self.settings.max_estimated_cost_usd:
                        raise ResearchFailure("budget_exceeded")
                    self.usage.estimated_search_cost_usd += self.settings.search_usd_per_request
                    self.usage.estimated_cost_usd = projected
            try:
                async with asyncio.timeout(
                    self.settings.ollama_timeout_seconds
                    if self.settings.execution_mode == "local"
                    else self.settings.provider_timeout_seconds
                ):
                    result = await operation()
                    if kind == "llm":
                        self.pending_llm_reservations.append((token_reservation, cost_reservation))
                    return result
            except (TimeoutError, TransientProviderError) as exc:
                if kind == "llm":
                    self.usage.usage_complete = False
                    # The request may have reached a billable provider even when its
                    # response failed. Keep the cost reservation conservative, but
                    # release the token reservation because no call remains in flight.
                    self.release_llm_reservation(token_reservation)
                if attempt == retry_limit:
                    if isinstance(exc, InvalidProviderOutput):
                        candidate = str(exc)
                        code = (
                            candidate
                            if candidate
                            in {
                                "invalid_output",
                                "invalid_json",
                                "schema_mismatch",
                                "exact_quote_invalid",
                            }
                            else "invalid_output"
                        )
                    elif isinstance(exc, ProviderHTTPError):
                        code = "provider_http_error"
                    elif isinstance(exc, TimeoutError):
                        code = "provider_timeout"
                    else:
                        code = "provider_transient"
                    raise ResearchFailure(code) from exc
                await asyncio.sleep(min(0.2 * (2**attempt), 1))
            except BaseException:
                if kind == "llm":
                    self.usage.usage_complete = False
                    self.release_llm_reservation(token_reservation)
                raise
        raise AssertionError("unreachable")
