from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LOCAL_WORKSPACE_ID, Document, ResearchSession
from app.schemas.sessions import SessionCreate, SessionPage, SessionRead


async def create_session(db: AsyncSession, payload: SessionCreate) -> SessionRead:
    if payload.document_ids:
        rows = (
            await db.scalars(
                select(Document.id).where(
                    Document.id.in_(payload.document_ids),
                    Document.workspace_id == LOCAL_WORKSPACE_ID,
                    Document.status == "ready",
                )
            )
        ).all()
        if len(set(rows)) != len(set(payload.document_ids)):
            raise HTTPException(422, "Select indexed documents from this workspace")
    record = ResearchSession(
        workspace_id=LOCAL_WORKSPACE_ID,
        question=payload.question,
        mode=payload.mode.value,
        status="pending",
        document_ids=[str(d) for d in dict.fromkeys(payload.document_ids)],
    )
    db.add(record)
    await db.flush()
    # Build the response before committing so serialization failures also roll back.
    result = SessionRead.model_validate(record)
    await db.commit()
    return result


async def list_sessions(db: AsyncSession, limit: int, offset: int) -> SessionPage:
    authorized = ResearchSession.workspace_id == LOCAL_WORKSPACE_ID
    total = await db.scalar(select(func.count()).select_from(ResearchSession).where(authorized))
    records = await db.scalars(
        select(ResearchSession)
        .where(authorized)
        .order_by(ResearchSession.created_at.desc(), ResearchSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [SessionRead.model_validate(record) for record in records]
    return SessionPage(
        items=items,
        total=total or 0,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < (total or 0),
    )


async def find_session(db: AsyncSession, session_id: UUID) -> SessionRead | None:
    record = await db.scalar(
        select(ResearchSession).where(
            ResearchSession.id == session_id,
            ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
        )
    )
    return SessionRead.model_validate(record) if record is not None else None
