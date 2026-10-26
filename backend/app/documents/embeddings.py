import hashlib
import math
import re
from typing import Protocol

from app.core.config import Settings


def tokens(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.casefold(), flags=re.UNICODE)


class Embeddings(Protocol):
    dimension: int
    revision: str

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


class FakeEmbeddings:
    """Deterministic hashed token vectors; test fixtures, not sentence semantics."""

    dimension = 64
    revision = "fake-hash-v1"

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        result = []
        for text in texts:
            row = [0.0] * self.dimension
            for token in tokens(text):
                row[
                    int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
                    % self.dimension
                ] += 1
            norm = math.sqrt(sum(v * v for v in row)) or 1
            result.append([v / norm for v in row])
        return result


MODEL_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"


class LocalEmbeddings:
    dimension = 384
    revision = "bge-small-aa8f8b06-v1"

    def __init__(self, settings: Settings) -> None:
        from fastembed import TextEmbedding

        snapshot = (
            settings.model_cache
            / "models--Qdrant--bge-small-en-v1.5-onnx-Q"
            / "snapshots"
            / MODEL_REVISION
        )
        if not snapshot.is_dir():
            raise ValueError("model_not_cached")
        self.batch = settings.embedding_batch_size
        self.model = TextEmbedding(
            model_name=settings.embedding_model,
            cache_dir=str(settings.model_cache),
            threads=2,
            providers=["CPUExecutionProvider"],
            local_files_only=True,
            specific_model_path=str(snapshot),
        )

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        rows = (
            self.model.query_embed(texts)
            if query
            else self.model.passage_embed(texts, batch_size=self.batch)
        )
        result = [row.tolist() for row in rows]
        validate_vectors(result, len(texts), self.dimension)
        return result


def validate_vectors(rows: list[list[float]], count: int, dimension: int) -> None:
    if len(rows) != count or any(
        len(r) != dimension or not all(math.isfinite(v) for v in r) for r in rows
    ):
        raise ValueError("embedding_dimension")


def embedding_provider(settings: Settings) -> Embeddings:
    return LocalEmbeddings(settings) if settings.embedding_provider == "local" else FakeEmbeddings()
