"""Run both real service paths on the same synthetic sources; never call NVIDIA."""
import base64
from copy import deepcopy
from dataclasses import asdict
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from cv.document import normalize_text
from cv.extraction import extract_document
from cv.grounding import verify_source_quote,GroundingError
from cv.schemas import ReviewRequest,CvAnalysis
from cv.service import CvService
from job_fit.schemas import JobFitRequest,ParsedJob,ClassifiedMatches,Evidence
from job_fit.service import JobFitService
from test_cv_documents import layout_pdf,column
from test_job_fit import JD,parsed,classified


TEXT=("Professional Summary\nSoftware developer building reliable applications in Germany.\n\n"
    "Professional Experience\nExample Employer, 2021–2024\nBuilt C#/.NET and C++ applications in Ger-\nmany using Vision-\nLib.\n\n"
    "Technical Skills\nPython, Angular, HTML5, Git, SQL Server.\n\n"
    "Education\nBachelor of Software Engineering, Example University, 2020.\n\n"
    "Projects\nCreated a React dashboard with Unicode ‘quotes’ and readable error messages.\n\n"
    "Certifications\nExample Testing Certificate, 2023.\n\n"
    "Sprachen\nDeutsch und Englisch: technische Dokumentation und Zusammenarbeit.")


def source(case):
    if case=="text":return {"cv_text":TEXT}
    left=column(35,"Professional Experience","Example Employer","C#/.NET")
    right=column(330,"Projects","Example Project","Python")
    if case=="single":pages=[left]
    elif case=="two":pages=[[entry for row in zip(left,right) for entry in row]]
    elif case=="three":
        narrow=lambda x,h,c,t:[(x,y,v) for y,v in zip((100,120,140,160,180,200),(h,c,"2021 - 2024",t,"Documented work.","Tested software."))]
        columns=[narrow(35,"Experience","Example Employer","C#/.NET C++"),narrow(220,"Projects","Example Project","Python Angular"),narrow(420,"Training","Example Course","SQL Server")]
        pages=[[entry for row in zip(*columns) for entry in row]]
    elif case=="sidebar":pages=[column(35,"Technical Skills","Example Skills","Python")+column(260,"Experience","Example Employer","C#/.NET")]
    elif case=="table":pages=[[(35,95,"Professional Experience"),(45,128,"Example Employer"),(310,128,"2021 - 2024"),
        (45,148,"Python APIs"),(310,148,"SQL Server"),(45,168,"Tested applications"),(310,168,"C#/.NET")]]
    else:
        pages=[left+right,[(35,70,"Professional Summary"),(35,90,"Software development in Germany."),
            (35,140,"Ausbildung"),(35,160,"Bachelor of Software Engineering, 2020."),
            (35,210,"Zertifikate"),(35,230,"Example Testing Certificate, 2023."),
            (35,280,"Technische Kenntnisse"),(35,300,"C++, C#, .NET, React, Angular, Python, SQL Server."),
            (35,350,"Sprachen"),(35,370,"Deutsch und Englisch: technische Dokumentation."),
            (35,420,"Projekte"),(35,440,"Built applications in Ger-"),(35,455,"many using Vision-"),(35,470,"Lib with Unicode ‘quotes’.")]]
    return {"pdf_base64":base64.b64encode(layout_pdf(pages,image=case in ("two","multipage"),table=case=="table")).decode()}


def repository():
    repo=MagicMock();repo.claim.return_value=(None,uuid4());repo.complete.side_effect=lambda i,o,f,a:a
    return repo


