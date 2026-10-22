"""Reproductions for stage-specific contract failures; synthetic source data only."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from cv.document import text_document
from cv.grounding import GroundingError,verify_source_quote
from cv.schemas import Finding,MAX_EVIDENCE_CHARACTERS
from job_fit.schemas import JobCriterion,CriterionMatch,Evidence,ParsedJob,ClassifiedMatches
from job_fit.job_description import parse_job_description
from job_fit.grounding import validate_matches
from job_fit.service import JobFitService
from test_job_fit import request,output,parsed,classified,JD,mock_llm


@pytest.mark.parametrize("alias,expected",[("soft_skills","communication"),("communication_skills","communication"),
    ("technical_skills","technical"),("work_experience","experience"),("responsibilities","responsibility"),("qualifications","education")])
def test_known_category_aliases_do_not_change_job_facts(alias,expected):
    item=parsed().requirements[0].model_dump();item["category"]=alias
    result=JobCriterion.model_validate(item)
    assert result.category==expected
    assert result.jd_source_id==item["jd_source_id"] and result.jd_quote==item["jd_quote"] and result.label==item["label"]


def test_unknown_categories_still_fail_structured_validation():
    item=parsed().requirements[0].model_dump();item["category"]="invented_candidate_quality"
    with pytest.raises(ValidationError):JobCriterion.model_validate(item)


def test_reported_posting_headings_preserve_responsibilities_and_profile():
    clauses=parse_job_description((Path(__file__).parent/"fixtures"/"job_fit_printing.txt").read_text(encoding="utf-8"))
    assert clauses[0].heading and clauses[0].importance_hint=="alignment"
    profile=next(i for i,c in enumerate(clauses) if c.text=="Your Profile")
    assert all(c.importance_hint=="alignment" for c in clauses[1:profile])
    assert clauses[profile].heading and all(c.importance_hint=="mandatory" for c in clauses[profile+1:])
    assert all(not c.heading for c in clauses[1:profile])


def test_valid_quote_accepted_by_cv_reviewer_is_also_accepted_by_job_fit():
    source="Python developer. "+"Built reliable software and documented actual contributions. "*7
    quote=source[:450]
    assert 300<len(quote)<MAX_EVIDENCE_CHARACTERS
    doc=text_document(source)
    finding=Finding(title="Relevant technical skills",evidence=quote,recommendation="Clarify project scope.",source_id="text_001")
    verify_source_quote(doc,finding.source_id,finding.evidence)
    value=output();value.requirements[0].evidence=[Evidence(source_id="text_001",quote=quote)]
    value.requirements[1].status="not_evidenced";value.requirements[1].evidence=[]
    result,_=validate_matches(value,doc,parse_job_description(JD))
    assert result.requirements[0].status=="matched"


def test_missing_skills_need_no_cv_quote_but_positive_matches_still_do():
    data=classified().model_dump();data["matches"][2].pop("evidence")
    match=ClassifiedMatches.model_validate(data)
    assert match.matches[2].status=="not_evidenced" and match.matches[2].evidence==[]
    value=output();value.requirements[0].evidence=[]
    with pytest.raises(GroundingError) as exc:validate_matches(value,text_document("Python developer. "*20),parse_job_description(JD))
    assert exc.value.code=="positive_match_requires_cv_evidence"


@pytest.mark.parametrize("stage",["job_requirements","cv_matching"])
def test_failure_reports_correct_stage_without_blame_or_provider_content(stage):
    req=request();repo=MagicMock();repo.claim.return_value=(None,uuid4());llm=mock_llm();normal=llm.generate_json.side_effect
    def generate(instructions,data,schema,**kwargs):
        if (schema is ParsedJob)==(stage=="job_requirements"):
            try:raise GroundingError("quote_not_in_cited_source",path=("matches",0,"evidence",0,"quote"))
            except GroundingError as cause:raise HTTPException(502,"Private provider response") from cause
        return normal(instructions,data,schema,**kwargs)
    llm.generate_json.side_effect=generate
    with pytest.raises(HTTPException) as exc:JobFitService(repo,llm).analyze(req,"a"*43)
    assert exc.value.headers["X-Analysis-Stage"]==stage
    assert exc.value.headers["X-Analysis-Code"]=="quote_not_in_cited_source"
    assert "Private provider response" not in exc.value.detail and "extraction" not in exc.value.detail
    repo.complete.assert_not_called();repo.release.assert_called_once()


def test_corrective_retry_receives_precise_cv_path_and_copy_instruction(caplog):
    from interviews.llm import NvidiaInterviewer
    from test_interviews import mock_client
    good=classified();bad=good.model_copy(deep=True);bad.matches[0].evidence[0].source_id="private_invented_source"
    client=mock_client("")
    response=lambda v:SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=v.model_dump_json()))])
    client.chat.completions.create.side_effect=[response(bad),response(good)]
    def validate(value):
        combined=output()
        for item,match in zip(combined.requirements,value.matches):item.status,item.evidence=match.status,match.evidence
        from test_job_fit import CV
        validate_matches(combined,text_document(CV),parse_job_description(JD));return value
    NvidiaInterviewer(lambda:client).generate_json("Compare",{},ClassifiedMatches,validator=validate)
    repair=client.chat.completions.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "matches.0.evidence.0.source_id" in repair and "never a job-description source ID" in repair
    assert "private_invented_source" not in caplog.text


def test_cv_paraphrase_is_still_rejected_using_shared_quote_verifier():
    value=output();value.requirements[0].evidence[0].quote="Extensive Python leadership experience"
    with pytest.raises(GroundingError) as exc:validate_matches(value,text_document("Python developer. "*20),parse_job_description(JD))
    assert exc.value.code=="quote_not_in_cited_source" and exc.value.path==("matches",0,"evidence",0,"quote")
