import pytest

from app.documents.evaluation import retrieval_metrics


def test_retrieval_metrics_multiple_relevant_and_no_answer_queries() -> None:
    result = retrieval_metrics(
        {"q1": ["a", "b"], "q2": []},
        {"q1": ["x", "b", "a"], "q2": []},
        {"q1": 10.0, "q2": 30.0},
        catalog_ids={"a", "b", "x"},
    )
    metrics = result["metrics_on_answerable_queries_only"]
    assert metrics["at_k"]["1"]["precision"] == 0
    assert metrics["at_k"]["3"]["precision"] == pytest.approx(2 / 3)
    assert metrics["at_k"]["3"]["recall"] == 1
    assert metrics["mrr"] == pytest.approx(0.5)
    assert result["no_answer_empty_result_rate"] == 1
    assert result["no_answer_nonempty_result_rate"] == 0
    assert result["answerable_query_count"] == 1


def test_metrics_report_deleted_mismatched_and_duplicate_ids() -> None:
    result = retrieval_metrics(
        {"q": ["deleted", "valid"]},
        {"q": ["missing", "valid", "valid"]},
        {"q": 1.0},
        catalog_ids={"valid"},
    )
    assert result["integrity"] == {
        "missing_relevant_ids": 1,
        "unknown_retrieved_ids": 1,
        "duplicate_retrieved_ids": 1,
    }
    assert result["metrics_on_answerable_queries_only"]["at_k"]["1"]["recall"] == 1


def test_p95_latency_requires_twenty_samples() -> None:
    small = retrieval_metrics(
        {f"q{i}": [] for i in range(3)},
        {f"q{i}": [] for i in range(3)},
        {f"q{i}": float(i) for i in range(3)},
    )
    assert small["latency_ms"]["median"] == 1
    assert small["latency_ms"]["p95"] is None
    many = retrieval_metrics(
        {f"q{i}": [] for i in range(20)},
        {f"q{i}": [] for i in range(20)},
        {f"q{i}": float(i + 1) for i in range(20)},
    )
    assert many["latency_ms"]["p95"] == 19


@pytest.mark.parametrize(
    ("judgments", "rankings", "latencies"),
    [({"a": ["x"]}, {}, {"a": 1}), ({"a": []}, {"a": []}, {})],
)
def test_mismatched_query_ids_are_rejected(
    judgments: dict[str, list[str]],
    rankings: dict[str, list[str]],
    latencies: dict[str, float],
) -> None:
    with pytest.raises(ValueError):
        retrieval_metrics(judgments, rankings, latencies)
