import asyncio
from uuid import UUID

import pytest

from app.core.config import Settings
from app.research.budget import GlobalRequestBudget, RunBudget
from app.research.errors import ProviderHTTPError, ResearchFailure, TransientProviderError
from app.research.providers import FetchedPage, MockLLM, SearchHit, WikipediaSearch
from app.research.workflow import ResearchState, run_workflow


def wikipedia_settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "llm_provider": "ollama",
            "search_provider": "wikipedia",
            "free_search_enabled": True,
            "public_search_contact": "mailto:offline@example.invalid",
            "max_external_requests_per_run": 3,
            "max_external_search_requests": 1,
            "max_article_fetch_attempts": 2,
            "provider_retries": 0,
            **overrides,
        }
    )


def test_failed_fetches_consume_budget_and_stop_before_next_http_attempt() -> None:
    async def exercise() -> None:
        settings = wikipedia_settings()
        budget = RunBudget(settings)
        provider = WikipediaSearch(settings, budget)
        provider.MIN_INTERVAL_SECONDS = 0
        calls = 0

        async def fail(*args: object, **kwargs: object) -> tuple[str, bytes, str]:
            nonlocal calls
            calls += 1
            raise ResearchFailure("http_unavailable")

        provider.http.get = fail  # type: ignore[method-assign]
        for _ in range(2):
            with pytest.raises(ResearchFailure, match="http_unavailable"):
                await provider.fetch("https://en.wikipedia.org/wiki/Test")
        with pytest.raises(ResearchFailure, match="request_budget_exceeded"):
            await provider.fetch("https://en.wikipedia.org/wiki/Test")

        assert calls == 2
        assert budget.usage.article_fetch_attempts == 2
        assert budget.usage.external_request_attempts == 2

    asyncio.run(exercise())


def test_workflow_stops_after_two_failed_article_fetches() -> None:
    class FailingSearch:
        def __init__(self, budget: RunBudget) -> None:
            self.budget = budget
            self.fetches = 0
            self.http_attempts = 0

        async def search(self, query: str) -> list[SearchHit]:
            await self.budget.reserve_external_request("search")
            return [
                SearchHit(f"Fixture {index}", f"https://example.org/paper-{index}")
                for index in range(5)
            ]

        async def fetch(self, url: str) -> FetchedPage:
            self.fetches += 1
            await self.budget.reserve_external_request("fetch")
            self.http_attempts += 1
            raise ResearchFailure("http_unavailable")

    async def exercise() -> None:
        settings = wikipedia_settings(max_sources=3)
        budget = RunBudget(settings)
        search = FailingSearch(budget)

        async def save(stage: str, state: ResearchState) -> None:
            pass

        with pytest.raises(ResearchFailure, match="request_budget_exceeded"):
            await run_workflow(
                UUID(int=1),
                "What does the evidence say about the fixture topic?",
                settings,
                MockLLM(),
                search,
                budget,
                save,
            )
        assert search.fetches == 3  # Third provider call is rejected before HTTP starts.
        assert search.http_attempts == 2
        assert budget.usage.external_search_attempts == 1
        assert budget.usage.article_fetch_attempts == 2
        assert budget.usage.external_request_attempts == 3

    asyncio.run(exercise())


def test_concurrent_attempts_cannot_race_past_per_run_fetch_limit() -> None:
    async def exercise() -> None:
        settings = wikipedia_settings()
        budget = RunBudget(settings)
        provider = WikipediaSearch(settings, budget)
        provider.MIN_INTERVAL_SECONDS = 0
        calls = 0

        async def fail(*args: object, **kwargs: object) -> tuple[str, bytes, str]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            raise ResearchFailure("http_unavailable")

        provider.http.get = fail  # type: ignore[method-assign]
        outcomes = await asyncio.gather(
            *(provider.fetch("https://en.wikipedia.org/wiki/Test") for _ in range(12)),
            return_exceptions=True,
        )
        assert calls == 2
        assert sum(isinstance(item, ResearchFailure) for item in outcomes) == 12
        assert budget.usage.article_fetch_attempts == 2
        assert budget.usage.external_request_attempts == 2

    asyncio.run(exercise())


