import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import ResearchRun, ResearchSession
from app.db.session import DATABASE_UNAVAILABLE, SCHEMA_REVISION, get_db
from app.schemas.system import HealthResponse, PublicConfig

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Process liveness only; database readiness will be separate in Phase 1."""
    return HealthResponse()


@router.get("/api/v1/config", response_model=PublicConfig, tags=["system"])
def public_config(request: Request) -> PublicConfig:
    """Expose capabilities, never serialize server settings or credentials."""
    settings: Settings = request.app.state.settings
    return PublicConfig(
        llm_provider=settings.llm_provider,
        search_provider=settings.search_provider,
        research_enabled=settings.execution_mode != "disabled",
        execution_mode=settings.execution_mode,
        model=settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_model,
        free_search_enabled=settings.free_search_enabled,
        ollama_context_tokens=(
            settings.ollama_context_tokens if settings.llm_provider == "ollama" else 0
        ),
        ollama_timeout_seconds=(
            settings.ollama_timeout_seconds if settings.llm_provider == "ollama" else 0
        ),
        live_calls_approved=settings.live_calls_approved,
        max_search_requests=settings.max_search_queries + settings.max_followup_searches,
        max_tool_calls=settings.max_tool_calls,
        max_llm_requests=settings.max_llm_calls,
        max_output_tokens_per_request=settings.llm_max_output_tokens,
        max_total_tokens=settings.max_total_tokens,
        max_estimated_cost_usd=settings.max_estimated_cost_usd,
        provider_timeout_seconds=settings.provider_timeout_seconds,
        run_timeout_seconds=settings.run_timeout_seconds,
        cost_rates_configured=all(
            value is not None
            for value in (
                settings.input_usd_per_million,
                settings.output_usd_per_million,
                settings.search_usd_per_request,
            )
        ),
    )


@router.get("/ready", tags=["system"])
async def ready(
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> dict[str, str]:
    """Check connectivity, expected migration revision and queryable session columns."""
    try:
        async with asyncio.timeout(3):
            revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != SCHEMA_REVISION:
                raise HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE)
            await db.execute(select(ResearchSession).limit(0))
            await db.execute(select(ResearchRun).limit(0))
    except (SQLAlchemyError, TimeoutError) as from_error:
        raise HTTPException(status_code=503, detail=DATABASE_UNAVAILABLE) from from_error
    return {"status": "ready", "database": "ok", "schema_revision": SCHEMA_REVISION}
