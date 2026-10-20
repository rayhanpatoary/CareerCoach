from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Configuration(StrictModel):
    job_role: str = Field(min_length=2, max_length=100)
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    interview_type: Literal["technical", "behavioral", "mixed"] = "technical"
    question_count: Literal[3, 5, 8] = 5
    job_description: str = Field(default="", max_length=8000)


class StartRequest(Configuration):
    persistent: bool = False
    operation_id: UUID | None = None

    @model_validator(mode="after")
    def require_operation(self):
        if self.persistent and self.operation_id is None:
            raise ValueError("Persistent interviews require an operation_id")
        return self


class OperationRequest(StrictModel):
    operation_id: UUID


class AnswerRequest(OperationRequest):
    question_id: UUID
    answer: str = Field(min_length=1, max_length=6000)


class QuestionOutput(StrictModel):
    question: str = Field(min_length=10, max_length=1800)


class Turn(StrictModel):
    id: UUID
    position: int = Field(ge=1, le=8)
    question: str
    answer: str | None = None
    asked_at: datetime
    answered_at: datetime | None = None


class Category(StrictModel):
    score: int | None = Field(ge=0, le=100)
    evidence: str = Field(min_length=1, max_length=1000)


class Categories(StrictModel):
    accuracy: Category
    clarity: Category
    reasoning: Category
    completeness: Category
    depth: Category


class QuestionReview(StrictModel):
    question_id: UUID
    effective: str = Field(min_length=1, max_length=1500)
    missing: str = Field(min_length=1, max_length=1500)
    improvement: str = Field(min_length=1, max_length=1500)
    example_answer: str = Field(max_length=2500)


class EvaluationOutput(StrictModel):
    categories: Categories
    summary: str = Field(min_length=1, max_length=1800)
    strengths: list[str] = Field(max_length=6)
    improvements: list[str] = Field(max_length=6)
    knowledge_gaps: list[str] = Field(max_length=6)
    recommendations: list[str] = Field(max_length=6)
    practice_plan: list[str] = Field(min_length=1, max_length=5)
    reviews: list[QuestionReview] = Field(max_length=8)

    @model_validator(mode="after")
    def bound_items(self):
        for name in ("strengths", "improvements", "knowledge_gaps", "recommendations", "practice_plan"):
            if any(not text.strip() or len(text) > 1500 for text in getattr(self, name)):
                raise ValueError("Feedback items must contain 1–1500 characters")
        return self


WEIGHTS = {"accuracy": 35, "clarity": 20, "reasoning": 20, "completeness": 15, "depth": 10}


def weighted_score(categories: Categories) -> tuple[int | None, int]:
    """Unscorable criteria are excluded; report the scored evidence coverage."""
    scored = [(getattr(categories, key).score, weight) for key, weight in WEIGHTS.items()
              if getattr(categories, key).score is not None]
    coverage = sum(weight for _, weight in scored)
    if not coverage:
        return None, 0
    score = sum(Decimal(value) * weight for value, weight in scored) / coverage
    return int(score.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), coverage


class Evaluation(EvaluationOutput):
    overall_score: int | None = Field(ge=0, le=100)
    evidence_coverage: int = Field(ge=0, le=100)
    partial: bool
    answered_count: int
    rubric: dict[str, int]


class InterviewState(Configuration):
    id: UUID
    status: Literal["generating_question", "in_progress", "completed", "evaluating", "finished"]
    question: str | None
    turns: list[Turn]
    answered_count: int
    started_at: datetime
    completed_at: datetime | None
    expires_at: datetime
    feedback: Evaluation | None = None
    busy: bool = False
