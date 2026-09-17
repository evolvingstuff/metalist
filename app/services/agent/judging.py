"""Structured output rubric for explicitly invoked prompt regression runs."""

from pydantic import BaseModel, ConfigDict, Field


class CriterionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str = Field(min_length=1)
    passed: bool
    reason: str = Field(min_length=1)


class OutputJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteria: list[CriterionVerdict] = Field(min_length=1)
