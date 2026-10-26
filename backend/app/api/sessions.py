from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.sessions import SessionCreate, SessionPage, SessionRead
from app.services import sessions

router = APIRouter(prefix="/api/v1/research/sessions", tags=["research sessions"])
Database = Annotated[AsyncSession, Depends(get_db, scope="function")]


@router.post("", response_model=SessionRead, status_code=201)
async def create(payload: SessionCreate, db: Database, response: Response) -> SessionRead:
    record = await sessions.create_session(db, payload)
    response.headers["Location"] = f"/api/v1/research/sessions/{record.id}"
    response.headers["Cache-Control"] = "no-store"
    return record


@router.get("", response_model=SessionPage)
async def history(
    db: Database,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> SessionPage:
    response.headers["Cache-Control"] = "no-store"
    return await sessions.list_sessions(db, limit, offset)


@router.get("/{session_id}", response_model=SessionRead)
async def detail(session_id: UUID, db: Database, response: Response) -> SessionRead:
    record = await sessions.find_session(db, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Research session not found")
    response.headers["Cache-Control"] = "no-store"
    return record
