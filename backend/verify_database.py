"""Non-destructive Supabase verification. Never prints credentials or row content.

--upgrade applies reviewed pending Alembic upgrades; no downgrade/reset exists.
--write-probe inserts uniquely identified probe rows in one rolled-back transaction.
"""
import argparse
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import inspect, insert, select, text

from interviews.database import build_engine
from interviews.repository import digest, now
from interviews.schemas import Configuration
from interviews.tables import Answer, Feedback, Interview, Operation, Question, RateBucket, SCHEMA


def revision(engine):
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def write_probe(engine):
    interview_id, question_id = uuid4(), uuid4()
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(insert(Interview).values(id=interview_id, owner_hash=digest(str(uuid4())),
                configuration=Configuration(job_role="Database verification probe").model_dump(),
                status="finished", started_at=now(), completed_at=now(), expires_at=now()+timedelta(minutes=5)))
            connection.execute(insert(Question).values(id=question_id, interview_id=interview_id, position=1,
                text="Database write probe; transaction will be rolled back.", fingerprint=digest(str(question_id)), asked_at=now()))
            connection.execute(insert(Answer).values(question_id=question_id, text="Nonpersistent connectivity probe.", answered_at=now()))
            connection.execute(insert(Feedback).values(interview_id=interview_id, content={"database_probe_only": True}))
            connection.execute(insert(Operation).values(interview_id=interview_id, id=uuid4(), request_hash=digest("probe"), kind="start", status="done"))
            connection.execute(insert(RateBucket).values(key="probe:"+str(interview_id), window_start=now(), count=1))
            assert connection.scalar(select(Answer.text).where(Answer.question_id == question_id)) == "Nonpersistent connectivity probe."
            assert connection.scalar(select(Feedback.content).where(Feedback.interview_id == interview_id))["database_probe_only"]
        finally:
            transaction.rollback()
    with engine.connect() as connection:
        assert connection.scalar(select(Interview.id).where(Interview.id == interview_id)) is None
    return "passed; all probe writes rolled back, no existing data modified"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument("--write-probe", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).parent
    load_dotenv(root / ".env")
    config = Config(str(root / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    direct = os.getenv("DIRECT_DATABASE_URL", "").strip()
    runtime = os.getenv("DATABASE_URL", "").strip()
    if not direct or not runtime:
        raise RuntimeError("Both backend database variables are required")
    direct_engine, engine = build_engine(direct), build_engine(runtime)
    try:
        current = revision(direct_engine)
        print(json.dumps({"direct_or_session_connection": "passed", "current_revision": current, "migration_head": head}), flush=True)
        if args.upgrade and current != head:
            command.upgrade(config, "head")
            current = revision(direct_engine)
        with engine.connect() as connection:
            tables = sorted(inspect(connection).get_table_names(schema=SCHEMA))
            expected = sorted(["interviews", "questions", "answers", "evaluations", "operations", "rate_buckets"])
            privileges = {}
            for role in ("anon", "authenticated", "service_role"):
                exists = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role})
                if exists:
                    privileges[role] = bool(connection.scalar(text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"), {"role":role, "schema":SCHEMA}))
            print(json.dumps({"runtime_pooler_connection": "passed", "current_revision": current,
                "tables": tables, "expected_tables_present": set(expected).issubset(tables),
                "prepared_statements_disabled": connection.connection.driver_connection.prepare_threshold is None,
                "api_role_schema_access": privileges}), flush=True)
            if current != head or not set(expected).issubset(tables) or any(privileges.values()):
                raise RuntimeError("Migration, table or private-schema checks did not pass")
        if args.write_probe:
            print(json.dumps({"read_write_probe": write_probe(engine)}), flush=True)
    finally:
        direct_engine.dispose(); engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        original = getattr(error, "orig", error)
        print(json.dumps({"verification": "failed", "error_type": type(error).__name__,
                          "sqlstate": getattr(original, "sqlstate", None)}), flush=True)
        raise SystemExit(1)
