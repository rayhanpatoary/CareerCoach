from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from interviews.database import get_engine
from interviews.llm import NvidiaInterviewer, inline_schema
from interviews.routes import owner_credential
from .repository import CvRepository
from .schemas import MAX_BODY_BYTES, Review, ReviewHistory, ReviewRequest
from .service import CvService

router = APIRouter(prefix="/api/cv/reviews",tags=["CV reviews"])


def get_repository():
    return CvRepository(get_engine())


def get_service(repository=Depends(get_repository)):
    from main import get_client
    return CvService(repository,NvidiaInterviewer(get_client))


async def parse_review(request:Request):
    if request.headers.get("content-type","").split(";")[0] != "application/json":
        raise HTTPException(415,"Send a PDF upload or pasted CV text as JSON through the CV workspace.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise HTTPException(413,"The upload is too large. Choose a PDF no larger than 3 MiB.")
        chunks.append(chunk)
    try:
        return ReviewRequest.model_validate_json(b"".join(chunks))
    except ValidationError:
        # FastAPI's default validation response would echo sensitive CV input.
        raise HTTPException(422,"Enter a role (2–100 characters), a CV (100–30,000 text characters or PDF up to 3 MiB), and an optional job description (up to 8,000 characters). Use one CV source and a valid request ID.") from None


@router.post("",response_model=Review,openapi_extra={"requestBody":{"required":True,
    "content":{"application/json":{"schema":inline_schema(ReviewRequest)}}}})
async def create_review(request=Depends(parse_review),owner=Depends(owner_credential),service=Depends(get_service)):
    # Synchronous extraction/SDK/database work must not block FastAPI's event loop.
    return await run_in_threadpool(service.review,request,owner)


@router.get("",response_model=ReviewHistory)
def review_history(limit:int=Query(default=10,ge=1,le=20),cursor:UUID|None=None,
                   owner=Depends(owner_credential),repository=Depends(get_repository)):
    return repository.history(owner,limit,cursor)


@router.get("/{review_id}",response_model=Review)
def read_review(review_id:UUID,owner=Depends(owner_credential),repository=Depends(get_repository)):
    return repository.read(review_id,owner)


@router.delete("/{review_id}",status_code=204)
def delete_review(review_id:UUID,owner=Depends(owner_credential),repository=Depends(get_repository)):
    repository.remove(review_id,owner)
