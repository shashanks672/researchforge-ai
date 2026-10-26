import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter
from typing import cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import (
    LOCAL_WORKSPACE_ID,
    Document,
    DocumentChunk,
    ResearchRun,
    ResearchSession,
    VerificationRun,
)
from app.documents.service import Documents
from app.research.budget import GlobalRequestBudget, RunBudget
from app.research.errors import MESSAGES, ResearchFailure
from app.research.providers import PROMPT_VERSION, providers
from app.research.schemas import RunRead, Usage
from app.research.workflow import ResearchState, run_workflow


def run_response(run: ResearchRun) -> RunRead:
    return RunRead.model_validate(
        {
            "id": run.id,
            "session_id": run.session_id,
            "execution_mode": run.execution_mode,
            "stage": run.stage,
            "plan": run.plan,
            "sources": run.sources,
            "investigated_queries": run.investigated_queries,
            "warnings": run.warnings,
            "report_markdown": run.report_markdown,
            "metrics": run.metrics,
            "error_code": run.error_code,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }
    )


class ResearchSupervisor:
    """One local worker, no queue. PostgreSQL guards ownership and duplicate starts."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession] | None, settings: Settings
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.global_request_budget = GlobalRequestBudget(settings.max_global_external_requests)
        self.worker_id = str(uuid4())
        self.task: asyncio.Task[None] | None = None
        self.active_session: UUID | None = None
        self.lock_connection: AsyncConnection | None = None
        self.guard = asyncio.Lock()
        self.documents: Documents | None = None

    async def open(self) -> None:
        if self.factory is None or self.lock_connection is not None:
            return
        connection: AsyncConnection | None = None
        try:
            async with asyncio.timeout(3):
                engine = cast(AsyncEngine, self.factory.kw["bind"])
                connection = await engine.connect()
                owns = await connection.scalar(text("SELECT pg_try_advisory_lock(72662002)"))
                await connection.commit()
                if not owns:
                    await connection.close()
                    return
                async with self.factory() as db, db.begin():
                    stranded = (
                        await db.scalars(
                            select(ResearchRun)
                            .join(ResearchSession)
                            .where(
                                ResearchSession.status == "running",
                                ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
                            )
                        )
                    ).all()
                    for run in stranded:
                        session = await db.get(ResearchSession, run.session_id)
                        if session is not None:
                            session.status = "failed"
                            session.error_message = MESSAGES["interrupted"]
                        run.stage = "failed"
                        run.error_code = "interrupted"
                        verification = await db.scalar(
                            select(VerificationRun).where(VerificationRun.run_id == run.id)
                        )
                        if verification is not None:
                            verification.status, verification.error_code = "failed", "interrupted"
                        run.finished_at = datetime.now(UTC)
                        metrics = Usage.model_validate(run.metrics)
                        metrics.usage_complete = False
                        metrics.estimated_cost_usd = (
                            0 if run.execution_mode in {"mock", "local"} else None
                        )
                        run.metrics = metrics.model_dump()
                self.lock_connection = connection
        except (SQLAlchemyError, TimeoutError):
            if connection is not None:
                # A session advisory lock survives pool rollback. Close the physical
                # connection on failed startup instead of returning a locked session.
                await connection.invalidate()
                await connection.close()
            logging.getLogger("researchforge.worker").warning("worker_not_ready")

    async def close(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                async with asyncio.timeout(5):
                    await self.task
            except (TimeoutError, asyncio.CancelledError):
                pass
        if self.lock_connection is not None:
            try:
                await self.lock_connection.execute(text("SELECT pg_advisory_unlock(72662002)"))
                await self.lock_connection.commit()
            except SQLAlchemyError:
                await self.lock_connection.invalidate()
            finally:
                await self.lock_connection.close()
                self.lock_connection = None

    async def submit(self, session_id: UUID, requested_mode: str) -> RunRead:
        if self.settings.execution_mode == "disabled":
            raise HTTPException(503, "Research providers are disabled or live approval is missing")
        if requested_mode != self.settings.execution_mode:
            raise HTTPException(409, "Requested execution mode does not match configured providers")
        async with self.guard:
            if self.task is not None and not self.task.done():
                raise HTTPException(
                    409, "The local research worker is busy; try after the active run finishes"
                )
            await self.open()
            if self.lock_connection is None or self.factory is None:
                raise HTTPException(
                    503, "Research worker unavailable; check database and single-worker setup"
                )
            async with self.factory() as db, db.begin():
                session = await db.scalar(
                    select(ResearchSession)
                    .where(
                        ResearchSession.id == session_id,
                        ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
                    )
                    .with_for_update()
                )
                if session is None:
                    raise HTTPException(404, "Research session not found")
                if session.mode == "documents" and (
                    self.documents is None
                    or not await self.documents.retrieve(
                        session.question, [UUID(d) for d in session.document_ids], 1
                    )
                ):
                    raise HTTPException(422, "Document mode requires ready indexed documents")
                if session.status != "pending":
                    raise HTTPException(
                        409, "Only pending sessions can execute; existing runs are never replayed"
                    )
                session.status = "running"
                session.error_message = None
                run = ResearchRun(
                    id=uuid4(),
                    session_id=session_id,
                    worker_id=self.worker_id,
                    execution_mode=requested_mode,
                    stage="accepted",
                    plan=None,
                    sources=[],
                    investigated_queries=[],
                    warnings=[],
                    metrics=Usage(
                        estimated_cost_usd=0 if requested_mode in {"mock", "local"} else None
                    ).model_dump(),
                    provider_model=(
                        self.settings.ollama_model
                        if self.settings.llm_provider == "ollama"
                        else self.settings.llm_model or "mock-v1"
                    ),
                    prompt_version=PROMPT_VERSION,
                )
                db.add(run)
                await db.flush()
                db.add(
                    VerificationRun(
                        run_id=run.id,
                        session_id=session_id,
                        status="running",
                        artifacts={},
                        drafts=[],
                        history=[],
                    )
                )
                response = run_response(run)
                question = session.question
                mode, document_ids = session.mode, [UUID(d) for d in session.document_ids]
            self.active_session = session_id
            self.task = asyncio.create_task(
                self.execute(run.id, session_id, question, mode, document_ids)
            )
            return response

    async def cancel(self, session_id: UUID) -> None:
        if self.factory is None:
            raise HTTPException(503, "Database unavailable")
        async with self.factory() as db, db.begin():
            session = await db.scalar(
                select(ResearchSession)
                .where(
                    ResearchSession.id == session_id,
                    ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
                )
                .with_for_update()
            )
            if session is None:
                raise HTTPException(404, "Research session not found")
            if session.status not in {"pending", "running"}:
                raise HTTPException(409, "Only pending or running sessions can be cancelled")
            session.status = "cancelled"
            run = await db.scalar(select(ResearchRun).where(ResearchRun.session_id == session_id))
            if run is not None:
                verification = await db.scalar(
                    select(VerificationRun).where(VerificationRun.run_id == run.id)
                )
                if verification is not None:
                    verification.status, verification.error_code = "failed", "cancelled"
                run.stage = "cancelled"
                run.finished_at = datetime.now(UTC)
        if self.active_session == session_id and self.task is not None:
            self.task.cancel()

    async def execute(
        self,
        run_id: UUID,
        session_id: UUID,
        question: str,
        mode: str = "web",
        document_ids: list[UUID] | None = None,
    ) -> None:
        assert self.factory is not None
        budget = RunBudget(self.settings, self.global_request_budget)
        started = perf_counter()
        llm = None
        current_stage = "accepted"
        current_sufficiency_statuses: list[str] = []
        current_candidate_count = 0

        def log_event(event: str, stage: str, error_code: str | None = None) -> None:
            usage = budget.usage
            logging.getLogger("researchforge.worker").info(
                event,
                extra={
                    "session_id": str(session_id),
                    "run_id": str(run_id),
                    "stage": stage,
                    "provider_type": (
                        f"{self.settings.llm_provider}/{self.settings.search_provider}"
                    ),
                    "model_id": (
                        self.settings.ollama_model
                        if self.settings.llm_provider == "ollama"
                        else self.settings.llm_model or "mock"
                    ),
                    "duration_ms": int((perf_counter() - started) * 1000),
                    "llm_requests": usage.llm_calls,
                    "search_requests": usage.search_calls,
                    "tool_calls": usage.tool_calls,
                    "token_usage": {
                        "input": usage.input_tokens,
                        "output": usage.output_tokens,
                        "reserved": usage.reserved_tokens,
                    },
                    "estimated_cost_usd": usage.estimated_cost_usd,
                    "candidate_count": current_candidate_count,
                    "sufficiency_statuses": current_sufficiency_statuses,
                    "error_code": error_code,
                },
            )

        async def checkpoint(stage: str, state: ResearchState) -> None:
            nonlocal current_stage, current_sufficiency_statuses, current_candidate_count
            assert self.factory is not None
            budget.usage.elapsed_ms = int((perf_counter() - started) * 1000)
            async with self.factory() as db, db.begin():
                session = await db.get(ResearchSession, session_id, with_for_update=True)
                run = await db.get(ResearchRun, run_id)
                if session is None or run is None or session.status != "running":
                    raise asyncio.CancelledError
                run.stage = stage
                run.plan = state["plan"].model_dump(mode="json") if state["plan"] else None
                run.sources = [source.model_dump(mode="json") for source in state["sources"]]
                run.investigated_queries = list(state["investigated_queries"])
                run.warnings = list(dict.fromkeys(state["warnings"]))
                run.metrics = budget.usage.model_dump()
                verification = await db.scalar(
                    select(VerificationRun).where(VerificationRun.run_id == run_id)
                )
                if verification is None:
                    raise ResearchFailure("verification_failed")
                verification.original_draft = (
                    state["original_report"].model_dump(mode="json")
                    if state["original_report"]
                    else None
                )
                verification.original_markdown = state["original_markdown"]
                verification.drafts = [
                    draft.model_dump(mode="json") for draft in state["draft_history"]
                ]
                verification.history = [
                    snapshot.model_dump(mode="json") for snapshot in state["verification_history"]
                ]
                if state["verification"]:
                    verification.artifacts = state["verification"].model_dump(mode="json")
                # Final completion is committed with the report in a later transaction.
            current_stage = stage
            current_candidate_count = len(state["sources"])
            if state["verification"]:
                current_sufficiency_statuses = [
                    result.status for result in state["verification"].evidence_sufficiency
                ]
            log_event("research_stage_completed", stage)

        error: str | None = None
        try:
            async with asyncio.timeout(self.settings.run_timeout_seconds):
                llm, search = providers(self.settings, budget)
                result = await run_workflow(
                    session_id,
                    question,
                    self.settings,
                    llm,
                    search,
                    budget,
                    checkpoint,
                    mode,
                    self.documents,
                    document_ids or [],
                )
                if (
                    not result["markdown"]
                    or result["report"] is None
                    or result["verification"] is None
                    or result["verification"].status != "completed"
                ):
                    raise ResearchFailure("invalid_output")
                async with self.factory() as db, db.begin():
                    session = await db.get(ResearchSession, session_id, with_for_update=True)
                    run = await db.get(ResearchRun, run_id)
                    if session is None or run is None or session.status != "running":
                        raise asyncio.CancelledError
                    # Deleted/reindexed/cross-workspace document evidence cannot pass finalization.
                    for source in result["sources"]:
                        if source.session_id != session_id:
                            raise ResearchFailure("verification_failed")
                        if source.source_type == "document":
                            valid = await db.scalar(
                                select(DocumentChunk.id)
                                .join(Document)
                                .where(
                                    DocumentChunk.id == source.chunk_id,
                                    Document.id == source.document_id,
                                    Document.workspace_id == LOCAL_WORKSPACE_ID,
                                    Document.status == "ready",
                                    DocumentChunk.generation == Document.generation,
                                    DocumentChunk.checksum == source.content_sha256,
                                )
                            )
                            if valid is None:
                                raise ResearchFailure("verification_failed")
                    verification = await db.scalar(
                        select(VerificationRun).where(VerificationRun.run_id == run_id)
                    )
                    if verification is None:
                        raise ResearchFailure("verification_failed")
                    verification.status = "completed"
                    verification.artifacts = result["verification"].model_dump(mode="json")
                    session.status = "completed"
                    run.stage = "completed"
                    run.report_json = result["report"].model_dump(mode="json")
                    run.report_markdown = result["markdown"]
                    budget.usage.elapsed_ms = int((perf_counter() - started) * 1000)
                    run.metrics = budget.usage.model_dump()
                    run.finished_at = datetime.now(UTC)
                current_stage = "completed"
                log_event("research_run_completed", current_stage)
        except asyncio.CancelledError:
            error = "interrupted"
        except TimeoutError:
            error = "run_timeout"
        except ResearchFailure as exc:
            error = str(exc) if str(exc) in MESSAGES else "internal_error"
        except Exception:
            error = "internal_error"
        finally:
            try:
                if error is not None:
                    async with self.factory() as db, db.begin():
                        session = await db.get(ResearchSession, session_id, with_for_update=True)
                        run = await db.get(ResearchRun, run_id)
                        if session is not None and run is not None:
                            if session.status == "running":
                                session.status = "failed"
                                session.error_message = MESSAGES[error]
                                run.stage = "failed"
                            if session.status == "failed":
                                verification = await db.scalar(
                                    select(VerificationRun).where(VerificationRun.run_id == run_id)
                                )
                                if verification is not None:
                                    verification.status, verification.error_code = "failed", error
                                    if verification.artifacts:
                                        verification.artifacts = {
                                            **verification.artifacts,
                                            "status": "failed",
                                            "error_code": error,
                                        }
                                run.error_code = error
                            budget.usage.usage_complete = False
                            budget.usage.estimated_cost_usd = (
                                None if self.settings.execution_mode == "live" else 0
                            )
                            budget.usage.elapsed_ms = int((perf_counter() - started) * 1000)
                            run.metrics = budget.usage.model_dump()
                            run.finished_at = datetime.now(UTC)
            except SQLAlchemyError:
                logging.getLogger("researchforge.worker").error(
                    "research_failure_persistence_unavailable"
                )
            finally:
                if error is not None:
                    log_event("research_run_failed", current_stage, error)
                if llm is not None:
                    try:
                        async with asyncio.timeout(2):
                            await llm.close()
                    except Exception:
                        logging.getLogger("researchforge.worker").warning("provider_close_failed")
