from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["researchforge-api"] = "researchforge-api"
    version: str = "0.1.0"


class PublicConfig(BaseModel):
    app_name: str = "ResearchForge AI"
    phase: int = 7
    access_mode: Literal["single-user-local"] = "single-user-local"
    research_enabled: bool = False
    uploads_enabled: bool = True
    llm_provider: Literal["disabled", "mock", "openai", "ollama"] = "disabled"
    search_provider: Literal["disabled", "mock", "brave", "wikipedia"] = "disabled"
    sessions_enabled: bool = True
    execution_mode: Literal["disabled", "mock", "local", "live"] = "disabled"
    model: str | None = None
    free_search_enabled: bool = False
    ollama_context_tokens: int = 0
    ollama_timeout_seconds: float = 0
    max_concurrent_model_requests: int = 1
    live_calls_approved: bool = False
    max_search_requests: int = 0
    max_tool_calls: int = 0
    max_llm_requests: int = 0
    max_output_tokens_per_request: int = 0
    max_total_tokens: int = 0
    max_estimated_cost_usd: float = 0
    provider_timeout_seconds: float = 0
    run_timeout_seconds: float = 0
    cost_rates_configured: bool = False
