import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from .database import get_engine
from .llm import NvidiaInterviewer
from .repository import PostgresRepository
from .schemas import AnswerRequest, Evaluation, InterviewState, OperationRequest
from .service import InterviewService

router = APIRouter(prefix="/api/interview", tags=["interviews"])


def owner_credential(authorization: str = Header(default="")):
    if not re.fullmatch(r"Bearer [A-Za-z0-9_-]{43,128}", authorization):
        raise HTTPException(401, "A valid anonymous session credential is required.")
    return authorization[7:]


def get_repository():
    return PostgresRepository(get_engine())


def get_service(repository=Depends(get_repository)):
    # Import lazily to retain the existing NVIDIA client configuration and test hook.
    from main import get_client
    return InterviewService(repository, NvidiaInterviewer(get_client))


@router.get("/{interview_id}", response_model=InterviewState)
def read_interview(interview_id: UUID, response: Response, owner=Depends(owner_credential), repository=Depends(get_repository)):
    response.headers["Cache-Control"] = "no-store"
    return repository.read(interview_id, owner)


@router.post("/{interview_id}/answer", response_model=InterviewState)
def answer_interview(interview_id: UUID, request: AnswerRequest,
                     owner=Depends(owner_credential), service=Depends(get_service)):
    return service.answer(interview_id, request, owner)


@router.post("/{interview_id}/finish", response_model=InterviewState)
def finish_interview(interview_id: UUID, request: OperationRequest,
                     owner=Depends(owner_credential), service=Depends(get_service)):
    return service.finish(interview_id, request, owner)


@router.get("/{interview_id}/feedback", response_model=Evaluation)
def read_feedback(interview_id: UUID, owner=Depends(owner_credential), repository=Depends(get_repository)):
    state = repository.read(interview_id, owner)
    if state.feedback is None:
        raise HTTPException(409, "Feedback is not ready. Finish the interview first.")
    return state.feedback


@router.delete("/{interview_id}", status_code=204)
def delete_interview(interview_id: UUID, owner=Depends(owner_credential), repository=Depends(get_repository)):
    repository.remove(interview_id, owner)
