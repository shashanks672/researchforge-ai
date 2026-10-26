from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.research import ResearchBudget, ResearchMode, ResearchRequest


def test_question_is_trimmed_and_budget_is_bounded() -> None:
    request = ResearchRequest(question="  How does retrieval improve grounding?  ")
    assert request.question == "How does retrieval improve grounding?"
    assert request.mode == ResearchMode.WEB
    assert request.budget.max_iterations == 2


@pytest.mark.parametrize("question", ["", " " * 20, "short", "q" * 4001])
def test_invalid_question_rejected(question: str) -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(question=question)


@pytest.mark.parametrize("iterations", [0, 6])
def test_unbounded_iterations_rejected(iterations: int) -> None:
    with pytest.raises(ValidationError):
        ResearchBudget(max_iterations=iterations)


def test_document_mode_requires_references() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(question="Compare these papers please", mode=ResearchMode.COMBINED)
    document_id = uuid4()
    request = ResearchRequest(
        question="Compare these papers please",
        mode=ResearchMode.DOCUMENTS,
        document_ids=[document_id],
    )
    assert request.document_ids == [document_id]
    with pytest.raises(ValidationError):
        ResearchRequest(
            question="Compare these papers please",
            mode=ResearchMode.DOCUMENTS,
            document_ids=[document_id, document_id],
        )


def test_unrecognized_execution_parameters_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest.model_validate({"question": "Explain grounded research", "shell": "whoami"})
