from typing import Literal
from uuid import UUID
from pydantic import Field,field_validator,ValidationError
from interviews.schemas import StrictModel
from cv.schemas import ReviewRequest, ReviewSummary, ExtractionInfo,MAX_EVIDENCE_CHARACTERS
from cv.grounding import GroundedRewrite

Importance=Literal["mandatory","preferred","alignment"]
Status=Literal["matched","partial","not_evidenced","uncertain"]
Category=Literal["technical","tools","experience","education","responsibility","domain","communication","language","seniority"]
ActionKind=Literal["improve_wording","add_truthful_evidence","develop_skill","clarify_experience"]


class JobFitRequest(ReviewRequest):
    job_description: str = Field(min_length=100,max_length=8000)
    company: str = Field(default="",max_length=100)


class Evidence(StrictModel):
    source_id: str = Field(min_length=1,max_length=60)
    quote: str = Field(min_length=2,max_length=MAX_EVIDENCE_CHARACTERS)
    page: int | None = None
    section: str | None = None


class JobCriterion(StrictModel):
    label: str = Field(min_length=2,max_length=120)
    category: Category
    importance: Importance
    jd_source_id: str = Field(min_length=1,max_length=60)
    jd_quote: str = Field(min_length=2,max_length=350)

    @field_validator("category",mode="before")
    @classmethod
    def category_alias(cls,value):
        # Normalize known taxonomy names, never source facts or quoted evidence.
        return {"soft_skills":"communication","soft_skill":"communication","communication_skills":"communication",
            "technical_skills":"technical","technical_skill":"technical","tool":"tools","qualifications":"education",
            "responsibilities":"responsibility","work_experience":"experience","languages":"language"}.get(value,value) if isinstance(value,str) else value


class CriterionMatch(StrictModel):
    requirement_index: int = Field(ge=0,le=15)
    status: Status
    evidence: list[Evidence] = Field(default_factory=list,max_length=2)
    action_kind: ActionKind
    suggested_action: str = Field(min_length=10,max_length=450)


class Requirement(JobCriterion):
    status: Status
    evidence: list[Evidence] = Field(default_factory=list,max_length=2)
    action_kind: ActionKind
    suggested_action: str = Field(min_length=10,max_length=450)


class ParsedJob(StrictModel):
    language: Literal["en","de","mixed","und"]
    requirements: list[JobCriterion] = Field(max_length=16)
    context_source_ids: list[str] = Field(max_length=100)
    coverage_complete: bool


class Improvement(StrictModel):
    horizon: Literal["immediate","strengthen","longer_term"]
    requirement_index: int = Field(ge=0,le=15)
    action: str = Field(min_length=10,max_length=450)


class ModelOutput(StrictModel):
    language: Literal["en","de","mixed","und"]
    requirements: list[Requirement] = Field(min_length=1,max_length=16)
    context_source_ids: list[str] = Field(max_length=100)
    coverage_complete: bool
    improvements: list[Improvement] = Field(min_length=1,max_length=6)
    rewrites: list[GroundedRewrite] = Field(default_factory=list,max_length=2)

    @field_validator("rewrites",mode="before")
    @classmethod
    def optional_well_formed_rewrites(cls,value):
        # Optional advice must not invalidate otherwise grounded core matching.
        # Malformed suggestions are omitted, never repaired into invented facts.
        if not isinstance(value,list):return []
        accepted=[]
        for item in value[:2]:
            try:accepted.append(GroundedRewrite.model_validate(item))
            except ValidationError:continue
        return accepted


class ClassifiedMatches(StrictModel):
    matches: list[CriterionMatch] = Field(min_length=1,max_length=16)
    improvements: list[Improvement] = Field(min_length=1,max_length=6)
    rewrites: list[GroundedRewrite] = Field(default_factory=list,max_length=2)

    _optional_rewrites=field_validator("rewrites",mode="before")(ModelOutput.optional_well_formed_rewrites.__func__)


class AssessedRequirement(Requirement):
    id: str
    explanation: str


class ScoreCategory(StrictModel):
    category: Importance
    count: int
    matched: int
    partial: int
    not_evidenced: int
    uncertain: int
    base_weight: int
    effective_weight: float
    score: float | None
    contribution: float


class Score(StrictModel):
    overall: int = Field(ge=0,le=100,strict=True)
    score_status: Literal["complete","provisional"]
    confidence: Literal["high","moderate","low"]
    confidence_reasons: list[str]
    scope: Literal["full_posting","known_groups","assessed_requirements"]
    assessed_count: int = Field(ge=1)
    unassessed_count: int | None = Field(ge=0)
    assessment_coverage: float | None = Field(ge=0,le=100)
    assessed_alignment: float = Field(ge=0,le=100)
    coverage_factor: float = Field(ge=0,le=1)
    reason: str
    categories: list[ScoreCategory]
    evidence_coverage: float
    uncertain_share: float
    rubric_version: str = "job-fit-v2"
    meaning: str = "Estimated alignment of supplied CV evidence to stated job criteria; not hiring, ATS or interview-selection probability."


class JobFitAnalysis(StrictModel):
    company: str
    language: Literal["en","de","mixed","und"]
    requirements: list[AssessedRequirement] = Field(min_length=1)
    score: Score
    improvements: list[Improvement]
    rewrites: list[GroundedRewrite]
    extraction: ExtractionInfo
    coverage_complete: bool
    warnings: list[str]
    # None means an older report did not retain its gap inventory. Empty means
    # the new audit found no omitted groups; false coverage may still be unknown.
    unassessed_job_source_ids: list[str] | None = Field(default=None,max_length=80)


LIMITATIONS=[
    "Not evidenced describes the supplied document, not your actual ability or knowledge.",
    "Matching is an AI coaching interpretation. Verified quotes do not independently verify CV claims or prove every semantic inference.",
    "The score is a documented evidence-alignment estimate, not candidate quality, hiring probability or ATS approval.",
    "PDF coordinates help recover reading order, but do not establish visual design quality. Verify the cited passages.",
    "History is private to this browser session for 7 days. Feedback quotes are personal data; raw CVs and complete job descriptions are not stored.",
]


class JobFitSummary(ReviewSummary):
    pass


class JobFitReview(JobFitSummary):
    analysis: JobFitAnalysis | None
    limitations: list[str] = Field(default_factory=lambda:list(LIMITATIONS))
    legacy_notice: str | None = None


class JobFitHistory(StrictModel):
    items: list[JobFitSummary]
    next_cursor: UUID | None = None
