"""One-shot local Ollama evaluation; never calls hosted models or search services."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from statistics import median
from uuid import UUID, uuid5

from app.core.config import Settings
from app.research.budget import RunBudget
from app.research.errors import InvalidProviderOutput, ResearchFailure
from app.research.providers import OllamaLLM, account_usage
from app.research.schemas import EvidenceSource
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/datasets/phase-7-answerability-v2.json"
NAMESPACE = UUID("db898604-e665-49bb-8251-12deef48df83")


def confusion(
    rows: list[dict[str, str]], labels: list[str]
) -> dict[str, dict[str, int]]:
    return {
        expected: {
            predicted: sum(
                row["expected_status"] == expected
                and row["predicted_status"] == predicted
                for row in rows
            )
            for predicted in labels
        }
        for expected in labels
    }


def macro_f1(matrix: dict[str, dict[str, int]], labels: list[str]) -> float:
    scores = []
    for label in labels:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[other][label] for other in labels if other != label)
        false_negative = sum(matrix[label][other] for other in labels if other != label)
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(2 * true_positive / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


async def main(development_only: bool = False) -> None:
    dataset = json.loads(DATASET.read_text())
    settings = Settings(
        _env_file=None,
        llm_provider="ollama",
        search_provider="disabled",
        free_search_enabled=False,
        live_calls_approved=False,
        max_context_chars=8000,
        ollama_context_tokens=8192,
        llm_max_output_tokens=512,
        ollama_timeout_seconds=90,
        max_page_bytes=256_000,
    )
    provider = OllamaLLM(settings)
    session_id = uuid5(NAMESPACE, dataset["dataset_id"])
    output_path = (
        ROOT
        / "evaluation/results"
        / (
            "phase-7-ollama-answerability-development-v3.json"
            if development_only
            else "phase-7-ollama-answerability-v2.json"
        )
    )
    output: dict[str, object] = {
        "dataset_id": dataset["dataset_id"],
        "label_status": dataset["label_status"],
        "model": settings.ollama_model,
        "provider": "local_ollama",
        "thinking_mode": "disabled",
        "search_calls": 0,
        "phase_6_held_out_used_for_tuning": False,
        "provider_retries": settings.provider_retries,
    }
    try:
        split_names = (
            ("development",) if development_only else ("development", "final_test")
        )
        for split_name in split_names:
            rows: list[dict[str, str]] = []
            for example in dataset[split_name]:
                sources: list[EvidenceSource] = []
                for source_index, excerpt in enumerate(example["sources"], start=1):
                    sources.append(
                        EvidenceSource(
                            source_id=f"S{source_index}",
                            session_id=session_id,
                            source_type="document",
                            title=f"{example['id']} passage {source_index}",
                            url="",
                            retrieved_at=datetime.now(UTC),
                            excerpt=excerpt,
                            content_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
                            search_query=example["question"],
                        )
                    )
                started = datetime.now(UTC)
                budget = RunBudget(settings)
                try:
                    operation = partial(
                        provider.assess_sufficiency, "Q1", example["question"], sources
                    )
                    result = await budget.invoke(operation, "llm")
                    decision = account_usage(budget, result)
                    status: str = decision.status
                    error = None
                    assessment = json.dumps(
                        decision.model_dump(mode="json"), ensure_ascii=False
                    )
                    elapsed_ms = int(
                        (datetime.now(UTC) - started).total_seconds() * 1000
                    )
                except (
                    ResearchFailure
                ) as exc:  # Record only a safe error class, never provider text.
                    status = "ERROR"
                    error = type(exc).__name__
                    cause = exc.__cause__
                    if isinstance(cause, InvalidProviderOutput):
                        cause = cause.__cause__
                    if isinstance(cause, ValidationError):
                        diagnostic = json.dumps(
                            [
                                {
                                    "field": ".".join(
                                        str(part) for part in issue["loc"]
                                    ),
                                    "type": issue["type"],
                                }
                                for issue in cause.errors()
                            ]
                        )
                    elif isinstance(cause, ValueError):
                        diagnostic = str(cause)[:200]
                    else:
                        diagnostic = (
                            type(cause).__name__ if cause is not None else "unknown"
                        )
                    assessment = ""
                    elapsed_ms = int(
                        (datetime.now(UTC) - started).total_seconds() * 1000
                    )
                rows.append(
                    {
                        "id": example["id"],
                        "question": example["question"],
                        "expected_status": example["expected_status"],
                        "predicted_status": status,
                        "error_type": error or "",
                        "validation_diagnostic": diagnostic if error else "",
                        "assessment_json": assessment,
                        "latency_ms": str(elapsed_ms),
                        "llm_calls": str(budget.usage.llm_calls),
                        "input_tokens": str(budget.usage.input_tokens),
                        "output_tokens": str(budget.usage.output_tokens),
                        "model_inference_ms": str(budget.usage.model_inference_ms),
                        "model_load_ms": str(budget.usage.model_load_ms),
                    }
                )
            labels = ["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "CONFLICTING"]
            false_answer = sum(
                row["expected_status"] in {"PARTIAL", "INSUFFICIENT", "CONFLICTING"}
                and row["predicted_status"] == "SUFFICIENT"
                for row in rows
            )
            unanswerable = sum(
                row["expected_status"] in {"PARTIAL", "INSUFFICIENT", "CONFLICTING"}
                for row in rows
            )
            expected_answerable = sum(
                row["expected_status"] == "SUFFICIENT" for row in rows
            )
            correct_abstentions = sum(
                row["expected_status"] in {"PARTIAL", "INSUFFICIENT", "CONFLICTING"}
                and row["predicted_status"]
                in {"PARTIAL", "INSUFFICIENT", "CONFLICTING"}
                for row in rows
            )
            rows_obj = {
                "cases": rows,
                "confusion_matrix": confusion(rows, labels),
                "macro_f1": macro_f1(confusion(rows, labels), labels),
                "error_count": sum(row["predicted_status"] == "ERROR" for row in rows),
                "valid_prediction_count": sum(
                    row["predicted_status"] in labels for row in rows
                ),
                "structured_output_validity_rate": sum(
                    row["predicted_status"] in labels for row in rows
                )
                / len(rows),
                "llm_calls": sum(int(row["llm_calls"]) for row in rows),
                "input_tokens": sum(int(row["input_tokens"]) for row in rows),
                "output_tokens": sum(int(row["output_tokens"]) for row in rows),
                "model_inference_ms": sum(
                    int(row["model_inference_ms"]) for row in rows
                ),
                "model_load_ms": sum(int(row["model_load_ms"]) for row in rows),
                "false_answer_count": false_answer,
                "unanswerable_count": unanswerable,
                "false_answer_rate": false_answer / unanswerable
                if unanswerable
                else None,
                "correct_abstention_count": correct_abstentions,
                "correct_abstention_rate": correct_abstentions / unanswerable
                if unanswerable
                else None,
                "answerable_recall": (
                    sum(
                        row["expected_status"] == "SUFFICIENT"
                        and row["predicted_status"] == "SUFFICIENT"
                        for row in rows
                    )
                    / expected_answerable
                    if expected_answerable
                    else None
                ),
                "accuracy": (
                    sum(
                        row["expected_status"] == row["predicted_status"]
                        for row in rows
                    )
                    / len(rows)
                ),
                "median_latency_ms": median(int(row["latency_ms"]) for row in rows),
                "validated_quote_count": sum(
                    len(fact.get("evidence", []))
                    for row in rows
                    if row["assessment_json"]
                    for fact in json.loads(row["assessment_json"])["fact_assessments"]
                ),
                "quote_id_and_exact_text_validity": "100% of quotes in accepted outputs; enforced by provider validation",
            }
            output[split_name] = rows_obj
    finally:
        await provider.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_WRITE = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    output_path.write_text(OUTPUT_WRITE)
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    ("model", "development")
                    if development_only
                    else ("model", "development", "final_test")
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--development-only",
        action="store_true",
        help="run calibration cases only; do not evaluate the final test split",
    )
    arguments = parser.parse_args()
    asyncio.run(main(arguments.development_only))
