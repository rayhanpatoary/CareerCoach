"""Uses the existing guarded local-only database fixture; never hosted Supabase."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text,update

from test_postgres import engine
from test_cv import analysis
from cv.repository import CvRepository
from cv.tables import CvReview
from interviews.repository import now


@pytest.fixture
def repository(engine):
    with engine.begin() as db:db.execute(text("TRUNCATE career_coach.cv_reviews, career_coach.rate_buckets"))
    return CvRepository(engine)


def claim(repo,id,owner="a"*43,hash="hash"):
    return repo.claim(id,owner,hash,"Python Developer","text",200,None)


def test_concurrent_claim_idempotency_and_private_history(repository):
    id=uuid4()
    def attempt():
        try:return claim(repository,id)[1]
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    assert results.count(409)==1
    fence=next(v for v in results if v!=409)
    repository.complete(id,"a"*43,fence,analysis())
    assert claim(repository,id)[1] is None
    assert len(repository.history("a"*43).items)==1
    assert not repository.history("b"*43).items
    for action in [lambda:repository.read(id,"b"*43),lambda:repository.remove(id,"b"*43)]:
        with pytest.raises(HTTPException) as exc:action()
        assert exc.value.status_code==404
    with pytest.raises(HTTPException) as exc:claim(repository,id,hash="changed")
    assert exc.value.status_code==409


def test_deletion_expiry_and_stale_fence(repository,engine):
    id=uuid4();_,fence=claim(repository,id)
    repository.remove(id,"a"*43)
    with pytest.raises(HTTPException):repository.complete(id,"a"*43,fence,analysis())
    repository.release(id,"a"*43,fence)
    assert not repository.history("a"*43).items
    id=uuid4();claim(repository,id)
    with engine.begin() as db:db.execute(update(CvReview).where(CvReview.id==id).values(expires_at=now()-timedelta(seconds=1)))
    assert not repository.history("a"*43).items
    repository.cleanup()
    with pytest.raises(HTTPException):repository.read(id,"a"*43)


def test_grounded_pdf_review_persistence_retry_and_deletion(repository):
    from unittest.mock import MagicMock
    from cv.service import CvService
    from cv.grounding import GroundedAnalysis
    from test_cv import pdf_request
    from test_cv_documents import layout_pdf,column
    req=pdf_request(layout_pdf([column(35,"Experience","Example Employer","Python")]))
    llm=MagicMock()
    def generate(instructions,payload,schema,**kwargs):
        a=analysis().model_dump()
        a["strengths"][0].update(title="Relevant professional experience",source_id=payload["resume"]["sources"][0]["source_id"],evidence="Built reliable Python applications.")
        return kwargs["validator"](GroundedAnalysis.model_validate(a))
    llm.generate_json.side_effect=generate
    service=CvService(repository,llm);owner="c"*43
    state=service.review(req,owner)
    assert state.analysis.strengths[0].source_page==1
    assert repository.read(state.id,owner).analysis.extraction.source_block_count>=1
    assert service.review(req,owner).id==state.id and llm.generate_json.call_count==1
    with pytest.raises(HTTPException) as exc:repository.read(state.id,"d"*43)
    assert exc.value.status_code==404
    repository.remove(state.id,owner)
    with pytest.raises(HTTPException):repository.read(state.id,owner)
