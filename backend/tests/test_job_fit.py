"""Synthetic job-fit contracts. No personal CVs or outbound NVIDIA requests."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cv.document import text_document
from cv.grounding import GroundingError
from interviews.repository import now
from job_fit.job_description import parse_job_description
from job_fit.grounding import validate_matches
from job_fit.schemas import JobFitRequest,ModelOutput,JobFitReview,ParsedJob,ClassifiedMatches,JobCriterion
from job_fit.scoring import calculate_score
from job_fit.service import JobFitService
from job_fit.routes import get_repository,get_service
from main import app

CV="Python developer building reliable APIs with FastAPI and SQL Server. Developed automated tests and documented deployment procedures. Collaborated with designers on customer workflows."
JD="Python is required for backend development.\nPostgreSQL is required for relational data.\nDocker is preferred for packaging services."


def request(**kwargs):
    return JobFitRequest(operation_id=uuid4(),job_role="Python Developer",job_description=JD,**(kwargs or {"cv_text":CV}))


def output():
    rows=[]
    for i,(label,importance,status,evidence) in enumerate([
        ("Python","mandatory","matched",[dict(source_id="text_001",quote="Python developer building reliable APIs")]),
        ("PostgreSQL","mandatory","partial",[dict(source_id="text_001",quote="FastAPI and SQL Server")]),
        ("Docker","preferred","not_evidenced",[])]):
        rows.append(dict(label=label,category="technical",importance=importance,jd_source_id=f"jd_{i+1:03d}",
            jd_quote=JD.splitlines()[i],status=status,evidence=evidence,action_kind="clarify_experience",
            suggested_action=f"Clarify your actual {label} experience, if applicable."))
    return ModelOutput(language="en",requirements=rows,context_source_ids=[],coverage_complete=True,
        improvements=[dict(horizon="strengthen",requirement_index=1,action="Practice PostgreSQL queries using your relational database foundation.")],rewrites=[])


def parsed(value=None):
    value=value or output()
    return ParsedJob(**value.model_dump(exclude={"requirements","improvements","rewrites"}),
        requirements=[r.model_dump(include=set(JobCriterion.model_fields)) for r in value.requirements])


def classified(value=None):
    value=value or output()
    return ClassifiedMatches(matches=[dict(requirement_index=i,**r.model_dump(include={"status","evidence","action_kind","suggested_action"})) for i,r in enumerate(value.requirements)],
        improvements=value.improvements,rewrites=value.rewrites)


def mock_llm():
    llm=MagicMock()
    llm.generate_json.side_effect=lambda instructions,data,schema,**kw:kw["validator"](parsed() if schema is ParsedJob else classified())
    return llm


def saved(req,status="finished",analysis=None):
    return JobFitReview(id=req.operation_id,job_role=req.job_role,source="text",status=status,character_count=len(CV),
        page_count=None,created_at=now(),expires_at=now()+timedelta(days=7),analysis=analysis)


def validate(value=None,jd=JD,cv=CV):return validate_matches(value or output(),text_document(cv),parse_job_description(jd))


def test_english_german_headings_preserve_importance_and_do_not_count_as_requirements():
    clauses=parse_job_description("Required skills:\nPython\nPreferred qualifications:\nDocker\nResponsibilities:\nBuild services\nWir bieten:\nFlexible Arbeitszeiten")
    assert [c.importance_hint for c in clauses]==["mandatory","mandatory","preferred","preferred","alignment","alignment",None,None]
    assert not any(c.explicit_requirement for c in clauses)
    de=parse_job_description("Anforderungen:\nPython ist erforderlich.\nDocker ist wünschenswert.\nAufgaben:\nAPIs entwickeln.")
    assert de[1].importance_hint=="mandatory" and de[2].importance_hint=="preferred" and de[4].importance_hint=="alignment"
    assert de[1].explicit_requirement and de[2].explicit_requirement


def test_parser_never_truncates_long_sources():
    text="Python "*180
    parts=parse_job_description(text)
    assert all(len(c.text)<=500 for c in parts)
    assert " ".join(c.text for c in parts)==text.strip()


def test_mixed_importance_sentence_is_not_forced_to_one_category():
    clause=parse_job_description("Python is required, but Docker is preferred.")[0]
    assert clause.importance_hint is None and clause.explicit_requirement


def test_generic_coaching_prefix_can_only_normalize_to_an_exact_job_phrase():
    value=output();value.requirements[0].label="Develop wartbare APIs";value.requirements[0].category="responsibility"
    value.requirements[0].jd_quote="Entwickle wartbare APIs für interne Anwendungen."
    jd=JD.replace(JD.splitlines()[0],value.requirements[0].jd_quote)
    value.requirements[0].importance="alignment"
    value,warnings=validate(value,jd=jd)
    assert value.requirements[0].label=="wartbare APIs" and "requirement_label_source_normalized" in warnings
    value.requirements[0].label="Develop Kubernetes"
    with pytest.raises(GroundingError):validate(value,jd=jd)


def test_service_never_persists_invalid_output_even_if_transport_validator_is_bypassed():
    req=request();repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    llm=MagicMock();bad=output();bad.requirements[0].label="Invented requirement";llm.generate_json.return_value=parsed(bad)
    with pytest.raises(HTTPException) as exc:JobFitService(repo,llm).analyze(req,"a"*43)
    assert exc.value.status_code==502;repo.complete.assert_not_called();repo.release.assert_called_once()


def test_exact_transferable_and_not_evidenced_matches_with_verified_metadata():
    value,warnings=validate()
    assert [r.status for r in value.requirements]==["matched","partial","not_evidenced"]
    assert value.requirements[0].evidence[0].section=="unclassified"
    assert not warnings


@pytest.mark.parametrize("change,code",[
    (lambda r:setattr(r,"jd_source_id","jd_999"),"unknown_job_source"),
    (lambda r:setattr(r,"jd_quote","Kubernetes is mandatory"),"job_quote_not_in_source"),
    (lambda r:setattr(r,"label","Kubernetes"),"requirement_label_not_in_quote"),
    (lambda r:setattr(r,"importance","preferred"),"job_importance_conflicts_with_source"),
    (lambda r:setattr(r,"evidence",[]),"positive_match_requires_cv_evidence"),
    (lambda r:setattr(r.evidence[0],"source_id","p99_fake"),"unknown_source_id"),
    (lambda r:setattr(r.evidence[0],"quote","Invented Python achievement"),"quote_not_in_cited_source"),
    (lambda r:setattr(r,"status","not_evidenced"),"absent_match_has_contradictory_evidence")])
def test_unsupported_claims_fail_closed(change,code):
    value=output();change(value.requirements[0])
    with pytest.raises(GroundingError) as exc:validate(value)
    assert exc.value.code==code


def test_duplicates_and_invalid_roadmap_reference_rejected():
    value=output();value.requirements.append(value.requirements[0].model_copy(deep=True))
    with pytest.raises(GroundingError,match="Source validation failed"):validate(value)
    value=output();value.improvements[0].requirement_index=15
    with pytest.raises(GroundingError) as exc:validate(value)
    assert exc.value.code=="unknown_recommendation_requirement"


def test_transferable_is_not_direct_and_missing_keyword_is_not_inability():
    value=output();value.requirements[1].status="matched"
    value,warnings=validate(value)
    assert value.requirements[1].status=="partial" and "direct_match_downgraded" in warnings
    value=output();value.requirements[0].status="not_evidenced";value.requirements[0].evidence=[]
    value,warnings=validate(value)
    assert value.requirements[0].status=="uncertain" and "present_keyword_requires_context" in warnings


def test_years_and_seniority_need_actual_evidence():
    value=output();value.requirements[0].label="5 years";value.requirements[0].category="experience"
    value.requirements[0].jd_quote="5 years of Python is required";jd=JD.replace(JD.splitlines()[0],value.requirements[0].jd_quote)
    value,warnings=validate(value,jd=jd)
    assert value.requirements[0].status=="uncertain" and "quantitative_requirement_unverified" in warnings
    value=output();value.requirements[0].category="seniority";value.requirements[0].label="Senior"
    value.requirements[0].jd_quote="Senior Python is required";jd=JD.replace(JD.splitlines()[0],value.requirements[0].jd_quote)
    assert validate(value,jd=jd)[0].requirements[0].status=="partial"


@pytest.mark.parametrize("years",["five years","fünf Jahren","5 years"])
def test_years_require_duration_evidence_not_just_an_unrelated_number(years):
    value=output();r=value.requirements[0];r.label="Python";r.jd_quote=f"Python with {years} experience is required"
    jd=JD.replace(JD.splitlines()[0],r.jd_quote)
    value,warnings=validate(value,jd=jd,cv=CV+" Built 5 projects.")
    assert value.requirements[0].status=="uncertain" and "experience_duration_unverified" in warnings


def test_heading_cannot_be_used_as_a_skill_requirement():
    value=output();r=value.requirements[0];r.label="skills";r.jd_quote="Required skills:"
    jd=JD.replace(JD.splitlines()[0],r.jd_quote)
    with pytest.raises(GroundingError) as exc:validate(value,jd=jd)
    assert exc.value.code=="job_heading_is_not_requirement"


def test_posting_without_assessable_criteria_returns_clear_input_error():
    req=request();repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    llm=MagicMock();llm.generate_json.return_value=parsed().model_copy(update={"requirements":[]})
    with pytest.raises(HTTPException) as exc:JobFitService(repo,llm).analyze(req,"a"*43)
    assert exc.value.status_code==422 and "No assessable" in exc.value.detail
    repo.complete.assert_not_called();repo.release.assert_called_once()


def test_incomplete_coverage_and_required_context_cannot_get_overall_score():
    value=output();value.requirements.pop();value.context_source_ids=["jd_003"]
    value,warnings=validate(value)
    assert not value.coverage_complete and "unassessed_explicit_job_clause" in warnings
    assert calculate_score(value.requirements,coverage_complete=value.coverage_complete).overall is None


def test_optional_rewrites_do_not_invent_metrics_or_skills():
    data=output().model_dump();data["rewrites"]=[dict(original="Developed automated tests",suggested="Developed 500 automated Python tests",rationale="Improve clarity",source_id="text_001")]
    value=ModelOutput.model_validate(data)
    assert not validate(value)[0].rewrites


def test_malformed_optional_rewrite_cannot_break_valid_matching():
    data=output().model_dump();data["rewrites"]=[{"original":"Developed automated tests","suggested":"Developed automated tests","rationale":"Retain wording"}]
    value=ModelOutput.model_validate(data)
    assert not value.rewrites and validate(value)[0].requirements[0].status=="matched"
    data["rewrites"][0]["source_id"]="fake_source"
    value,warnings=validate(ModelOutput.model_validate(data))
    assert not value.rewrites and "unsupported_rewrite_omitted" in warnings


def points(*values):return [SimpleNamespace(importance=k,status=s) for k,s in values]


def test_scoring_exact_default_weights_and_redistribution():
    score=calculate_score(points(("mandatory","matched"),("mandatory","partial"),("preferred","not_evidenced"),("alignment","matched")))
    assert score.overall==60
    assert [c.contribution for c in score.categories]==[45,0,15]
    score=calculate_score(points(("mandatory","matched"),("mandatory","partial"),("alignment","matched")))
    assert score.overall==80 and score.categories[0].effective_weight==80
    assert score.categories[1].score is None and score.categories[1].effective_weight==0


@pytest.mark.parametrize("options",[{"coverage_complete":False},{"layout_confidence":"low"}])
def test_weak_input_withholds_overall(options):
    assert calculate_score(points(*[("mandatory","matched")]*3),**options).overall is None


def test_uncertain_items_stay_in_denominator_and_score_is_not_probability():
    score=calculate_score(points(("mandatory","matched"),("mandatory","uncertain"),("mandatory","not_evidenced")))
    assert score.overall==33 and score.categories[0].count==3
    assert calculate_score(points(*[("mandatory","uncertain")]*3)).overall is None
    assert calculate_score(points(*[("preferred","matched")]*3)).overall is None
    assert calculate_score([]).overall is None
    assert "not hiring" in score.meaning and score.rubric_version=="job-fit-v1"


def test_service_single_extraction_cache_no_raw_persistence_and_diagnostics(monkeypatch):
    from job_fit import service as module
    original=module.extract_document;extract=MagicMock(side_effect=original);monkeypatch.setattr(module,"extract_document",extract)
    req=request();repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4());repo.complete.side_effect=lambda i,o,f,a:saved(req,analysis=a)
    llm=MagicMock()
    def generate(instructions,data,schema,**kwargs):
        value=output();value.requirements[1].status="matched"
        return kwargs["validator"](parsed(value) if schema is ParsedJob else classified(value))
    llm.generate_json.side_effect=generate
    result=JobFitService(repo,llm).analyze(req,"a"*43)
    assert result.analysis.score.overall==53
    assert "direct_match_downgraded" in result.analysis.warnings
    assert extract.call_count==1 and llm.generate_json.call_count==2
    assert "cv" not in llm.generate_json.call_args_list[0].args[1]
    assert "job_sources" not in llm.generate_json.call_args_list[1].args[1]
    assert llm.generate_json.call_args_list[0].kwargs["budget"] is llm.generate_json.call_args_list[1].kwargs["budget"]
    assert CV not in str(repo.claim.call_args) and JD not in str(repo.complete.call_args)
    assert "not your actual" in " ".join(result.limitations)
    repo.claim.return_value=(result,None)
    assert JobFitService(repo,llm).analyze(req,"a"*43)==result
    assert llm.generate_json.call_count==2


def test_service_releases_failed_operation_and_rejects_unreadable_posting():
    req=request();repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    llm=MagicMock();llm.generate_json.side_effect=HTTPException(504,"AI timeout")
    with pytest.raises(HTTPException):JobFitService(repo,llm).analyze(req,"a"*43)
    repo.release.assert_called_once();repo.complete.assert_not_called()
    req.job_description="x"*200;repo.claim.reset_mock()
    with pytest.raises(HTTPException) as exc:JobFitService(repo,llm).analyze(req,"a"*43)
    assert exc.value.status_code==422;repo.claim.assert_not_called()


def test_nvidia_repairs_grounding_once_and_does_not_log_source(caplog):
    from interviews.llm import NvidiaInterviewer
    from test_interviews import mock_client
    client=mock_client("")
    bad=output();bad.requirements[0].evidence[0].quote="Private hallucinated content"
    def response(v):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=v.model_dump_json()))])
    client.chat.completions.create.side_effect=[response(bad),response(output())]
    model=NvidiaInterviewer(lambda:client)
    result=model.generate_json("Compare",{},ModelOutput,validator=lambda v:validate(v)[0])
    assert result.requirements[0].status=="matched" and client.chat.completions.create.call_count==2
    assert "Private hallucinated content" not in caplog.text
    client.chat.completions.create.reset_mock(side_effect=True);client.chat.completions.create.return_value=response(bad)
    with pytest.raises(HTTPException) as exc:model.generate_json("Compare",{},ModelOutput,validator=lambda v:validate(v)[0])
    assert exc.value.status_code==502 and client.chat.completions.create.call_count==2


def test_two_stages_share_a_three_attempt_budget():
    from interviews.llm import NvidiaInterviewer,GenerationBudget
    from test_interviews import mock_client
    client=mock_client("")
    def response(text):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    client.chat.completions.create.side_effect=[response(parsed().model_dump_json()),response("{}"),response("{}")]
    llm=NvidiaInterviewer(lambda:client);budget=GenerationBudget()
    llm.generate_json("Parse posting",{},ParsedJob,budget=budget)
    with pytest.raises(HTTPException):llm.generate_json("Classify",{},ClassifiedMatches,budget=budget)
    assert client.chat.completions.create.call_count==3 and budget.remaining==0
    with pytest.raises(HTTPException):llm.generate_json("Do not call",{},ClassifiedMatches,budget=budget)
    assert client.chat.completions.create.call_count==3


def test_fixed_requirement_indices_must_cover_every_criterion_exactly_once():
    req=request();repo=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    llm=mock_llm()
    def generate(instructions,data,schema,**kwargs):
        if schema is ParsedJob:return kwargs["validator"](parsed())
        matches=classified();matches.matches[1].requirement_index=0
        return kwargs["validator"](matches)
    llm.generate_json.side_effect=generate
    with pytest.raises(HTTPException) as exc:JobFitService(repo,llm).analyze(req,"a"*43)
    assert exc.value.status_code==502;repo.complete.assert_not_called();repo.release.assert_called_once()


def test_api_auth_sanitized_validation_private_history_and_deletion():
    req=request();repo=MagicMock();service=MagicMock();service.analyze.return_value=saved(req)
    repo.history.return_value={"items":[],"next_cursor":None};repo.read.return_value=saved(req)
    app.dependency_overrides[get_service]=lambda:service;app.dependency_overrides[get_repository]=lambda:repo
    try:
        with TestClient(app) as client:
            headers={"Authorization":"Bearer "+"a"*43}
            assert client.post("/api/job-fit/analyze",json=req.model_dump(mode="json")).status_code==401
            response=client.post("/api/job-fit/analyze",json=req.model_dump(mode="json"),headers=headers)
            assert response.status_code==200 and response.headers["cache-control"]=="no-store"
            assert service.analyze.call_args.args[1]=="a"*43
            assert client.get("/api/job-fit/history",headers=headers).json()=={"items":[],"next_cursor":None}
            assert client.get(f"/api/job-fit/{req.operation_id}",headers=headers).status_code==200
            assert client.delete(f"/api/job-fit/{req.operation_id}",headers=headers).status_code==204
            repo.remove.assert_called_once_with(req.operation_id,"a"*43)
            invalid=client.post("/api/job-fit/analyze",json={"secret":"personal CV data"},headers=headers)
            assert invalid.status_code==422 and "personal CV data" not in invalid.text
            assert client.post("/api/job-fit/analyze",content="A"*4_300_001,headers={**headers,"content-type":"application/json"}).status_code==413
            assert client.get("/api/job-fit/history?limit=21",headers=headers).status_code==422
    finally:app.dependency_overrides.clear()


def test_complex_pdf_uses_shared_extractor_without_losing_columns():
    import base64
    from test_cv_documents import layout_pdf,column
    from cv.extraction import extract_document
    rows=[entry for row in zip(column(35,"Experience","Example Employer","C#/.NET"),column(330,"Projects","Example Project","Python")) for entry in row]
    doc=extract_document(request(pdf_base64=base64.b64encode(layout_pdf([rows])).decode()))
    assert any(b.section=="experience" and "Example Employer" in b.text and "Example Project" not in b.text for b in doc.blocks)
    assert any(b.section=="projects" and "Python" in b.text and "Example Employer" not in b.text for b in doc.blocks)
