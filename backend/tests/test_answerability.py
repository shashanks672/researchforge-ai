import pytest

from app.research.answerability_evaluation import binary_metrics, select_f1_threshold
from app.research.sufficiency import EvidenceQuote, EvidenceSufficiencyResult, FactAssessment


def test_metrics_define_false_answers_and_abstentions_with_clear_denominators() -> None:
    result = binary_metrics(
        [True, True, False, False], [True, False, True, False], ["a", "b", "c", "d"]
    )
    assert result["confusion_matrix"] == {
        "actual_answerable": {"predicted_answerable": 1, "abstained": 1},
        "actual_unanswerable": {"predicted_answerable": 1, "abstained": 1},
    }
    assert result["false_answer_rate"] == 0.5
    assert result["false_answer_denominator"] == 2
    assert result["correct_abstention_rate"] == 0.5
    assert result["incorrect_abstention_rate"] == 0.5
    assert result["macro_f1"] == 0.5


def test_threshold_is_selected_from_development_labels_only() -> None:
    threshold = select_f1_threshold([0.8, 0.7, 0.2, 0.1], [True, True, False, False])
    assert threshold == 0.7


def test_sufficiency_schema_rejects_unknown_sources_and_inconsistent_status() -> None:
    item = EvidenceSufficiencyResult(
        question_id="Q1",
        question_text="What is the power output?",
        sufficient=False,
        status="PARTIAL",
        supporting_evidence_ids=["S1"],
        missing_information=["maximum output"],
        explanation="A passage supports only part of the question.",
        fact_assessments=[
            FactAssessment(
                fact="A supported portion",
                entity="",
                property="power",
                value="2",
                unit="kW",
                time_period="",
                scope="",
                negation="",
                status="SUPPORTED",
                evidence=[EvidenceQuote(source_id="S1", quote="power is 2 kW")],
            ),
            FactAssessment(
                fact="Maximum output",
                entity="",
                property="maximum output",
                value="",
                unit="",
                time_period="",
                scope="",
                negation="",
                status="MISSING",
                evidence=[],
            ),
        ],
    )
    item.validate_consistency({"S1"})
    try:
        item.validate_consistency({"S2"})
    except ValueError as exc:
        assert "unknown evidence" in str(exc)
    else:
        raise AssertionError("unknown evidence IDs must be rejected")
    duplicate = item.model_copy(
        update={
            "status": "SUFFICIENT",
            "sufficient": True,
            "missing_information": [],
            "fact_assessments": [item.fact_assessments[0], item.fact_assessments[0]],
        }
    )
    with pytest.raises(ValueError, match="must not duplicate"):
        duplicate.validate_consistency({"S1"})
