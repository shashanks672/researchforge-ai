import asyncio
from uuid import UUID

from rank_bm25 import BM25Plus  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import LOCAL_WORKSPACE_ID, Document, DocumentChunk
from app.documents.embeddings import Embeddings, tokens
from app.documents.schemas import Passage
from app.documents.vectors import VectorStore


async def retrieve(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    embedder: Embeddings,
    question: str,
    document_ids: list[UUID],
    k: int = 5,
    method: str = "hybrid",
) -> list[Passage]:
    async with factory() as db:
        query = (
            select(DocumentChunk, Document)
            .join(Document)
            .where(
                Document.workspace_id == LOCAL_WORKSPACE_ID,
                Document.status == "ready",
                Document.embedding_model == embedder.revision,
                DocumentChunk.generation == Document.generation,
            )
        )
        if document_ids:
            query = query.where(Document.id.in_(document_ids))
        # bounded local corpus: max 30 documents * 400 chunks; hard ceiling remains explicit.
        rows = (await db.execute(query.order_by(DocumentChunk.id).limit(12001))).all()
        if len(rows) > 12000:
            raise ValueError("corpus_limit")
        if not rows:
            return []
        chunks = {str(chunk.id): (chunk, doc) for chunk, doc in rows}

        def stable_key(chunk_id: str) -> tuple[str, str, int, int, str]:
            chunk, document = chunks[chunk_id]
            return (
                chunk.checksum,
                document.filename.casefold(),
                chunk.page or 0,
                chunk.ordinal,
                chunk.text,
            )

        keywords: list[tuple[str, float]] = []
        semantic: list[tuple[str, float]] = []
        if method != "semantic":
            corpus = [tokens(chunk.text) or [""] for chunk, _ in rows]
            # BM25Okapi can assign negative IDF to common terms in a tiny selected
            # document set, causing a passage with fewer matching terms to rank first.
            # BM25Plus keeps term contributions positive in this small-corpus case.
            bm25 = BM25Plus(corpus)
            scores = bm25.get_scores(tokens(question))
            # BM25Okapi may yield negative IDF on tiny corpora. An actual token overlap
            # is required; negative scores are still ranked, not discarded as 'no evidence'.
            query_tokens = set(tokens(question))
            keywords = sorted(
                [
                    (str(row[0].id), float(score))
                    for row, score, ts in zip(rows, scores, corpus, strict=True)
                    if query_tokens.intersection(ts)
                ],
                key=lambda x: (-x[1], stable_key(x[0])),
            )[:20]
        if method != "bm25":
            vectors = await asyncio.to_thread(embedder.embed, [question], query=True)
            store = VectorStore(settings, embedder.revision, embedder.dimension)
            try:
                await store.ensure(create=False)
                semantic = await store.search(vectors[0], list({doc.id for _, doc in rows}), 20)
                semantic = [(sid, score) for sid, score in semantic if sid in chunks]
                semantic.sort(key=lambda item: (-item[1], stable_key(item[0])))
            finally:
                await store.close()
        ranking: dict[str, float] = {}
        for ranking_list in [semantic, keywords]:
            for rank, (sid, _) in enumerate(ranking_list, 1):
                ranking[sid] = ranking.get(sid, 0) + 1 / (60 + rank)
        if method != "hybrid":
            ranking = dict(semantic if method == "semantic" else keywords)
        sem, key = dict(semantic), dict(keywords)
        result = []
        for sid, score in sorted(ranking.items(), key=lambda item: (-item[1], stable_key(item[0])))[
            :k
        ]:
            chunk, doc = chunks[sid]
            result.append(
                Passage(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    filename=doc.filename,
                    page=chunk.page,
                    heading=chunk.heading,
                    text=chunk.text,
                    checksum=chunk.checksum,
                    score=score,
                    semantic_score=sem.get(sid),
                    keyword_score=key.get(sid),
                )
            )
        return result
