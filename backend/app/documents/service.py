import asyncio
import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import LOCAL_WORKSPACE_ID, Document, DocumentChunk, ResearchSession
from app.documents.embeddings import Embeddings, embedding_provider, validate_vectors
from app.documents.parsing import Page, chunks
from app.documents.retrieval import retrieve
from app.documents.schemas import DocumentRead, Passage
from app.documents.vectors import VectorStore

TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class Documents:
    def __init__(
        self, factory: async_sessionmaker[AsyncSession] | None, settings: Settings
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.task: asyncio.Task[None] | None = None
        self.guard = asyncio.Lock()
        self.embedder: Embeddings | None = None
        self.owner = False

    async def embeddings(self) -> Embeddings:
        if self.embedder is None:
            self.embedder = await asyncio.to_thread(embedding_provider, self.settings)
        return self.embedder

    def path(self, key: str) -> Path:
        root = self.settings.storage_root.resolve()
        if not key or Path(key).name != key:
            raise ValueError("storage_key")
        path = root / key
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError("storage_key")
        return path

    def database(self) -> async_sessionmaker[AsyncSession]:
        if self.factory is None:
            raise HTTPException(503, "Document database unavailable")
        return self.factory

    async def open(self, owner: bool) -> None:
        self.owner = owner
        if not owner or self.factory is None:
            return
        try:
            async with self.factory() as db, db.begin():
                rows = (
                    await db.scalars(
                        select(Document).where(
                            Document.workspace_id == LOCAL_WORKSPACE_ID,
                            Document.status.in_(["queued", "processing", "deleting"]),
                        )
                    )
                ).all()
                for row in rows:
                    row.status, row.index_status, row.error_code = (
                        "failed",
                        "incomplete",
                        "interrupted",
                    )
        except SQLAlchemyError:
            self.owner = False

    async def close(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    def available(self) -> None:
        if not self.owner:
            raise HTTPException(503, "Document worker unavailable; use one API worker")
        if self.task and not self.task.done():
            raise HTTPException(409, "Document worker is busy; refresh before retrying")

    async def find(self, db: AsyncSession, document_id: UUID) -> Document:
        row = await db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == LOCAL_WORKSPACE_ID,
                Document.status != "deleted",
            )
        )
        if row is None:
            raise HTTPException(404, "Document not found")
        return row

    async def upload(self, request: Request, filename: str) -> DocumentRead:
        suffix = Path(filename).suffix.lower()
        if (
            suffix not in TYPES
            or len(filename) > 255
            or not filename
            or any(c in filename for c in "/\\")
            or any(ord(c) < 32 or ord(c) == 127 for c in filename)
        ):
            raise HTTPException(422, "Use a simple PDF, DOCX, TXT or Markdown filename")
        async with self.guard:
            self.available()
            factory = self.database()
            root = self.settings.storage_root
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            key = f"{uuid4().hex}{suffix}"
            temporary = self.path(key + ".part")
            final = self.path(key)
            digest, size = hashlib.sha256(), 0
            try:
                with temporary.open("xb") as stream:
                    os.chmod(temporary, 0o600)
                    async with asyncio.timeout(30):
                        async for block in request.stream():
                            size += len(block)
                            if size > self.settings.max_upload_bytes:
                                raise HTTPException(413, "Document exceeds upload size limit")
                            digest.update(block)
                            stream.write(block)
                    stream.flush()
                    os.fsync(stream.fileno())
                if size == 0:
                    raise HTTPException(422, "Empty document")
                header = temporary.read_bytes()[:8]
                if (suffix == ".pdf" and not header.startswith(b"%PDF-")) or (
                    suffix == ".docx" and not header.startswith(b"PK\x03\x04")
                ):
                    raise HTTPException(422, "File content does not match its extension")
                os.replace(temporary, final)
                async with factory() as db, db.begin():
                    count = await db.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(
                            Document.status != "deleted",
                            Document.workspace_id == LOCAL_WORKSPACE_ID,
                        )
                    )
                    if (count or 0) >= self.settings.max_documents:
                        raise HTTPException(409, "Local document storage limit reached")
                    existing = await db.scalar(
                        select(Document).where(
                            Document.workspace_id == LOCAL_WORKSPACE_ID,
                            Document.checksum == digest.hexdigest(),
                            Document.status != "deleted",
                        )
                    )
                    if existing:
                        raise HTTPException(
                            409, "Duplicate upload; inspect the existing document or reindex it"
                        )
                    row = Document(
                        id=uuid4(),
                        workspace_id=LOCAL_WORKSPACE_ID,
                        filename=filename,
                        storage_key=key,
                        content_type=TYPES[suffix],
                        size_bytes=size,
                        checksum=digest.hexdigest(),
                        status="queued",
                    )
                    db.add(row)
                    await db.flush()
                    result = DocumentRead.model_validate(row)
                self.task = asyncio.create_task(self.ingest(result.id))
                return result
            except BaseException:
                temporary.unlink(missing_ok=True)
                final.unlink(missing_ok=True)
                raise

    async def ingest(self, document_id: UUID) -> None:
        factory = self.database()
        process: asyncio.subprocess.Process | None = None
        code = "ingestion_failed"
        try:
            async with asyncio.timeout(90):
                async with factory() as db, db.begin():
                    row = await self.find(db, document_id)
                    row.status, row.index_status, row.error_code = "processing", "indexing", None
                    path, generation = self.path(row.storage_key), row.generation
                    old_collection = row.index_collection
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "app.documents.parsing",
                    str(path),
                    path.suffix,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env={
                        "PATH": os.environ.get("PATH", ""),
                        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                    },
                )
                async with asyncio.timeout(20):
                    output, _ = await process.communicate()
                if process.returncode != 0 or len(output) > 2_000_000:
                    raise ValueError("parser_failed")
                data = json.loads(output)
                if "error" in data:
                    code = data["error"]
                    raise ValueError(code)
                pages = [Page(**page) for page in data["pages"]]
                batch = chunks(
                    pages, document_id, self.settings.chunk_chars, self.settings.chunk_overlap
                )
                embedder = await self.embeddings()
                store = VectorStore(self.settings, embedder.revision, embedder.dimension)
                try:
                    await store.ensure()
                    await store.delete(document_id, old_collection)
                    vectors = await asyncio.to_thread(
                        embedder.embed, [str(chunk["text"]) for chunk in batch]
                    )
                    validate_vectors(vectors, len(batch), embedder.dimension)
                    await store.upsert(batch, vectors, document_id, generation)
                    # Read-after-write count is mandatory; wait=true alone is not ingestion readin
                    count = await store.client.count(
                        store.collection, count_filter=store.scope([document_id]), exact=True
                    )
                    if count.count != len(batch):
                        raise ValueError("index_incomplete")
                    async with factory() as db, db.begin():
                        row = await self.find(db, document_id)
                        await db.execute(
                            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                        )
                        for chunk in batch:
                            db.add(
                                DocumentChunk(
                                    id=UUID(str(chunk["id"])),
                                    document_id=document_id,
                                    generation=generation,
                                    ordinal=chunk["ordinal"],
                                    page=chunk["page"],
                                    heading=chunk["heading"],
                                    text=chunk["text"],
                                    checksum=chunk["checksum"],
                                )
                            )
                        row.status, row.index_status = "ready", "indexed"
                        row.chunk_count, row.page_count = (
                            len(batch),
                            max((p.page or 0 for p in pages), default=0) or None,
                        )
                        row.embedding_model, row.index_collection = (
                            embedder.revision,
                            store.collection,
                        )
                finally:
                    await store.close()
                return
        except asyncio.CancelledError:
            code = "interrupted"
        except Exception:
            pass
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
        try:
            async with factory() as db, db.begin():
                row = await self.find(db, document_id)
                row.status, row.index_status, row.error_code = "failed", "incomplete", code
        except Exception:
            # Startup recovery retries state reconciliation; failed vectors remain filtered out.
            pass

    async def mutate(self, document_id: UUID, *, deleting: bool) -> DocumentRead:
        async with self.guard:
            self.available()
            factory = self.database()
            async with factory() as db, db.begin():
                row = await self.find(db, document_id)
                active = await db.scalar(
                    select(ResearchSession.id)
                    .where(
                        ResearchSession.workspace_id == LOCAL_WORKSPACE_ID,
                        ResearchSession.status == "running",
                        ResearchSession.mode.in_(["documents", "combined"]),
                    )
                    .limit(1)
                )
                if active:
                    raise HTTPException(
                        409, "Wait for active document research before deleting or reindexing"
                    )
                row.status, row.index_status = (
                    ("deleting", "deleting") if deleting else ("queued", "not_indexed")
                )
                row.generation = uuid4()
                result = DocumentRead.model_validate(row)
                key, collection = row.storage_key, row.index_collection
            if not deleting:
                self.task = asyncio.create_task(self.ingest(document_id))
                return result
            embedder = await self.embeddings()
            store = VectorStore(self.settings, embedder.revision, embedder.dimension)
            try:
                await store.delete(document_id, collection)
                self.path(key).unlink(missing_ok=True)
                async with factory() as db, db.begin():
                    row = await self.find(db, document_id)
                    await db.execute(
                        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                    )
                    row.status, row.index_status, row.chunk_count = "deleted", "deleted", 0
                    # Tombstone keeps checksum for idempotency; explicit re-upload requires reinde
                    result = DocumentRead.model_validate(row)
                return result
            except Exception as exc:
                async with factory() as db, db.begin():
                    row = await self.find(db, document_id)
                    row.status, row.index_status, row.error_code = (
                        "failed",
                        "delete_incomplete",
                        "delete_failed",
                    )
                raise HTTPException(
                    503, "Deletion incomplete; retry deletion to reconcile vectors and storage"
                ) from exc
            finally:
                await store.close()

    async def retrieve(
        self, question: str, ids: list[UUID], k: int = 5, method: str = "hybrid"
    ) -> list[Passage]:
        try:
            return await retrieve(
                self.database(), self.settings, await self.embeddings(), question, ids, k, method
            )
        except Exception as exc:
            raise HTTPException(
                503, "Document retrieval unavailable; check model, database and Qdrant"
            ) from exc
