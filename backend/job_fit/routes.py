from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from interviews.database import get_engine
from interviews.llm import NvidiaInterviewer,inline_schema
from interviews.routes import owner_credential
from cv.schemas import MAX_BODY_BYTES
from .schemas import JobFitRequest,JobFitReview,JobFitHistory
from .repository import JobFitRepository
from .service import JobFitService

router=APIRouter(prefix="/api/job-fit",tags=["Job-fit analysis"])


def get_repository():return JobFitRepository(get_engine())


def get_service(repository=Depends(get_repository)):
    from main import get_client
    return JobFitService(repository,NvidiaInterviewer(get_client))


async def parse_request(request:Request):
    if request.headers.get("content-type","").split(";")[0]!="application/json":
        raise HTTPException(415,"Send your CV and job description as JSON through the job-fit workspace.")
    chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>MAX_BODY_BYTES:raise HTTPException(413,"Choose a PDF no larger than 3 MiB.")
        chunks.append(chunk)
    try:return JobFitRequest.model_validate_json(b"".join(chunks))
    except ValidationError:
        raise HTTPException(422,"Provide a job title (2–100 characters), full job description (100–8,000 characters), optional company (up to 100), and exactly one PDF or CV text (100–30,000 characters). Use a valid request ID.") from None


@router.post("/analyze",response_model=JobFitReview,openapi_extra={"requestBody":{"required":True,
    "content":{"application/json":{"schema":inline_schema(JobFitRequest)}}}})
async def analyze(request=Depends(parse_request),owner=Depends(owner_credential),service=Depends(get_service)):
    return await run_in_threadpool(service.analyze,request,owner)


@router.get("/history",response_model=JobFitHistory)
def history(limit:int=Query(default=10,ge=1,le=20),cursor:UUID|None=None,owner=Depends(owner_credential),repository=Depends(get_repository)):
    return repository.history(owner,limit,cursor)


@router.get("/{analysis_id}",response_model=JobFitReview)
def read(analysis_id:UUID,owner=Depends(owner_credential),repository=Depends(get_repository)):
    return repository.read(analysis_id,owner)


@router.delete("/{analysis_id}",status_code=204)
def remove(analysis_id:UUID,owner=Depends(owner_credential),repository=Depends(get_repository)):
    repository.remove(analysis_id,owner)
