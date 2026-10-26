"""Metrics for binary evidence answerability decisions; not model-quality claims."""

from collections.abc import Sequence


def binary_metrics(
    expected: Sequence[bool], predicted: Sequence[bool], categories: Sequence[str]
) -> dict[str, object]:
    if not expected or len(expected) != len(predicted) or len(expected) != len(categories):
        raise ValueError(
            "expected labels, predictions, and categories must be non-empty and aligned"
        )
    tp = sum(a and p for a, p in zip(expected, predicted, strict=True))
    tn = sum(not a and not p for a, p in zip(expected, predicted, strict=True))
    fp = sum(not a and p for a, p in zip(expected, predicted, strict=True))
    fn = sum(a and not p for a, p in zip(expected, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    negative_precision = tn / (tn + fn) if tn + fn else 0.0
    negative_recall = tn / (tn + fp) if tn + fp else 0.0
    f1_positive = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    f1_negative = (
        2 * negative_precision * negative_recall / (negative_precision + negative_recall)
        if negative_precision + negative_recall
        else 0.0
    )
    per_category: dict[str, dict[str, int]] = {}
    for category, actual, guess in zip(categories, expected, predicted, strict=True):
        row = per_category.setdefault(category, {"samples": 0, "correct": 0, "false_answers": 0})
        row["samples"] += 1
        row["correct"] += int(actual == guess)
        row["false_answers"] += int(not actual and guess)
    negatives = sum(not label for label in expected)
    positives = len(expected) - negatives
    return {
        "sample_count": len(expected),
        "confusion_matrix": {
            "actual_answerable": {"predicted_answerable": tp, "abstained": fn},
            "actual_unanswerable": {"predicted_answerable": fp, "abstained": tn},
        },
        "accuracy": (tp + tn) / len(expected),
        "answerable_precision": precision,
        "answerable_recall": recall,
        "macro_f1": (f1_positive + f1_negative) / 2,
        "false_answer_rate": fp / negatives if negatives else None,
        "false_answer_denominator": negatives,
        "correct_abstention_rate": tn / negatives if negatives else None,
        "incorrect_abstention_rate": fn / positives if positives else None,
        "per_category": per_category,
    }


def select_f1_threshold(scores: Sequence[float], expected: Sequence[bool]) -> float:
    """Choose the smallest development threshold maximizing positive-class F1."""
    if len(scores) != len(expected) or not scores:
        raise ValueError("development scores and labels must be non-empty and aligned")
    candidates = sorted({min(scores) - 1e-9, *scores, max(scores) + 1e-9})
    best_threshold, best_f1 = candidates[0], -1.0
    for threshold in candidates:
        predicted = [score >= threshold for score in scores]
        tp = sum(a and p for a, p in zip(expected, predicted, strict=True))
        fp = sum(not a and p for a, p in zip(expected, predicted, strict=True))
        fn = sum(a and not p for a, p in zip(expected, predicted, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if f1 > best_f1:
            best_threshold, best_f1 = threshold, f1
    return best_threshold


def lexical_overlap(question: str, passages: Sequence[str]) -> float:
    """Uncalibrated Jaccard token overlap; included only as a weak baseline."""
    import re

    stop = {
        "what",
        "which",
        "when",
        "where",
        "how",
        "does",
        "the",
        "and",
        "for",
        "with",
        "from",
        "about",
    }
    query = set(re.findall(r"[a-z0-9]+", question.casefold())) - stop
    if not query:
        return 0.0
    scores = []
    for passage in passages:
        words = set(re.findall(r"[a-z0-9]+", passage.casefold())) - stop
        union = query | words
        scores.append(len(query & words) / len(union) if union else 0.0)
    return max(scores, default=0.0)
