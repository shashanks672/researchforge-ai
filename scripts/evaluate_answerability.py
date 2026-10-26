#!/usr/bin/env python3
"""Run the synthetic lexical baseline with a development-only threshold."""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.research.answerability_evaluation import (
    binary_metrics,
    lexical_overlap,
    select_f1_threshold,
)


def main() -> None:
    dataset = json.loads(
        (ROOT / "evaluation/datasets/answerability-v1.json").read_text()
    )
    records = dataset["records"]
    for row in records:
        row["lexical_overlap_score"] = lexical_overlap(
            row["question_text"], [item["text"] for item in row["passages"]]
        )
    development = [row for row in records if row["split"] == "development"]
    held_out = [row for row in records if row["split"] == "held_out"]
    if not development or not held_out:
        raise SystemExit("Dataset must have development and held-out records")
    dev_labels = [
        row["expected_answerability"] != "INSUFFICIENT" for row in development
    ]
    threshold = select_f1_threshold(
        [row["lexical_overlap_score"] for row in development], dev_labels
    )
    actual = [row["expected_answerability"] != "INSUFFICIENT" for row in held_out]
    predicted = [row["lexical_overlap_score"] >= threshold for row in held_out]
    metrics = binary_metrics(
        actual, predicted, [str(row["category"]) for row in held_out]
    )
    baseline = binary_metrics(
        actual, [True] * len(actual), [str(r["category"]) for r in held_out]
    )
    output = {
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["version"],
        "provenance": dataset["provenance"],
        "review_status": dataset["review_status"],
        "run_type": "synthetic lexical baseline; not an LLM or semantic quality result",
        "split_counts": {"development": len(development), "held_out": len(held_out)},
        "threshold_selection": {
            "method": "maximize answerable-class F1 on development split; ties choose the lowest threshold",
            "lexical_overlap_threshold": threshold,
            "threshold_is_calibrated_probability": False,
        },
        "metric_denominators": {
            "false_answer_rate": "false positives / all held-out labels marked INSUFFICIENT",
            "correct_abstention_rate": "true negatives / all held-out labels marked INSUFFICIENT",
            "incorrect_abstention_rate": "false negatives / all held-out answerable labels",
        },
        "held_out_metrics": metrics,
        "always_answer_baseline": baseline,
        "per_record": [
            {
                "question_id": row["question_id"],
                "category": row["category"],
                "expected_answerability": row["expected_answerability"],
                "lexical_overlap_score": row["lexical_overlap_score"],
                "predicted_answerable": guess,
                "correct": actual_label == guess,
            }
            for row, actual_label, guess in zip(
                held_out, actual, predicted, strict=True
            )
        ],
        "limitations": [
            "Only 12 held-out synthetic examples; labels and passages are not human-reviewed.",
            "Jaccard token overlap ignores meaning, relation, entity binding, and numerical semantics.",
            "The threshold is tuned on six development examples and evaluated once on held-out examples.",
            "No generalization or real-world answerability claim is justified.",
        ],
    }
    results = ROOT / "evaluation/results/phase-6-answerability.json"
    results.write_text(json.dumps(output, indent=2) + "\n")
    review = ROOT / "evaluation/annotations/answerability-review.csv"
    with review.open("w", newline="") as handle:
        fields = [
            "question_id",
            "split",
            "category",
            "question_text",
            "expected_answerability",
            "relevant_passage_ids",
            "required_facts",
            "expected_missing_facts",
            "evidence_passages",
            "review_status",
            "reviewer_notes",
            "disagreement",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    "question_id": row["question_id"],
                    "split": row["split"],
                    "category": row["category"],
                    "question_text": row["question_text"],
                    "expected_answerability": row["expected_answerability"],
                    "relevant_passage_ids": ";".join(row["relevant_passage_ids"]),
                    "required_facts": ";".join(row["required_facts"]),
                    "expected_missing_facts": ";".join(row["expected_missing_facts"]),
                    "evidence_passages": " || ".join(
                        f"{p['id']}: {p['text']}" for p in row["passages"]
                    ),
                    "review_status": "unreviewed",
                    "reviewer_notes": "",
                    "disagreement": "",
                }
            )
    print(
        json.dumps(
            {
                "results": str(results),
                "threshold": threshold,
                "held_out_metrics": metrics,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
