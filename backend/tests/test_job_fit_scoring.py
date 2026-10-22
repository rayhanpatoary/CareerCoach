"""Deterministic numerical scores and safe restoration, without NVIDIA calls."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from pydantic import ValidationError
from job_fit.scoring import calculate_score
from job_fit.schemas import Score
from job_fit.saved_analysis import restore_analysis
from job_fit.grounding import unassessed_job_sources,validate_job
from job_fit.job_description import parse_job_description
from job_fit.repository import JobFitRepository
from job_fit.service import JobFitService
from test_job_fit import request,mock_llm,parsed,JD
from interviews.repository import now
from datetime import timedelta


def criteria(*statuses,importance="mandatory"):
    return [SimpleNamespace(status=s,importance=importance) for s in statuses]


def analysis():
    repo=MagicMock();repo.claim.return_value=(None,uuid4());repo.complete.side_effect=lambda i,o,f,a:a
    return JobFitService(repo,mock_llm()).analyze(request(),"s"*43)


@pytest.mark.parametrize("statuses,expected",[
    (["matched"]*5,100),(["matched"]*4+["partial"],90),(["partial"]*4,50),
    (["partial"]+["not_evidenced"]*4,10),(["not_evidenced"]*4,0),(["uncertain"]*4,0)])
def test_alignment_from_perfect_to_zero_is_always_numerical(statuses,expected):
    score=calculate_score(criteria(*statuses))
    assert type(score.overall) is int and score.overall==expected
    assert score.assessed_count==len(statuses)
    assert score.uncertain_share==(100 if statuses[0]=="uncertain" else 0)


def test_weak_alignment_does_not_mean_low_assessment_confidence():
    score=calculate_score(criteria(*["not_evidenced"]*4))
    assert score.overall==0 and score.confidence=="high" and score.score_status=="complete"


@pytest.mark.parametrize("options",[{"layout_confidence":"low"},{"coverage_complete":False}])
def test_low_confidence_does_not_hide_an_evaluable_score(options):
    score=calculate_score(criteria("matched","partial","not_evidenced"),**options)
    assert score.overall==50 and score.confidence=="low" and score.score_status=="provisional"


def test_five_of_ten_requirements_is_not_eighty_percent_overall():
    score=calculate_score(criteria(*["matched"]*4,"not_evidenced"),coverage_complete=False,unassessed_count=5)
    assert score.evidence_coverage==80  # proportion of assessed criteria supported
    assert score.assessed_alignment==80
    assert score.assessment_coverage==50  # distinct denominator: five out of ten
    assert score.coverage_factor==.5 and score.overall==40
    assert score.scope=="known_groups" and score.unassessed_count==5
    assert sum(c.contribution for c in score.categories)==40


def test_unknown_coverage_is_explicitly_partial_scope_without_invented_counts():
    score=calculate_score(criteria(*["matched"]*4,"not_evidenced"),coverage_complete=False)
    assert score.overall==80 and score.score_status=="provisional"
    assert score.assessment_coverage is None and score.unassessed_count is None
    assert score.scope=="assessed_requirements" and "assessed-criteria alignment only" in score.reason


def test_posting_without_mandatory_or_preferred_categories_still_scores():
    for importance in ("preferred","alignment"):
        score=calculate_score(criteria("matched","partial",importance=importance))
        assert score.overall==75
        present=next(c for c in score.categories if c.category==importance)
        assert present.effective_weight==100 and present.contribution==75


def test_missing_preferred_weight_is_redistributed_and_uncertain_items_stay_zero():
    rows=criteria("matched","partial")+criteria("matched",importance="alignment")
    assert calculate_score(rows).overall==80
    rows=criteria("matched","uncertain","uncertain")
    assert calculate_score(rows).overall==33 and calculate_score(rows).confidence=="low"


def test_determinism_bounds_and_no_division_by_zero():
    for n in range(1,17):
        for status in ("matched","partial","not_evidenced","uncertain"):
            for missing in (0,1,7):
                rows=criteria(*[status]*n)
                kwargs=dict(coverage_complete=missing==0,unassessed_count=missing)
                first=calculate_score(rows,**kwargs)
                assert first==calculate_score(rows,**kwargs) and 0<=first.overall<=100
    with pytest.raises(ValueError,match="At least one"):calculate_score([])


@pytest.mark.parametrize("invalid",[None,-1,101,True])
def test_successful_score_contract_rejects_null_out_of_range_or_boolean(invalid):
    data=calculate_score(criteria("matched")).model_dump();data["overall"]=invalid
    with pytest.raises(ValidationError):Score.model_validate(data)


def test_known_gaps_come_from_actual_posting_sources_not_invented_skills():
    job=parsed();job.requirements.pop();job.context_source_ids=["jd_003"]
    validate_job(job,parse_job_description(JD))
    assert not job.coverage_complete
    assert unassessed_job_sources(job,parse_job_description(JD))==["jd_003"]
    assert job.requirements[0].label=="Python"  # no new criterion/classification created


def test_legacy_null_score_is_recomputed_without_raw_documents_or_ai(monkeypatch):
    raw=analysis().model_dump(mode="json");raw["score"]["overall"]=None;raw["score"]["rubric_version"]="job-fit-v1"
    raw["coverage_complete"]=False;raw.pop("unassessed_job_source_ids")
    before=deepcopy(raw)
    def forbidden(*args,**kwargs):raise AssertionError("Restoration must not call NVIDIA")
    monkeypatch.setattr("interviews.llm.NvidiaInterviewer.generate_json",forbidden)
    result=restore_analysis(raw)
    assert result.score.overall==53 and result.score.score_status=="provisional"
    assert result.score.confidence=="low" and result.score.scope=="assessed_requirements"
    assert result.score.assessment_coverage is None and raw==before


def test_saved_complete_and_legacy_zero_scores_are_reproducible():
    raw=analysis().model_dump(mode="json")
    assert restore_analysis(raw).model_dump(mode="json")==raw
    for r in raw["requirements"]:r["status"]="not_evidenced";r["evidence"]=[]
    raw["score"]["overall"]=None
    assert restore_analysis(raw).score.overall==0


def row_with(raw):
    return SimpleNamespace(id=uuid4(),job_role="Developer",source="text",status="finished",character_count=200,
        page_count=None,created_at=now(),expires_at=now()+timedelta(days=7),analysis=raw)


@pytest.mark.parametrize("damage",["empty","missing_classification","missing_evidence"])
def test_unrecoverable_legacy_report_gets_explicit_notice_not_fake_percentage(damage):
    raw=analysis().model_dump(mode="json")
    if damage=="empty":raw["requirements"]=[]
    elif damage=="missing_classification":raw["requirements"][0].pop("status")
    else:raw["requirements"][0]["evidence"]=[]
    view=JobFitRepository._view(row_with(raw))
    assert view.status=="finished" and view.analysis is None and "insufficient structured data" in view.legacy_notice
