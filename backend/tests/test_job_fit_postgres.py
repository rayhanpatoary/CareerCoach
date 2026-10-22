"""Uses only the guarded local *_test database fixture; never hosted Supabase."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import text,update
from sqlalchemy.orm import Session
from test_postgres import engine  # noqa: F401 -- shared guarded pytest fixture
from test_job_fit import request,mock_llm,CV,JD
from job_fit.repository import JobFitRepository
from job_fit.service import JobFitService
from job_fit.tables import JobFitRecord
from interviews.repository import now
from unittest.mock import MagicMock


@pytest.fixture
def repository(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE career_coach.job_fit_analyses, career_coach.rate_buckets"))
    return JobFitRepository(engine)


def start(repository):
    owner="j"*43;req=request();llm=mock_llm()
    return owner,req,llm,JobFitService(repository,llm)


def test_persistence_duplicate_retry_owner_isolation_and_deletion(repository):
    owner,req,llm,service=start(repository)
    result=service.analyze(req,owner)
    assert result.analysis.score.overall==53
    assert service.analyze(req,owner)==result and llm.generate_json.call_count==2
    assert repository.read(result.id,owner)==result
    assert repository.history(owner).items[0].id==result.id
    assert not repository.history("x"*43).items
    for method in (repository.read,repository.remove):
        with pytest.raises(HTTPException) as exc:method(result.id,"x"*43)
        assert exc.value.status_code==404
    with Session(repository.engine) as db:
        row=db.get(JobFitRecord,result.id)
        assert row.owner_hash!=owner and CV not in str(row.analysis) and JD not in str(row.analysis)
        assert not hasattr(row,"cv_text") and not hasattr(row,"job_description")
    changed=req.model_copy(update={"company":"Changed company"})
    with pytest.raises(HTTPException) as exc:service.analyze(changed,owner)
    assert exc.value.status_code==409
    repository.remove(result.id,owner)
    assert not repository.history(owner).items
    with pytest.raises(HTTPException):repository.read(result.id,owner)


def test_legacy_null_score_restores_on_read_without_backfill_or_llm(repository):
    owner,req,llm,service=start(repository);original=service.analyze(req,owner)
    with repository.engine.begin() as db:
        with Session(bind=db) as session:
            row=session.get(JobFitRecord,original.id);raw=dict(row.analysis)
        raw["score"]={**raw["score"],"overall":None,"rubric_version":"job-fit-v1"}
        raw["coverage_complete"]=False;raw.pop("unassessed_job_source_ids")
        db.execute(update(JobFitRecord).where(JobFitRecord.id==original.id).values(analysis=raw))
    restored=repository.read(original.id,owner)
    assert restored.analysis.score.overall==53 and restored.analysis.score.score_status=="provisional"
    assert restored.analysis.score.scope=="assessed_requirements" and restored.analysis.score.assessment_coverage is None
    assert service.analyze(req,owner)==restored and llm.generate_json.call_count==2
    with Session(repository.engine) as db:
        assert db.get(JobFitRecord,original.id).analysis["score"]["overall"] is None
    with pytest.raises(HTTPException) as exc:repository.read(original.id,"x"*43)
    assert exc.value.status_code==404


def test_known_coverage_gaps_persist_as_metadata_and_reduce_score(repository):
    from test_job_fit import parsed,classified
    from job_fit.schemas import ParsedJob
    owner,req,llm,service=start(repository)
    def generate(instructions,data,schema,**kwargs):
        if schema is ParsedJob:
            value=parsed();value.requirements.pop();value.context_source_ids=["jd_003"]
        else:value=classified();value.matches.pop()
        return kwargs["validator"](value)
    llm.generate_json.side_effect=generate
    result=service.analyze(req,owner)
    assert result.analysis.unassessed_job_source_ids==["jd_003"]
    assert result.analysis.score.overall==50 and result.analysis.score.assessed_alignment==75
    assert result.analysis.score.unassessed_count==1 and result.analysis.score.assessment_coverage==66.67
    assert repository.read(result.id,owner)==result


def test_unrecoverable_legacy_report_keeps_owner_checks_and_deletion(repository):
    owner,req,llm,service=start(repository);result=service.analyze(req,owner)
    with repository.engine.begin() as db:
        db.execute(update(JobFitRecord).where(JobFitRecord.id==result.id).values(analysis={"requirements":[]}))
    restored=repository.read(result.id,owner)
    assert restored.analysis is None and "insufficient structured data" in restored.legacy_notice
    assert repository.history(owner).items[0].id==result.id
    with pytest.raises(HTTPException):repository.read(result.id,"x"*43)
    repository.remove(result.id,owner)
    assert not repository.history(owner).items


def test_concurrent_claim_only_one_owner_and_stale_lease_fenced(repository):
    owner="k"*43;analysis_id=uuid4()
    def claim():
        try:return repository.claim(analysis_id,owner,"h"*64,"Developer","text",200,None)[1]
        except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(lambda _:claim(),range(2)))
    assert results.count(409)==1
    old=next(v for v in results if v!=409)
    with repository.engine.begin() as db:
        db.execute(update(JobFitRecord).where(JobFitRecord.id==analysis_id).values(lease_until=now()-timedelta(seconds=1)))
    new=claim();assert new!=old and new!=409
    repository.release(analysis_id,owner,old)
    assert repository.read(analysis_id,owner).status=="processing"
    with pytest.raises(HTTPException) as exc:repository.complete(analysis_id,owner,old,MagicMock())
    assert exc.value.status_code==409
    repository.remove(analysis_id,owner)
    repository.release(analysis_id,owner,new)
    assert not repository.history(owner).items


def test_expiry_cleanup_pagination_and_feature_rate_limits(repository):
    owner,req,llm,service=start(repository)
    first=service.analyze(req,owner);second=service.analyze(request(),owner)
    history=repository.history(owner,limit=1)
    assert len(history.items)==1 and history.next_cursor
    assert repository.history(owner,limit=1,cursor=history.next_cursor).items[0].id==first.id
    with repository.engine.begin() as db:
        db.execute(update(JobFitRecord).where(JobFitRecord.id==first.id).values(expires_at=now()-timedelta(seconds=1)))
    with pytest.raises(HTTPException):repository.read(first.id,owner)
    repository.cleanup()
    assert [v.id for v in repository.history(owner).items]==[second.id]
    for _ in range(8):service.analyze(request(),owner)
    with pytest.raises(HTTPException) as exc:service.analyze(request(),owner)
    assert exc.value.status_code==429 and exc.value.headers["Retry-After"]=="3600"
