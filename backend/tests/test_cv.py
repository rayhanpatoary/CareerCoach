import base64
import io
import subprocess
from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from cv.extraction import extract
from cv.routes import get_repository, get_service
from cv.schemas import CvAnalysis, Review, ReviewRequest, MAX_PDF_BYTES
from cv.service import CvService
from interviews.repository import now
from main import app

CV = "Python developer building reliable APIs with FastAPI and PostgreSQL. Developed automated tests and documented deployment procedures. Collaborated with designers to improve customer workflows."


def test_shared_schema_preserves_fields_named_title():
    from interviews.llm import inline_schema
    schema=inline_schema(CvAnalysis)
    finding=schema["properties"]["strengths"]["items"]
    assert finding["properties"]["title"]["type"]=="string"
    assert "title" in finding["required"]
    assert "$defs" not in schema


def test_cv_transport_repairs_once_within_existing_attempt_budget(caplog):
    from types import SimpleNamespace
    from interviews.llm import NvidiaInterviewer
    from test_interviews import mock_client
    client=mock_client("")
    def response(value):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])
    client.chat.completions.create.side_effect=[response('{"private-field":"private-source-text"}'),response(analysis().model_dump_json())]
    result=NvidiaInterviewer(lambda:client).generate_json("Review this CV",{"cv_text":CV},CvAnalysis)
    assert result==analysis() and client.chat.completions.create.call_count==2
    assert "private-source-text" not in caplog.text and "private-field" not in caplog.text
    client.chat.completions.create.reset_mock(side_effect=True)
    client.chat.completions.create.return_value=response("{}")
    with pytest.raises(HTTPException):NvidiaInterviewer(lambda:client).generate_json("Review",{},CvAnalysis)
    assert client.chat.completions.create.call_count==2


def analysis():
    return CvAnalysis(summary="Your backend experience is clearly described. Add evidence of impact where available.",
        strengths=[dict(title="Relevant technical skills",source_id="text_001",evidence="reliable APIs with FastAPI and PostgreSQL",recommendation="Describe one API project in more detail.")],
        weaknesses=[],missing_skills=[],unclear_descriptions=[],content_errors=[],rewrites=[],
        practice_plan=["Describe one project outcome using only verified facts."])


def request(**kwargs):
    return ReviewRequest(operation_id=uuid4(),job_role="Python Developer",**(kwargs or {"cv_text":CV}))


def saved(request, status="finished"):
    return Review(id=request.operation_id,job_role=request.job_role,source="text",status=status,
        character_count=len(CV),page_count=None,created_at=now(),expires_at=now()+timedelta(days=7),
        analysis=analysis() if status=="finished" else None)


def pdf(text=CV, pages=1, encrypted=False):
    writer=PdfWriter()
    font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),NameObject("/Subtype"):NameObject("/Type1"),NameObject("/BaseFont"):NameObject("/Helvetica")})
    for _ in range(pages):
        page=writer.add_blank_page(width=600,height=800)
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")]=writer._add_object(stream)
    if encrypted:writer.encrypt("secret")
    out=io.BytesIO();writer.write(out);return out.getvalue()


def pdf_request(data):return request(pdf_base64=base64.b64encode(data).decode())


def test_pdf_and_pasted_extraction():
    assert extract(request())==(CV,"text",None)
    text,source,pages=extract(pdf_request(pdf()))
    assert CV in text and source=="pdf" and pages==1


@pytest.mark.parametrize("data,fragment",[(b"not a PDF","complete PDF"),(b"%PDF-1.7 broken %%EOF","malformed"),(pdf(encrypted=True),"Password"),(pdf(text=""),"100"),(pdf(pages=11),"1–10")])
def test_pdf_rejections(data,fragment):
    with pytest.raises(HTTPException) as exc:extract(pdf_request(data))
    assert exc.value.status_code==422 and fragment in exc.value.detail


def test_pdf_size_and_extraction_timeout(monkeypatch):
    encoded=base64.b64encode(b"x"*(MAX_PDF_BYTES+1)).decode()
    with pytest.raises(ValidationError):request(pdf_base64=encoded)
    # Defense in depth after the request schema's encoded-size check.
    oversized=ReviewRequest.model_construct(operation_id=uuid4(),job_role="Developer",pdf_base64=encoded)
    with pytest.raises(HTTPException) as exc:extract(oversized)
    assert exc.value.status_code==413
    monkeypatch.setattr(subprocess,"run",MagicMock(side_effect=subprocess.TimeoutExpired("pdf",8)))
    with pytest.raises(HTTPException) as exc:extract(pdf_request(pdf()))
    assert "too long" in exc.value.detail


