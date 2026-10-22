"""Read-time v2 scoring for private saved JSON; never writes or calls NVIDIA."""
from .schemas import AssessedRequirement,JobFitAnalysis
from cv.schemas import ExtractionInfo
from .scoring import calculate_score


def restore_analysis(raw):
    if not isinstance(raw,dict):raise ValueError("Legacy feedback is unavailable")
    requirements=[AssessedRequirement.model_validate(r) for r in raw.get("requirements",[])]
    if any(r.status in ("matched","partial") and not r.evidence for r in requirements):
        raise ValueError("Legacy positive classifications lack their saved evidence")
    if len({r.id for r in requirements})!=len(requirements):
        raise ValueError("Legacy requirement identifiers are duplicated")
    extraction=ExtractionInfo.model_validate(raw.get("extraction"))
    complete=raw.get("coverage_complete")
    if type(complete) is not bool:raise ValueError("Legacy coverage is unavailable")
    sources=raw.get("unassessed_job_source_ids")
    if sources is not None and (not isinstance(sources,list) or any(not isinstance(v,str) for v in sources)):
        raise ValueError("Legacy gap inventory is invalid")
    score=calculate_score(requirements,coverage_complete=complete,layout_confidence=extraction.confidence,
        unassessed_count=len(set(sources)) if sources is not None else None)
    return JobFitAnalysis.model_validate({**raw,"score":score.model_dump(mode="json")})
