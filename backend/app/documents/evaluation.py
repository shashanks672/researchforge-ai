"""Deterministic retrieval ranking metrics with explicit no-answer handling."""

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any


def retrieval_metrics(
    judgments: Mapping[str, Sequence[str]],
    rankings: Mapping[str, Sequence[str]],
    latencies_ms: Mapping[str, float],
    *,
    catalog_ids: set[str] | None = None,
    ks: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, Any]:
    """Compute binary relevance metrics; empty judgment lists mean no answer exists.

    No-answer queries are excluded from relevance metrics and counted separately.
    Dangling relevance labels are excluded and reported; unknown retrieved IDs are
    discarded and counted. Duplicate rankings count once at their first position.
    """
    if set(judgments) != set(rankings):
        raise ValueError("judgment and ranking query identifiers must match")
    if set(judgments) != set(latencies_ms):
        raise ValueError("latency and ranking query identifiers must match")
    if not ks or any(k < 1 for k in ks):
        raise ValueError("K values must be positive")
    answerable = [query for query, relevant in judgments.items() if relevant]
    no_answer = [query for query, relevant in judgments.items() if not relevant]
    per_k: dict[str, dict[str, float]] = {}
    reciprocal: list[float] = []
    ndcg_by_k: dict[int, list[float]] = {k: [] for k in ks}
    integrity = {
        "missing_relevant_ids": 0,
        "unknown_retrieved_ids": 0,
        "duplicate_retrieved_ids": 0,
    }
    no_answer_empty = 0
    for query in judgments:
        ranked = list(rankings[query])
        deduplicated = list(dict.fromkeys(ranked))
        integrity["duplicate_retrieved_ids"] += len(ranked) - len(deduplicated)
        if catalog_ids is not None:
            integrity["unknown_retrieved_ids"] += sum(
                item not in catalog_ids for item in deduplicated
            )
            deduplicated = [item for item in deduplicated if item in catalog_ids]
        if query in no_answer:
            no_answer_empty += not deduplicated
            continue
        requested = set(judgments[query])
        if catalog_ids is not None:
            dangling = requested - catalog_ids
            integrity["missing_relevant_ids"] += len(dangling)
            requested -= dangling
        if not requested:
            continue
        positions = {item: i + 1 for i, item in enumerate(deduplicated)}
        ranks = [positions[item] for item in requested if item in positions]
        reciprocal.append(1 / min(ranks) if ranks else 0.0)
        for k in ks:
            top = deduplicated[:k]
            hits = sum(item in requested for item in top)
            precision = hits / k
            recall = hits / len(requested)
            dcg = sum(
                1 / math.log2(rank + 1) for rank, item in enumerate(top, 1) if item in requested
            )
            ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(k, len(requested)) + 1))
            ndcg_by_k[k].append(dcg / ideal if ideal else 0.0)
            per_k.setdefault(str(k), {})
            per_k[str(k)].setdefault("precision", 0.0)
            per_k[str(k)].setdefault("recall", 0.0)
            per_k[str(k)]["precision"] += precision
            per_k[str(k)]["recall"] += recall
    for values in per_k.values():
        for metric in values:
            values[metric] /= len(answerable) if answerable else 1
    latencies = [float(latencies_ms[q]) for q in judgments]
    ordered_latency = sorted(latencies)
    p95 = None
    if len(ordered_latency) >= 20:
        p95 = ordered_latency[math.ceil(0.95 * len(ordered_latency)) - 1]
    return {
        "query_count": len(judgments),
        "answerable_query_count": len(answerable),
        "no_answer_query_count": len(no_answer),
        "no_answer_empty_result_rate": no_answer_empty / len(no_answer) if no_answer else None,
        "no_answer_nonempty_result_rate": (
            (len(no_answer) - no_answer_empty) / len(no_answer) if no_answer else None
        ),
        "metrics_on_answerable_queries_only": {
            "at_k": per_k,
            "mrr": statistics.mean(reciprocal) if reciprocal else 0.0,
            "ndcg": {
                str(k): statistics.mean(values) if values else 0.0
                for k, values in ndcg_by_k.items()
            },
        },
        "latency_ms": {
            "median": statistics.median(latencies) if latencies else None,
            "p95": p95,
            "p95_minimum_sample_size": 20,
        },
        "integrity": integrity,
    }
