from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "career_coach"


class Base(DeclarativeBase):
    pass


class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = (CheckConstraint("status in ('generating_question','in_progress','completed','evaluating','finished')"),
                      {"schema": SCHEMA})
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    active_operation: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fence: Mapped[UUID | None] = mapped_column(Uuid)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("interview_id", "position"),
                      UniqueConstraint("interview_id", "fingerprint"),
                      CheckConstraint("position between 1 and 8"), {"schema": SCHEMA})
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.interviews.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(1800))
    fingerprint: Mapped[str] = mapped_column(String(64))
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = ({"schema": SCHEMA},)
    question_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.questions.id", ondelete="CASCADE"), primary_key=True)
    text: Mapped[str] = mapped_column(String(6000))
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Feedback(Base):
    __tablename__ = "evaluations"
    __table_args__ = ({"schema": SCHEMA},)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.interviews.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[dict] = mapped_column(JSONB)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (CheckConstraint("status in ('pending','failed','done')"), {"schema": SCHEMA})
    interview_id: Mapped[UUID] = mapped_column(ForeignKey(f"{SCHEMA}.interviews.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    __table_args__ = ({"schema": SCHEMA},)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
