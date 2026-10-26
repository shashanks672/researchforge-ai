"""Opt-in cached BGE/Qdrant answerability score study on synthetic fixtures."""

import json
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
from app.main import create_app
from app.research.answerability_evaluation import binary_metrics, select_f1_threshold
from tests.test_documents_postgres import ready, upload

pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(
        os.environ.get("RF_RUN_LOCAL_EVALUATION") != "1",
        reason="Opt-in cached BGE/Qdrant evaluation; no model downloads",
    ),
]


def test_phase6_retrieval_threshold_study(postgres_url: URL) -> None:
    root = Path(__file__).resolve().parents[2]
    dataset = json.loads((root / "evaluation/datasets/answerability-v1.json").read_text())
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=SecretStr(postgres_url.render_as_string(hide_password=False)),
        embedding_provider="local",
    )
    indexed: dict[str, str] = {}
    indexed_text: dict[str, str] = {}
    try:
        with TestClient(create_app(settings)) as client:
            for row in dataset["records"]:
                for passage in row["passages"]:
                    passage_id = str(passage["id"])
                    if passage_id in indexed:
                        continue
                    text = str(passage["text"])
                    if text in indexed_text:
                        indexed[passage_id] = indexed_text[text]
                        continue
                    did = upload(
                        client,
                        f"answerability-{passage_id}.txt",
                        text.encode(),
                    )
                    ready(client, did)
                    indexed[passage_id] = did
                    indexed_text[text] = did
            methods: dict[str, object] = {}
            for method in ("semantic", "bm25", "hybrid"):
                scores: dict[str, float] = {}
                gaps: dict[str, float] = {}
                relevant: dict[str, list[str]] = {}
                rankings: dict[str, list[str]] = {}
                categories: dict[str, str] = {}
                expected_status: dict[str, str] = {}
                for row in dataset["records"]:
                    qid = str(row["question_id"])
                    response = client.post(
                        "/api/v1/documents/retrieve",
                        json={
                            "question": row["question_text"],
                            "k": 10,
                            "method": method,
                            "document_ids": list(dict.fromkeys(indexed.values())),
                        },
                    )
                    assert response.status_code == 200, response.text
                    reverse = {did: pid for pid, did in indexed.items()}
                    found = [item for item in response.json() if item["document_id"] in reverse]
                    score_values = [float(item["score"]) for item in found]
                    scores[qid] = score_values[0] if score_values else float("-inf")
                    gaps[qid] = score_values[0] - score_values[1] if len(score_values) > 1 else 0.0
                    rankings[qid] = [reverse[item["document_id"]] for item in found]
                    relevant[qid] = [str(value) for value in row["relevant_passage_ids"]]
                    categories[qid] = str(row["category"])
                    expected_status[qid] = str(row["expected_answerability"])

                development = [r for r in dataset["records"] if r["split"] == "development"]
                held_out = [r for r in dataset["records"] if r["split"] == "held_out"]
                dev_ids = [str(r["question_id"]) for r in development]
                held_ids = [str(r["question_id"]) for r in held_out]
                threshold = select_f1_threshold(
                    [scores[qid] for qid in dev_ids],
                    [expected_status[qid] != "INSUFFICIENT" for qid in dev_ids],
                )
                actual = [expected_status[qid] != "INSUFFICIENT" for qid in held_ids]
                predicted = [scores[qid] >= threshold for qid in held_ids]
                measure = binary_metrics(actual, predicted, [categories[qid] for qid in held_ids])
                distributions = {}
                for label in ("answerable", "unanswerable"):
                    values = [
                        scores[qid]
                        for qid in held_ids
                        if (expected_status[qid] != "INSUFFICIENT") == (label == "answerable")
                        and scores[qid] != float("-inf")
                    ]
                    distributions[label] = {
                        "sample_count": len(values),
                        "min": min(values) if values else None,
                        "median": statistics.median(values) if values else None,
                        "max": max(values) if values else None,
                    }
                methods[method] = {
                    "threshold_selected_on_development_only": threshold,
                    "held_out_answerability_metrics": measure,
                    "held_out_top_score_distributions": distributions,
                    "held_out_top_score_gaps": {qid: gaps[qid] for qid in held_ids},
                    "raw_top_scores": scores,
                    "ranked_passage_ids": rankings,
                    "score_interpretation": (
                        "Ranking signal only, not a calibrated probability or answerability score."
                    ),
                }
            result = {
                "dataset_id": dataset["dataset_id"],
                "dataset_version": dataset["version"],
                "review_status": dataset["review_status"],
                "run_date": time.strftime("%Y-%m-%d", time.gmtime()),
                "source_revision": "uncommitted working tree",
                "run_config": {
                    "embedding_model": settings.embedding_model,
                    "embedding_provider": "cached BGE small English ONNX CPU",
                    "qdrant": "local disposable test namespace",
                    "python": platform.python_version(),
                    "hardware": "Apple M4, 16 GB unified memory",
                    "development_count": sum(
                        r["split"] == "development" for r in dataset["records"]
                    ),
                    "held_out_count": sum(r["split"] == "held_out" for r in dataset["records"]),
                },
                "methodology": {
                    "threshold_selection": (
                        "Maximize answerable-class F1 on development queries, then "
                        "apply once to held-out."
                    ),
                    "baseline": "See the lexical overlap baseline in phase-6-answerability.json.",
                    "no_answer_policy": (
                        "INSUFFICIENT is unanswerable; PARTIAL and CONFLICTING "
                        "require qualifications."
                    ),
                    "limitations": [
                        "Synthetic unreviewed corpus; six development, twelve held-out questions.",
                        "Top scores and score gaps do not establish coverage or entailment.",
                        "Hybrid RRF values are ranking signals, not probabilities.",
                    ],
                },
                "results_by_method": methods,
            }
            (root / "evaluation/results/phase-6-retrieval-thresholds.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
            for did in dict.fromkeys(indexed.values()):
                assert client.post(f"/api/v1/documents/{did}/delete", json={}).status_code == 200
    finally:
        indexed.clear()
