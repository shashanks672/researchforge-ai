"""Opt-in real local-model benchmark; generated English pilot records, no quality generalization."""

import json
import math
import os
import platform
import statistics
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.engine import URL

from app.core.config import Settings
from app.documents.evaluation import retrieval_metrics
from app.main import create_app
from tests.test_documents_postgres import ready, upload

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.environ.get("RF_RUN_LOCAL_EVALUATION") != "1",
        reason="Opt-in cached local model evaluation; no CI downloads",
    ),
]
CASES = [
    (
        "juniper.txt",
        "The Juniper battery stores 20 kWh of electricity. "
        "It operates in Bristol. Inspections are required every 30 days.",
        "What is the energy storage capacity of Juniper?",
    ),
    (
        "cedar.txt",
        "The Cedar wind turbine produces 50 kilowatts at rated wind speed. "
        "This pilot is in York. It was installed in 2024.",
        "How much power does the Cedar turbine generate?",
    ),
    (
        "maple.txt",
        "The Maple solar array has 40 panels with a total peak capacity of 16 kilowatts. "
        "Its panels face south.",
        "How many photovoltaic panels does Maple contain?",
    ),
    (
        "birch.txt",
        "The Birch water reservoir holds 900 litres. "
        "The inspection schedule is once a week. Water is used for irrigation.",
        "How much water can Birch store?",
    ),
    (
        "willow.txt",
        "The Willow heat pump has a seasonal coefficient of performance of 3.8. "
        "It heats the local library in Bath.",
        "What is the seasonal efficiency coefficient of Willow?",
    ),
    (
        "oak.txt",
        "The Oak electric shuttle carries 18 passengers. "
        "It runs between the station and campus every 15 minutes.",
        "What is the passenger capacity of Oak?",
    ),
]


def test_phase5_retrieval_benchmark(postgres_url: URL) -> None:
    dataset_path = Path(__file__).resolve().parents[2] / "evaluation/datasets/retrieval-v1.json"
    dataset = json.loads(dataset_path.read_text())
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
        embedding_provider="local",
    )
    indexed: dict[str, tuple[str, dict[str, object]]] = {}
    indexing_ms: dict[str, float] = {}
    started = time.perf_counter()
    with TestClient(create_app(settings)) as client:
        for passage in dataset["passages"]:
            begin = time.perf_counter()
            did = upload(
                client,
                str(passage["document"]),
                str(passage["text"]).encode("utf-8"),
            )
            doc = ready(client, did)
            indexed[str(passage["id"])] = (did, doc)
            indexing_ms[str(passage["id"])] = (time.perf_counter() - begin) * 1000
        methods: dict[str, object] = {}
        raw_results: dict[str, object] = {}
        for method in ("semantic", "bm25", "hybrid"):
            rankings: dict[str, list[str]] = {}
            judgments: dict[str, list[str]] = {}
            latencies: dict[str, float] = {}
            for query in dataset["queries"]:
                qid = str(query["id"])
                begin = time.perf_counter()
                response = client.post(
                    "/api/v1/documents/retrieve",
                    json={
                        "question": query["text"],
                        "k": 10,
                        "method": method,
                        "document_ids": [did for did, _ in indexed.values()],
                    },
                )
                assert response.status_code == 200, response.text
                latencies[qid] = (time.perf_counter() - begin) * 1000
                reverse = {doc_id: passage_id for passage_id, (doc_id, _) in indexed.items()}
                rankings[qid] = [
                    reverse[item["document_id"]]
                    for item in response.json()
                    if item["document_id"] in reverse
                ]
                judgments[qid] = [str(pid) for pid in query["relevant"]]
            methods[method] = retrieval_metrics(
                judgments,
                rankings,
                latencies,
                catalog_ids=set(indexed),
                ks=(1, 3, 5, 10),
            )
            raw_results[method] = {
                "ranked_passage_ids_by_query": rankings,
                "latency_ms_by_query": latencies,
            }
        result = {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["version"],
            "provenance": dataset["provenance"],
            "run_date": time.strftime("%Y-%m-%d", time.gmtime()),
            "source_revision": "uncommitted working tree; no Git commit required",
            "run_config": {
                "embedding_model": settings.embedding_model,
                "embedding_revision": "aa8f8b060edb00e03bfdd08813a2949946c8ba55",
                "embedding_provider": "FastEmbed ONNX CPU, 2 threads, batch 8",
                "qdrant": "local Compose service; existing named collection; cosine",
                "chunk_size_characters": settings.chunk_chars,
                "chunk_overlap_characters": settings.chunk_overlap,
                "retrieval_candidate_k": 20,
                "hybrid_fusion": "reciprocal rank fusion, constant 60",
                "returned_k": 10,
                "hardware": "Apple M4, ARM64, 16 GB unified memory",
                "python": platform.python_version(),
                "dataset_passages": len(dataset["passages"]),
                "dataset_queries": len(dataset["queries"]),
                "sample_type": (
                    "small synthetic, provisional labels; not external or human-validated"
                ),
            },
            "metric_definitions": {
                "recall_at_k": (
                    "fraction of labelled relevant passages retrieved in first K; "
                    "answerable queries only"
                ),
                "precision_at_k": (
                    "relevant passages in first K divided by K; answerable queries only"
                ),
                "mrr": "mean reciprocal rank of first relevant passage; answerable queries only",
                "ndcg_at_k": (
                    "binary relevance discounted cumulative gain divided by ideal gain; "
                    "answerable queries only"
                ),
                "no_answer": (
                    "excluded from relevance metrics; empty-result rate is reported separately"
                ),
                "p95": "nearest-rank p95 only when at least 20 query samples exist",
            },
            "results_by_method": methods,
            "raw_results_by_method": raw_results,
            "indexing_ms_by_passage": indexing_ms,
            "total_indexing_ms": (time.perf_counter() - started) * 1000,
            "uploaded_bytes": sum(int(str(doc["size_bytes"])) for _, doc in indexed.values()),
            "memory": "not measured; no profiling package installed",
            "limitations": [
                "Synthetic evaluation corpus and provisional labels; not independently reviewed.",
                "Queries were designed to cover retrieval types and were not used for tuning.",
                "Short passages are separate documents; long-document chunking is untested.",
                "A small corpus cannot support statistical significance or broad quality claims.",
                "Actual local embeddings and Qdrant; no generator is called.",
            ],
        }
        target = Path(__file__).resolve().parents[2] / "evaluation/results/phase-5-retrieval.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2) + "\n")
        for did, _ in indexed.values():
            assert client.post(f"/api/v1/documents/{did}/delete", json={}).status_code == 200