def test_external_retries_stay_zero_when_local_model_retries_are_enabled() -> None:
    async def exercise() -> None:
        settings = wikipedia_settings(provider_retries=1, max_external_retries=0)
        budget = RunBudget(settings)
        provider = WikipediaSearch(settings, budget)
        provider.MIN_INTERVAL_SECONDS = 0
        calls = 0

        async def fail(*args: object, **kwargs: object) -> tuple[str, bytes, str]:
            nonlocal calls
            calls += 1
            raise TransientProviderError("http_transient")

        provider.http.get = fail  # type: ignore[method-assign]
        with pytest.raises(ResearchFailure, match="provider_transient"):
            await budget.invoke(
                lambda: provider.fetch("https://en.wikipedia.org/wiki/Test"), "fetch"
            )
        assert calls == 1
        assert budget.usage.article_fetch_attempts == 1

    asyncio.run(exercise())


def test_failed_or_cancelled_llm_calls_release_reserved_usage() -> None:
    async def exercise() -> None:
        settings = Settings.model_validate(
            {
                "llm_provider": "ollama",
                "search_provider": "disabled",
                "provider_retries": 0,
            }
        )
        budget = RunBudget(settings)

        async def fail() -> None:
            raise TransientProviderError("fixture_failure")

        with pytest.raises(ResearchFailure, match="provider_transient"):
            await budget.invoke(fail, "llm")
        assert budget.usage.reserved_tokens == 0
        assert budget.usage.reserved_llm_cost_usd == 0
        assert budget.usage.usage_complete is False

        http_budget = RunBudget(settings)

        async def http_500() -> None:
            raise ProviderHTTPError(500)

        with pytest.raises(ResearchFailure, match="provider_http_error"):
            await http_budget.invoke(http_500, "llm")
        assert http_budget.usage.reserved_tokens == 0
        assert http_budget.usage.llm_calls == 1

        async def block() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(budget.invoke(block, "llm"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert budget.usage.reserved_tokens == 0
        assert budget.usage.reserved_llm_cost_usd == 0
        assert budget.usage.usage_complete is False

    asyncio.run(exercise())


def test_llm_call_cap_is_checked_before_reserving_resources() -> None:
    async def exercise() -> None:
        settings = Settings.model_validate(
            {
                "llm_provider": "ollama",
                "search_provider": "disabled",
                "provider_retries": 0,
            }
        )
        budget = RunBudget(settings)
        budget.usage.llm_calls = settings.max_llm_calls
        called = False

        async def operation() -> None:
            nonlocal called
            called = True

        with pytest.raises(ResearchFailure, match="budget_exceeded"):
            await budget.invoke(operation, "llm")
        assert called is False
        assert budget.usage.llm_calls == settings.max_llm_calls
        assert budget.usage.reserved_tokens == 0
        assert budget.usage.reserved_llm_cost_usd == 0

    asyncio.run(exercise())


def test_global_budget_is_shared_across_runs_and_counts_failed_requests() -> None:
    async def exercise() -> None:
        settings = wikipedia_settings()
        global_budget = GlobalRequestBudget(6)
        budgets = [RunBudget(settings, global_budget) for _ in range(2)]
        providers = [WikipediaSearch(settings, budget) for budget in budgets]
        for provider in providers:
            provider.MIN_INTERVAL_SECONDS = 0

            async def fail(*args: object, **kwargs: object) -> tuple[str, bytes, str]:
                raise ResearchFailure("http_unavailable")

            provider.http.get = fail  # type: ignore[method-assign]

        for provider in providers:
            with pytest.raises(ResearchFailure, match="http_unavailable"):
                await provider.search("offline test")
            for _ in range(2):
                with pytest.raises(ResearchFailure, match="http_unavailable"):
                    await provider.fetch("https://en.wikipedia.org/wiki/Test")
        with pytest.raises(ResearchFailure, match="request_budget_exceeded"):
            await budgets[0].reserve_external_request("fetch")
        assert global_budget.attempts == 6
        assert [budget.usage.external_request_attempts for budget in budgets] == [3, 3]

    asyncio.run(exercise())


def test_wikipedia_extracted_text_is_capped_and_truncation_reported() -> None:
    async def exercise() -> None:
        settings = wikipedia_settings(max_article_text_chars=1000)
        budget = RunBudget(settings)
        provider = WikipediaSearch(settings, budget)
        provider.MIN_INTERVAL_SECONDS = 0

        async def response(*args: object, **kwargs: object) -> tuple[str, bytes, str]:
            return (
                "https://en.wikipedia.org/wiki/Test",
                b"<html><body><p>" + b"A useful passage. " * 100 + b"</p></body></html>",
                "text/html",
            )

        provider.http.get = response  # type: ignore[method-assign]
        fetched = await provider.fetch("https://en.wikipedia.org/wiki/Test")
        assert len(fetched.text) == 1000
        assert fetched.truncated is True
        assert budget.usage.article_fetch_attempts == 1

    asyncio.run(exercise())
