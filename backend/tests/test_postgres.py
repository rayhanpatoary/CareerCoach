"""Real PostgreSQL integration tests. Only a disposable local *_test DB is allowed."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from interviews.database import build_engine, database_url
from interviews.repository import PostgresRepository, now
from interviews.schemas import AnswerRequest, Configuration, OperationRequest, StartRequest
from interviews.service import InterviewService
from interviews.tables import Answer, Feedback, Interview, Operation, Question
from test_interviews import evaluation


@pytest.fixture(scope="module")
def engine():
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set TEST_DATABASE_URL to a disposable local PostgreSQL *_test database; CI supplies one")
    url = database_url(raw)
    if url.host not in ("localhost", "127.0.0.1", "postgres") or not (url.database or "").endswith("_test"):
        pytest.fail("Refusing integration tests against a non-local or non-*_test database")
    engine = build_engine(raw)
    original = os.environ.get("DIRECT_DATABASE_URL")
    os.environ["DIRECT_DATABASE_URL"] = raw
    try:
        # Fresh disposable test database only; no access to hosted environments.
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        if original is None: os.environ.pop("DIRECT_DATABASE_URL", None)
        else: os.environ["DIRECT_DATABASE_URL"] = original


@pytest.fixture
def repository(engine):
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE career_coach.interviews, career_coach.rate_buckets CASCADE"))
    return PostgresRepository(engine)


def begin(repository):
    owner, operation_id = "a"*43, uuid4()
    config = Configuration(job_role="Python Developer", question_count=3)
    before, fence = repository.claim(operation_id, owner, operation_id, "start", config.model_dump(), config)
    state = repository.complete(operation_id, owner, operation_id, fence, "start", config.model_dump(), "Explain how Python lists differ from tuples?", None)
    return owner, state


def test_complete_interview_context_and_cached_evaluation(repository):
    llm = MagicMock()
    llm.question.side_effect = lambda config, turns: f"Question {len(turns)+1}: How would you apply a tuple in a practical example?"
    llm.evaluate.side_effect = lambda config, turns: evaluation([type("T", (), {"id":turn["id"]})() for turn in turns])
    service = InterviewService(repository, llm)
    owner = "b"*43
    request = StartRequest(job_role="Python Developer", question_count=3, persistent=True, operation_id=uuid4())
    state = service.start(request, owner)
    assert len(state.turns) == 1
    assert service.start(request, owner).id == state.id
    assert llm.question.call_count == 1
    for index in range(3):
        answer = AnswerRequest(operation_id=uuid4(), question_id=state.turns[-1].id, answer=f"Lists are mutable. Practical example {index}.")
        state = service.answer(state.id, answer, owner)
        assert state.answered_count == index+1
        assert service.answer(state.id, answer, owner).answered_count == index+1
    assert state.status == "completed" and llm.question.call_count == 3
    assert "Practical example 1" in llm.question.call_args.args[1][-1]["answer"]
    finish = OperationRequest(operation_id=uuid4())
    state = service.finish(state.id, finish, owner)
    assert state.status == "finished" and not state.feedback.partial
    assert state.feedback.overall_score == 66
    assert service.finish(state.id, finish, owner).feedback == state.feedback
    assert service.finish(state.id, OperationRequest(operation_id=uuid4()), owner).feedback == state.feedback
    assert repository.read(state.id, owner).feedback == state.feedback
    llm.evaluate.assert_called_once()
    with pytest.raises(HTTPException) as exc:
        service.answer(state.id, AnswerRequest(operation_id=uuid4(), question_id=state.turns[-1].id, answer="Too late"), owner)
    assert exc.value.status_code == 409


def test_ownership_expiry_and_cascade_deletion(repository, engine):
    owner, state = begin(repository)
    with pytest.raises(HTTPException) as exc: repository.read(state.id, "x"*43)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException): repository.remove(state.id, "x"*43)
    repository.remove(state.id, owner)
    with Session(engine) as db:
        assert db.scalar(select(Question).where(Question.interview_id == state.id)) is None
        assert db.scalar(select(Operation).where(Operation.interview_id == state.id)) is None
    owner, state = begin(repository)
    with engine.begin() as connection:
        connection.execute(update(Interview).where(Interview.id == state.id).values(expires_at=now()-timedelta(seconds=1)))
    with pytest.raises(HTTPException): repository.read(state.id, owner)
    repository.cleanup()
    with Session(engine) as db: assert db.get(Interview, state.id) is None


def test_concurrent_claims_and_stale_worker_fencing(repository, engine):
    owner, state = begin(repository)
    operation_id = uuid4(); payload = {"question_id":str(state.turns[-1].id), "answer":"A tuple stores fixed coordinates."}
    def claim():
        try: return repository.claim(state.id, owner, operation_id, "answer", payload)
        except HTTPException as error: return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(result == 409 for result in results) == 1
    old_fence = next(result[1] for result in results if isinstance(result, tuple))
    with engine.begin() as connection:
        connection.execute(update(Interview).where(Interview.id == state.id).values(lease_until=now()-timedelta(seconds=1)))
    _, new_fence = repository.claim(state.id, owner, operation_id, "answer", payload)
    with pytest.raises(HTTPException): repository.complete(state.id, owner, operation_id, old_fence, "answer", payload, "Should not persist?", None)
    result = repository.complete(state.id, owner, operation_id, new_fence, "answer", payload, "When could a tuple contain a mutable value?", None)
    assert result.answered_count == 1 and len(result.turns) == 2
    with Session(engine) as db:
        assert len(db.scalars(select(Answer)).all()) == 1
        assert len(db.scalars(select(Question)).all()) == 2


def test_payload_reuse_rejected_and_failed_answer_retryable(repository):
    owner, state = begin(repository)
    operation_id = uuid4(); payload = {"question_id":str(state.turns[-1].id), "answer":"An example"}
    _, fence = repository.claim(state.id, owner, operation_id, "answer", payload)
    repository.release(state.id, operation_id, fence)
    assert repository.read(state.id, owner).answered_count == 0
    with pytest.raises(HTTPException): repository.claim(state.id, owner, operation_id, "answer", {**payload, "answer":"Different payload"})
    _, fence = repository.claim(state.id, owner, operation_id, "answer", payload)
    result = repository.complete(state.id, owner, operation_id, fence, "answer", payload, "What is tuple hashability?", None)
    assert result.answered_count == 1
    with pytest.raises(HTTPException): repository.claim(state.id, owner, uuid4(), "answer", payload)


def test_early_finish_only_reviews_submitted_answers(repository):
    owner, state = begin(repository); llm = MagicMock()
    llm.question.return_value = "When are tuple values suitable dictionary keys?"
    service = InterviewService(repository, llm)
    state = service.answer(state.id, AnswerRequest(operation_id=uuid4(), question_id=state.turns[-1].id, answer="Lists are mutable."), owner)
    llm.evaluate.return_value = evaluation([state.turns[0]])
    state = service.finish(state.id, OperationRequest(operation_id=uuid4()), owner)
    assert state.feedback.partial and state.feedback.answered_count == 1
    assert len(llm.evaluate.call_args.args[1]) == 1


def test_start_rate_limit_is_durable(repository):
    for _ in range(10): begin(repository)
    with pytest.raises(HTTPException) as exc: begin(repository)
    assert exc.value.status_code == 429


def test_finish_claims_serialize_and_old_worker_cannot_commit(repository, engine):
    owner, state = begin(repository)
    old_id, new_id = uuid4(), uuid4()
    _, old_fence = repository.claim(state.id, owner, old_id, "finish", {})
    with pytest.raises(HTTPException) as exc:
        repository.claim(state.id, owner, new_id, "finish", {})
    assert exc.value.status_code == 409
    with engine.begin() as connection:
        connection.execute(update(Interview).where(Interview.id == state.id).values(lease_until=now()-timedelta(seconds=1)))
    _, new_fence = repository.claim(state.id, owner, new_id, "finish", {})
    with pytest.raises(HTTPException):
        repository.complete(state.id, owner, old_id, old_fence, "finish", {}, None, {})
    repository.release(state.id, new_id, new_fence)
    # Finish the recovered empty interview through the service, without AI calls.
    llm = MagicMock()
    result = InterviewService(repository, llm).finish(state.id, OperationRequest(operation_id=new_id), owner)
    assert result.feedback.overall_score is None
    llm.evaluate.assert_not_called()
    with Session(engine) as db: assert len(db.scalars(select(Feedback)).all()) == 1


def test_private_schema_has_no_public_privileges(engine):
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT nspacl::text FROM pg_namespace WHERE nspname='career_coach'"))
        acl = rows.scalar()
        # PUBLIC entries have an empty grantee before '='.
        assert '"=U/' not in (acl or '') and '{=U/' not in (acl or '')
        assert connection.execute(text("SELECT count(*) FROM career_coach.interviews")).scalar() >= 0