def test_local_retrieval_evaluation(postgres_url: URL) -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
        embedding_provider="local",
    )
    indexed = []
    indexing_ms = []
    with TestClient(create_app(settings)) as client:
        for name, text, _ in CASES:
            start = time.perf_counter()
            did = upload(client, name, text.encode())
            doc = ready(client, did)
            indexed.append((did, doc))
            indexing_ms.append((time.perf_counter() - start) * 1000)
        scores: dict[str, object] = {}
        for method in ("semantic", "bm25", "hybrid"):
            recalls, reciprocal, ndcgs, latencies = [], [], [], []
            for (_, _, question), (relevant, _) in zip(CASES, indexed, strict=True):
                start = time.perf_counter()
                response = client.post(
                    "/api/v1/documents/retrieve",
                    json={
                        "question": question,
                        "k": 3,
                        "method": method,
                        "document_ids": [did for did, _ in indexed],
                    },
                )
                assert response.status_code == 200, response.text
                latency = (time.perf_counter() - start) * 1000
                results = response.json()
                ranks = [
                    i for i, passage in enumerate(results, 1) if passage["document_id"] == relevant
                ]
                rank = min(ranks) if ranks else None
                recalls.append(float(rank is not None))
                reciprocal.append(1 / rank if rank else 0)
                ndcgs.append(1 / math.log2(rank + 1) if rank else 0)
                latencies.append(latency)
            scores[method] = {
                "recall_at_3": statistics.mean(recalls),
                "mrr_at_3": statistics.mean(reciprocal),
                "ndcg_at_3": statistics.mean(ndcgs),
                "mean_latency_ms": statistics.mean(latencies),
                "latencies_ms": latencies,
            }
        result = {
            "corpus": "6 generated records; one relevant document per query; K=3",
            "cases": CASES,
            "model": settings.embedding_model,
            "model_revision": "aa8f8b060edb00e03bfdd08813a2949946c8ba55",
            "device": "CPUExecutionProvider, 2 threads, batch 8",
            "metrics": scores,
            "indexing_ms": indexing_ms,
            "chunks": sum(int(str(doc["chunk_count"])) for _, doc in indexed),
            "uploaded_bytes": sum(int(str(doc["size_bytes"])) for _, doc in indexed),
            "collection_storage": "Docker volume observation includes shared collections",
        }
        target = Path(__file__).resolve().parents[2] / "evaluation/phase-3-results.json"
        target.write_text(json.dumps(result, indent=2) + "\n")
        for did, _ in indexed:
            assert client.post(f"/api/v1/documents/{did}/delete", json={}).status_code == 200
