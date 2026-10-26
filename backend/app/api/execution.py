from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LOCAL_WORKSPACE_ID, ResearchRun, ResearchSession, VerificationRun
from app.db.session import get_db
from app.research.schemas import ExecuteRequest, RunRead
from app.research.supervisor import ResearchSupervisor, run_response

router = APIRouter(prefix="/api/v1/research/sessions", tags=["research execution"])
Database = Annotated[AsyncSession, Depends(get_db, scope="function")]


@router.post("/{session_id}/execute", response_model=RunRead, status_code=202)
async def execute(session_id: UUID, payload: ExecuteRequest, request: Request) -> RunRead:
    supervisor = cast(ResearchSupervisor, request.app.state.research)
    return await supervisor.submit(session_id, payload.execution_mode)


@router.get("/{session_id}/run", response_model=RunRead)
async def details(session_id: UUID, db: Database, response: Response) -> RunRead:
    run = await db.scalar(
        select(ResearchRun)
        .join(ResearchSession)
        .where(
            ResearchRun.session_id == session_id,
            ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
        )
    )
    if run is None:
        raise HTTPException(404, "No execution found for this research session")
    response.headers["Cache-Control"] = "no-store"
    return run_response(run)


@router.post("/{session_id}/cancel", status_code=200)
async def cancel(session_id: UUID, request: Request) -> dict[str, str]:
    await cast(ResearchSupervisor, request.app.state.research).cancel(session_id)
    return {"status": "cancelled"}


@router.get("/{session_id}/report", response_class=PlainTextResponse)
async def export(session_id: UUID, db: Database) -> PlainTextResponse:
    run = await db.scalar(
        select(ResearchRun)
        .join(ResearchSession)
        .where(
            ResearchRun.session_id == session_id,
            ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
            ResearchSession.status == "completed",
        )
    )
    if run is None or run.report_markdown is None:
        raise HTTPException(404, "No completed report is available")
    return PlainTextResponse(
        run.report_markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="researchforge-{session_id}.md"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{session_id}/verification")
async def verification_details(
    session_id: UUID, db: Database, response: Response
) -> dict[str, object]:
    row = await db.scalar(
        select(VerificationRun)
        .join(ResearchSession)
        .where(
            VerificationRun.session_id == session_id,
            ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
        )
    )
    if row is None:
        raise HTTPException(
            404, "No stored verification; older reports are not retroactively assessed"
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": str(row.id),
        "session_id": str(row.session_id),
        "status": row.status,
        "artifacts": row.artifacts or None,
        "error_code": row.error_code,
        "original_markdown": row.original_markdown,
        "drafts": row.drafts,
        "history": row.history,
        "updated_at": row.updated_at.isoformat(),
    }