def test_invalid_input_contract():
    with pytest.raises(ValidationError):request(cv_text=CV,pdf_base64="AAAA")
    with pytest.raises(ValidationError):request(cv_text="too short")
    with pytest.raises(HTTPException):extract(request(pdf_base64="!!!!"))
    with pytest.raises(HTTPException):extract(request(cv_text="1"*200))


def test_pdf_worker_concurrency_is_bounded(monkeypatch):
    from cv import extraction
    slots=MagicMock();slots.acquire.return_value=False
    monkeypatch.setattr(extraction,"_PDF_SLOTS",slots)
    worker=MagicMock();monkeypatch.setattr(subprocess,"run",worker)
    with pytest.raises(HTTPException) as exc:extract(pdf_request(pdf()))
    assert exc.value.status_code==503 and exc.value.headers["Retry-After"]=="3"
    worker.assert_not_called();slots.release.assert_not_called()


def test_analysis_calls_existing_llm_and_cached_retries():
    req=request();repo=MagicMock();llm=MagicMock();fence=uuid4()
    repo.claim.return_value=(saved(req,"processing"),fence);repo.complete.return_value=saved(req)
    llm.generate_json.return_value=analysis()
    service=CvService(repo,llm);assert service.review(req,"a"*43).analysis
    assert llm.generate_json.call_args.args[1]["resume"]["sources"][0]["text"]==CV
    assert repo.complete.call_args.args[2]==fence
    repo.claim.return_value=(saved(req),None)
    assert service.review(req,"a"*43).id==req.operation_id
    assert llm.generate_json.call_count==1
    assert CV not in str(repo.claim.call_args)


def test_hallucinated_evidence_or_provider_failure_never_saved():
    req=request();repo=MagicMock();llm=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    invalid=analysis();invalid.strengths[0].evidence="An entirely invented achievement"
    llm.generate_json.return_value=invalid
    with pytest.raises(HTTPException) as exc:CvService(repo,llm).review(req,"a"*43)
    assert exc.value.status_code==502;repo.complete.assert_not_called();repo.release.assert_called_once()
    repo.release.reset_mock();llm.generate_json.side_effect=HTTPException(503,"NVIDIA temporarily unavailable")
    with pytest.raises(HTTPException):CvService(repo,llm).review(req,"a"*43)
    repo.release.assert_called_once();repo.complete.assert_not_called()


def test_rewrites_cannot_add_achievement_metrics():
    req=request();repo=MagicMock();llm=MagicMock();repo.claim.return_value=(saved(req,"processing"),uuid4())
    output=analysis()
    from cv.schemas import Rewrite
    output.rewrites=[Rewrite(original="Developed automated tests",suggested="Developed 500 automated tests",rationale="More specific",source_id="text_001")]
    llm.generate_json.return_value=output
    CvService(repo,llm).review(req,"a"*43)
    committed=repo.complete.call_args.args[3]
    assert not committed.rewrites
    assert "unsupported_rewrite_omitted" in committed.extraction.warnings


def test_api_contract_auth_privacy_and_history():
    req=request();repo=MagicMock();service=MagicMock();service.review.return_value=saved(req)
    repo.read.return_value=saved(req);repo.history.return_value={"items":[],"next_cursor":None}
    app.dependency_overrides[get_repository]=lambda:repo
    app.dependency_overrides[get_service]=lambda:service
    try:
        with TestClient(app) as client:
            path="/api/cv/reviews";headers={"Authorization":"Bearer "+"a"*43}
            assert client.post(path,json=req.model_dump(mode="json")).status_code==401
            response=client.post(path,headers=headers,json=req.model_dump(mode="json"))
            assert response.status_code==200 and response.headers["cache-control"]=="no-store"
            assert response.json()["analysis"]["strengths"]
            response=client.post(path,headers=headers,json={"cv_text":"SECRET personal data"})
            assert response.status_code==422 and "SECRET" not in response.text
            assert client.post(path,headers=headers,content=b"x"*4_300_001).status_code==415
            assert client.post(path,headers={**headers,"Content-Type":"application/json"},content=b"x"*4_300_001).status_code==413
            assert client.get(path,headers=headers).json()=={"items":[],"next_cursor":None}
            assert client.get(f"{path}/{req.operation_id}",headers=headers).status_code==200
            assert client.delete(f"{path}/{req.operation_id}",headers=headers).status_code==204
            repo.remove.assert_called_once_with(req.operation_id,"a"*43)
    finally:app.dependency_overrides.clear()
