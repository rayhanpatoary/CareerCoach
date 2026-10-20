from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from interviews.schemas import StrictModel

MAX_PDF_BYTES = 3 * 1024 * 1024
MAX_BODY_BYTES = 4_300_000
MAX_TEXT = 30_000
LIMITATIONS = [
    "This is a review of extracted text. It cannot reliably assess PDF visual layout, columns, typography or graphics.",
    "Missing skills mean not evidenced in the submitted text, not proof that you lack them. AI suggestions may be wrong; verify every change.",
    "Never add qualifications, employers, dates, experience or achievement metrics that are not true. Example rewrites are suggestions, not verified facts.",
    "No hiring outcome or ATS ranking is predicted. Scanned/image-only PDFs need OCR elsewhere or pasted text; OCR is not performed here.",
]


class ReviewRequest(StrictModel):
    operation_id: UUID
    job_role: str = Field(min_length=2, max_length=100)
    job_description: str = Field(default="", max_length=8000)
    cv_text: str | None = Field(default=None, min_length=100, max_length=MAX_TEXT)
    pdf_base64: str | None = Field(default=None, max_length=4 * ((MAX_PDF_BYTES + 2) // 3))

    @model_validator(mode="after")
    def one_source(self):
        if (self.cv_text is None) == (self.pdf_base64 is None):
            raise ValueError("Provide exactly one PDF or pasted CV text.")
        return self


class Finding(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    evidence: str = Field(min_length=5, max_length=600)
    recommendation: str = Field(min_length=1, max_length=1000)


class MissingSkill(StrictModel):
    skill: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=700)
    evidence_status: Literal["not_evidenced", "partially_evidenced"]
    recommendation: str = Field(min_length=1, max_length=700)


class Rewrite(StrictModel):
    original: str = Field(min_length=5, max_length=800)
    suggested: str = Field(min_length=1, max_length=1200)
    rationale: str = Field(min_length=1, max_length=600)


class CvAnalysis(StrictModel):
    summary: str = Field(min_length=1, max_length=1800)
    strengths: list[Finding] = Field(max_length=5)
    weaknesses: list[Finding] = Field(max_length=5)
    missing_skills: list[MissingSkill] = Field(max_length=6)
    unclear_descriptions: list[Finding] = Field(max_length=5)
    content_errors: list[Finding] = Field(max_length=5)
    rewrites: list[Rewrite] = Field(max_length=4)
    practice_plan: list[str] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def bound_plan(self):
        if any(not value.strip() or len(value) > 1000 for value in self.practice_plan):
            raise ValueError("Practice steps must contain 1–1000 characters.")
        return self


class ReviewSummary(StrictModel):
    id: UUID
    job_role: str
    source: Literal["pdf", "text"]
    status: Literal["processing", "failed", "finished"]
    character_count: int
    page_count: int | None
    created_at: datetime
    expires_at: datetime


class Review(ReviewSummary):
    analysis: CvAnalysis | None
    limitations: list[str] = Field(default_factory=lambda:list(LIMITATIONS))


class ReviewHistory(StrictModel):
    items: list[ReviewSummary]
    next_cursor: UUID | None = None
