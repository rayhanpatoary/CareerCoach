"""All mutations serialize on the owning interview; no locks across LLM calls."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .schemas import Configuration, InterviewState, Turn
from .tables import Answer, Feedback, Interview, Operation, Question, RateBucket


def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(question: str):
    return digest(re.sub(r"[^\w]+", "", question.casefold()))


def payload_hash(kind: str, payload: dict):
    return digest(kind + json.dumps(payload, sort_keys=True, separators=(",", ":")))


class InterviewRepository(Protocol):
    def read(self, interview_id: UUID, owner: str) -> InterviewState: ...
    def claim(self, interview_id: UUID, owner: str, operation_id: UUID,
              kind: str, payload: dict, configuration: Configuration | None = None): ...
    def complete(self, interview_id: UUID, owner: str, operation_id: UUID, fence: UUID,
                 kind: str, payload: dict, question: str | None, feedback: dict | None) -> InterviewState: ...
    def release(self, interview_id: UUID, operation_id: UUID, fence: UUID): ...
    def remove(self, interview_id: UUID, owner: str): ...


class PostgresRepository:
    def __init__(self, engine):
        self.engine = engine

    def _authorized(self, db, interview_id, owner, lock=False):
        query = select(Interview).where(Interview.id == interview_id,
                                        Interview.owner_hash == digest(owner), Interview.expires_at > now())
        row = db.scalar(query.with_for_update() if lock else query)
        if not row:
            raise HTTPException(404, "Interview not found or expired.")
        return row

    def _state(self, db, row):
        turns = []
        for question, answer in db.execute(select(Question, Answer).outerjoin(
                Answer, Answer.question_id == Question.id).where(
                Question.interview_id == row.id).order_by(Question.position)):
            turns.append(Turn(id=question.id, position=question.position, question=question.text,
                              answer=answer.text if answer else None, asked_at=question.asked_at,
                              answered_at=answer.answered_at if answer else None))
        feedback = db.get(Feedback, row.id)
        current = next((turn.question for turn in turns if turn.answer is None), None)
        return InterviewState(**row.configuration, id=row.id, status=row.status,
                              question=current, turns=turns, answered_count=sum(t.answer is not None for t in turns),
                              started_at=row.started_at, completed_at=row.completed_at,
                              expires_at=row.expires_at, feedback=feedback.content if feedback else None,
                              busy=bool(row.active_operation and row.lease_until and row.lease_until > now()))

    def _rate(self, db, key, limit):
        window = now().replace(minute=0, second=0, microsecond=0)
        statement = insert(RateBucket).values(key=key, window_start=window, count=1)
        count = db.scalar(statement.on_conflict_do_update(
            index_elements=[RateBucket.key, RateBucket.window_start],
            set_={"count": RateBucket.count + 1}).returning(RateBucket.count))
        if count > limit:
            raise HTTPException(429, "Interview request limit reached. Please try again later.",
                                headers={"Retry-After": "3600"})

    def read(self, interview_id, owner):
        with Session(self.engine) as db, db.begin():
            # Lock also makes transcript/status a consistent multi-query snapshot.
            return self._state(db, self._authorized(db, interview_id, owner, lock=True))

    def reserve_legacy_request(self):
        with Session(self.engine) as db, db.begin():
            self._rate(db, "legacy:global", 100)
            self._rate(db, "ai:global", 1500)

    def claim(self, interview_id, owner, operation_id, kind, payload, configuration=None):
        with Session(self.engine) as db, db.begin():
            if kind == "start":
                inserted = db.scalar(insert(Interview).values(
                    id=interview_id, owner_hash=digest(owner), configuration=configuration.model_dump(),
                    status="generating_question", started_at=now(), expires_at=now() + timedelta(days=7)
                ).on_conflict_do_nothing(index_elements=[Interview.id]).returning(Interview.id))
                if inserted:
                    self._rate(db, "starts:global", 200)
                    self._rate(db, "starts:" + digest(owner), 10)
            row = self._authorized(db, interview_id, owner, lock=True)
            state = self._state(db, row)
            operation = db.get(Operation, (interview_id, operation_id))
            expected_hash = payload_hash(kind, payload)
            if operation and (operation.request_hash != expected_hash or operation.kind != kind):
                raise HTTPException(409, "This operation ID was already used for a different request.")
            if operation and operation.status == "done":
                return state, None
            if row.active_operation and row.lease_until > now():
                raise HTTPException(409, "A request is still processing. Wait, then retry the same action.",
                                    headers={"Retry-After": "3"})
            if row.active_operation and row.active_operation != operation_id:
                # Its lease expired. Fence out the crashed worker and allow an
                # explicit new action even if the original browser tab was lost.
                abandoned = db.get(Operation, (interview_id, row.active_operation))
                if abandoned:
                    abandoned.status = "failed"
                row.active_operation = row.lease_until = row.fence = None
                row.status = "completed" if state.answered_count >= state.question_count else "in_progress"
                state = state.model_copy(update={"status": row.status, "busy": False})
            if kind == "answer":
                if state.status in ("completed", "evaluating", "finished") or not state.turns:
                    raise HTTPException(409, "This interview is no longer accepting answers.")
                if str(state.turns[-1].id) != payload["question_id"] or state.turns[-1].answer is not None:
                    raise HTTPException(409, "This question has already changed or been answered.")
            if kind == "finish" and state.status == "finished":
                return state, None
            if kind == "start" and state.turns:
                raise HTTPException(409, "This interview has already started.")
            self._rate(db, "operations:" + digest(owner), 90)
            self._rate(db, "ai:global", 1500)
            if not operation:
                operation = Operation(interview_id=interview_id, id=operation_id,
                                      request_hash=expected_hash, kind=kind, status="pending")
                db.add(operation)
            operation.status = "pending"
            row.active_operation, row.fence = operation_id, uuid4()
            row.lease_until = now() + timedelta(seconds=100)
            row.status = "evaluating" if kind == "finish" else "generating_question"
            fence = row.fence
            return state, fence

    def complete(self, interview_id, owner, operation_id, fence, kind, payload, question, feedback):
        with Session(self.engine) as db, db.begin():
            row = self._authorized(db, interview_id, owner, lock=True)
            if row.active_operation != operation_id or row.fence != fence:
                raise HTTPException(409, "A newer request owns this operation. Reload the interview.")
            if kind == "answer":
                db.add(Answer(question_id=UUID(payload["question_id"]), text=payload["answer"], answered_at=now()))
                db.flush()
            state = self._state(db, row)
            if question:
                db.add(Question(id=uuid4(), interview_id=interview_id, position=len(state.turns) + 1,
                                text=question, fingerprint=fingerprint(question), asked_at=now()))
            if feedback is not None:
                db.add(Feedback(interview_id=interview_id, content=feedback))
                row.status, row.completed_at = "finished", now()
            elif kind == "answer" and state.answered_count >= state.question_count:
                row.status, row.completed_at = "completed", now()
            else:
                row.status = "in_progress"
            db.get(Operation, (interview_id, operation_id)).status = "done"
            row.active_operation = row.lease_until = row.fence = None
            db.flush()
            return self._state(db, row)

    def release(self, interview_id, operation_id, fence):
        with Session(self.engine) as db, db.begin():
            row = db.scalar(select(Interview).where(Interview.id == interview_id).with_for_update())
            if row and row.active_operation == operation_id and row.fence == fence:
                db.get(Operation, (interview_id, operation_id)).status = "failed"
                row.active_operation = row.lease_until = row.fence = None
                state = self._state(db, row)
                row.status = "completed" if state.answered_count >= state.question_count else "in_progress"

    def remove(self, interview_id, owner):
        with Session(self.engine) as db, db.begin():
            row = self._authorized(db, interview_id, owner, lock=True)
            db.delete(row)

    def cleanup(self):
        """Explicit maintenance command, never a response-lifetime background task."""
        with Session(self.engine) as db, db.begin():
            db.execute(delete(Interview).where(Interview.expires_at <= now()))
            db.execute(delete(RateBucket).where(RateBucket.window_start < now() - timedelta(days=1)))