@pytest.mark.parametrize("case",["text","single","two","three","sidebar","table","multipage"])
def test_both_services_receive_identical_source_facts_ids_and_normalization(case,monkeypatch):
    from cv import service as cv_module
    from job_fit import service as fit_module
    documents=[];payloads={}
    def extract(req):
        doc=extract_document(req);documents.append(doc);return doc
    monkeypatch.setattr(cv_module,"extract_document",extract);monkeypatch.setattr(fit_module,"extract_document",extract)
    cv_llm=MagicMock();fit_llm=MagicMock()
    def review(instructions,data,schema,**kwargs):
        payloads["cv"]=deepcopy(data["resume"]);block=data["resume"]["sources"][0]
        value=CvAnalysis(summary="Source-backed synthetic feedback.",strengths=[dict(title="Relevant technical skills",
            source_id=block["source_id"],evidence=block["text"][:100],recommendation="Clarify actual project responsibilities.")],
            weaknesses=[],missing_skills=[],unclear_descriptions=[],content_errors=[],rewrites=[],practice_plan=["Use only truthful details."])
        return kwargs["validator"](value)
    def compare(instructions,data,schema,**kwargs):
        if schema is ParsedJob:return kwargs["validator"](parsed())
        assert schema is ClassifiedMatches;payloads["job_fit"]=deepcopy(data["cv"]);value=classified()
        for term,match in zip(("Python","PostgreSQL","Docker"),value.matches):
            block=next((b for b in data["cv"]["sources"] if term in b["text"]),None)
            match.status="matched" if block else "not_evidenced"
            match.evidence=[Evidence(source_id=block["source_id"],quote=term)] if block else []
        return kwargs["validator"](value)
    cv_llm.generate_json.side_effect=review;fit_llm.generate_json.side_effect=compare
    data=source(case)
    cv_result=CvService(repository(),cv_llm).review(ReviewRequest(operation_id=uuid4(),job_role="Developer",**data),"a"*43)
    fit_result=JobFitService(repository(),fit_llm).analyze(JobFitRequest(operation_id=uuid4(),job_role="Developer",job_description=JD,**data),"a"*43)
    assert len(documents)==2  # one extraction per feature, never per model stage
    assert asdict(documents[0])==asdict(documents[1])
    assert payloads["cv"]==payloads["job_fit"]
    assert "Example Employer" in documents[0].text and "2021" in documents[0].text
    for finding in cv_result.strengths:
        for doc in documents:verify_source_quote(doc,finding.source_id,finding.evidence)
    for item in fit_result.requirements:
        for quote in item.evidence:
            for doc in documents:verify_source_quote(doc,quote.source_id,quote.quote)
    if case in ("text","multipage"):
        for fact in ("Bachelor of Software Engineering","2020","Example Testing Certificate","2023","Germany","VisionLib","Angular","C#","C++",".NET"):
            assert fact in documents[0].text
        assert {"education","certifications","summary","experience","projects"}<=set(payloads["cv"]["sections"])
        assert normalize_text("Unicode ‘quotes’") in documents[0].text
    # Neither feature can verify a synthetic invention or another source's quote.
    for doc in documents:
        with pytest.raises(GroundingError):verify_source_quote(doc,"invented_source","Fabricated qualification")
        with pytest.raises(GroundingError):verify_source_quote(doc,doc.blocks[0].source_id,"Fabricated qualification")


def test_real_reference_pdf_processing_parity_without_external_calls():
    """Opt-in private local extraction benchmark; no committed paths or contents."""
    import os
    from pathlib import Path
    path=os.getenv("PRIVATE_RESUME_PDF")
    if not path:pytest.skip("Optional private PDF extraction requires PRIVATE_RESUME_PDF; never used in CI")
    data={"pdf_base64":base64.b64encode(Path(path).read_bytes()).decode()}
    cv=extract_document(ReviewRequest(operation_id=uuid4(),job_role="Developer",**data))
    fit=extract_document(JobFitRequest(operation_id=uuid4(),job_role="Developer",job_description=JD,**data))
    if asdict(cv)!=asdict(fit) or not cv.blocks or len(cv.text)<100:
        pytest.fail("Private PDF extraction parity failed; source contents withheld")
    for block in cv.blocks:verify_source_quote(fit,block.source_id,block.text[:150])
