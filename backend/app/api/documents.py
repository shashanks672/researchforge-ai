from typing import Annotated, cast
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LOCAL_WORKSPACE_ID, Document
from app.db.session import get_db
from app.documents.schemas import DocumentRead, Passage, RetrievalRequest
from app.documents.service import Documents

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
Database = Annotated[AsyncSession, Depends(get_db, scope="function")]


def manager(request: Request) -> Documents:
    return cast(Documents, request.app.state.documents)


@router.post("/upload", response_model=DocumentRead, status_code=202)
async def upload(request: Request) -> DocumentRead:
    return await manager(request).upload(request, unquote(request.headers.get("x-filename", "")))


@router.get("", response_model=list[DocumentRead])
async def listing(db: Database, response: Response) -> list[DocumentRead]:
    response.headers["Cache-Control"] = "no-store"
    rows = await db.scalars(
        select(Document)
        .where(Document.workspace_id == LOCAL_WORKSPACE_ID, Document.status != "deleted")
        .order_by(Document.uploaded_at.desc())
        .limit(100)
    )
    return [DocumentRead.model_validate(row) for row in rows]


@router.get("/{document_id}", response_model=DocumentRead)
async def details(
    document_id: UUID, db: Database, request: Request, response: Response
) -> DocumentRead:
    response.headers["Cache-Control"] = "no-store"
    return DocumentRead.model_validate(await manager(request).find(db, document_id))


@router.post("/{document_id}/delete", response_model=DocumentRead)
async def delete_document(document_id: UUID, request: Request) -> DocumentRead:
    return await manager(request).mutate(document_id, deleting=True)


@router.post("/{document_id}/reindex", response_model=DocumentRead, status_code=202)
async def reindex(document_id: UUID, request: Request) -> DocumentRead:
    return await manager(request).mutate(document_id, deleting=False)


@router.post("/retrieve", response_model=list[Passage])
async def retrieval(payload: RetrievalRequest, request: Request) -> list[Passage]:
    return await manager(request).retrieve(
        payload.question, payload.document_ids, payload.k, payload.method
    )
