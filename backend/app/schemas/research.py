from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ResearchMode(StrEnum):
    WEB = "web"
    DOCUMENTS = "documents"
    COMBINED = "combined"


class ResearchBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=2, ge=1, le=5)
    max_sources: int = Field(default=8, ge=1, le=20)
    max_duration_seconds: int = Field(default=120, ge=10, le=300)


class ResearchRequest(BaseModel):
    """Initial contract only; submitting or executing runs starts in later phases."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=10, max_length=4000)
    mode: ResearchMode = ResearchMode.WEB
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)

    @field_validator("document_ids")
    @classmethod
    def unique_documents(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("Document IDs must be unique")
        return values

    @model_validator(mode="after")
    def validate_mode(self) -> Self:
        if self.mode in {ResearchMode.DOCUMENTS, ResearchMode.COMBINED} and not self.document_ids:
            raise ValueError("Document research requires at least one document ID")
        if self.mode == ResearchMode.WEB and self.document_ids:
            raise ValueError("Use combined mode when including documents")
        return self
