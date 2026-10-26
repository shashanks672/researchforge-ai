"""Explicit small CPU-model download; never called by application startup or tests."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import get_settings
from app.documents.embeddings import MODEL_REVISION
from fastembed import TextEmbedding
from huggingface_hub import snapshot_download

if __name__ == "__main__":
    settings = get_settings()
    snapshot = snapshot_download(
        repo_id="Qdrant/bge-small-en-v1.5-onnx-Q",
        revision=MODEL_REVISION,
        cache_dir=str(settings.model_cache),
        allow_patterns=[
            "model_optimized.onnx",
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ],
    )
    model = TextEmbedding(
        model_name=settings.embedding_model,
        cache_dir=str(settings.model_cache),
        specific_model_path=snapshot,
        threads=2,
        providers=["CPUExecutionProvider"],
    )
    print(
        json.dumps(
            {
                "model": settings.embedding_model,
                "dimensions": len(
                    next(
                        iter(model.embed(["ResearchForge local embedding smoke test."]))
                    )
                ),
                "cache_bytes": sum(
                    p.stat().st_size
                    for p in settings.model_cache.rglob("*")
                    if p.is_file() and not p.is_symlink()
                ),
            }
        )
    )
