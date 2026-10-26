from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings


class VectorStore:
    def __init__(self, settings: Settings, revision: str, dimension: int) -> None:
        self.dimension = dimension
        self.collection = f"{settings.qdrant_namespace}_{revision.replace('-', '_')}"
        self.client = AsyncQdrantClient(
            url=settings.qdrant_url, timeout=5, check_compatibility=False
        )

    async def ensure(self, *, create: bool = True) -> None:
        if not await self.client.collection_exists(self.collection):
            if not create:
                raise ValueError("index_missing")
            await self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(
                    size=self.dimension, distance=models.Distance.COSINE
                ),
                optimizers_config=models.OptimizersConfigDiff(default_segment_number=1),
            )
        info = await self.client.get_collection(self.collection)
        config = info.config.params.vectors
        if (
            not isinstance(config, models.VectorParams)
            or config.size != self.dimension
            or config.distance != models.Distance.COSINE
        ):
            raise ValueError("collection_dimension")

    async def upsert(
        self,
        rows: list[dict[str, object]],
        vectors: list[list[float]],
        document_id: UUID,
        generation: UUID,
    ) -> None:
        for start in range(0, len(rows), 8):
            points = [
                models.PointStruct(
                    id=str(row["id"]),
                    vector=vector,
                    payload={
                        "workspace_id": "local",
                        "document_id": str(document_id),
                        "generation": str(generation),
                    },
                )
                for row, vector in zip(
                    rows[start : start + 8], vectors[start : start + 8], strict=True
                )
            ]
            await self.client.upsert(self.collection, points=points, wait=True)

    @staticmethod
    def scope(document_ids: list[UUID]) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(key="workspace_id", match=models.MatchValue(value="local")),
                models.FieldCondition(
                    key="document_id", match=models.MatchAny(any=[str(d) for d in document_ids])
                ),
            ]
        )

    async def search(
        self, vector: list[float], document_ids: list[UUID], limit: int
    ) -> list[tuple[str, float]]:
        if not document_ids:
            return []
        result = await self.client.query_points(
            self.collection,
            query=vector,
            query_filter=self.scope(document_ids),
            limit=limit,
            with_payload=True,
        )
        return [(str(p.id), float(p.score)) for p in result.points]

    async def delete(self, document_id: UUID, collection: str | None = None) -> None:
        name = collection or self.collection
        if await self.client.collection_exists(name):
            await self.client.delete(
                name,
                points_selector=models.FilterSelector(filter=self.scope([document_id])),
                wait=True,
            )

    async def close(self) -> None:
        await self.client.close()
