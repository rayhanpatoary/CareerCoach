"""Private durable interview storage. No Supabase Data API grants."""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    statements = [
        "CREATE SCHEMA career_coach",
        "REVOKE ALL ON SCHEMA career_coach FROM PUBLIC",
        """CREATE TABLE career_coach.interviews (
            id uuid PRIMARY KEY, owner_hash varchar(64) NOT NULL,
            configuration jsonb NOT NULL, status varchar(32) NOT NULL
            CHECK (status IN ('generating_question','in_progress','completed','evaluating','finished')),
            started_at timestamptz NOT NULL, completed_at timestamptz,
            expires_at timestamptz NOT NULL, active_operation uuid,
            lease_until timestamptz, fence uuid)""",
        "CREATE INDEX ix_career_coach_interviews_owner_hash ON career_coach.interviews(owner_hash)",
        "CREATE INDEX ix_career_coach_interviews_expires_at ON career_coach.interviews(expires_at)",
        """CREATE TABLE career_coach.questions (
            id uuid PRIMARY KEY, interview_id uuid NOT NULL REFERENCES career_coach.interviews(id) ON DELETE CASCADE,
            position integer NOT NULL CHECK (position BETWEEN 1 AND 8), text varchar(1800) NOT NULL,
            fingerprint varchar(64) NOT NULL, asked_at timestamptz NOT NULL,
            UNIQUE(interview_id, position), UNIQUE(interview_id, fingerprint))""",
        "CREATE INDEX ix_career_coach_questions_interview_id ON career_coach.questions(interview_id)",
        """CREATE TABLE career_coach.answers (
            question_id uuid PRIMARY KEY REFERENCES career_coach.questions(id) ON DELETE CASCADE,
            text varchar(6000) NOT NULL, answered_at timestamptz NOT NULL)""",
        """CREATE TABLE career_coach.evaluations (
            interview_id uuid PRIMARY KEY REFERENCES career_coach.interviews(id) ON DELETE CASCADE,
            content jsonb NOT NULL)""",
        """CREATE TABLE career_coach.operations (
            interview_id uuid NOT NULL REFERENCES career_coach.interviews(id) ON DELETE CASCADE,
            id uuid NOT NULL, request_hash varchar(64) NOT NULL, kind varchar(16) NOT NULL,
            status varchar(16) NOT NULL CHECK(status IN ('pending','failed','done')),
            PRIMARY KEY(interview_id, id))""",
        """CREATE TABLE career_coach.rate_buckets (
            key varchar(100) NOT NULL, window_start timestamptz NOT NULL, count integer NOT NULL,
            PRIMARY KEY(key, window_start))""",
        "REVOKE ALL ON ALL TABLES IN SCHEMA career_coach FROM PUBLIC",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA career_coach REVOKE ALL ON TABLES FROM PUBLIC",
    ]
    for statement in statements:
        op.execute(statement)
    # Supabase roles exist in Supabase but not necessarily in a plain CI database.
    for role in ("anon", "authenticated", "service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'REVOKE ALL ON SCHEMA career_coach FROM {role}';
            EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA career_coach FROM {role}';
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA career_coach REVOKE ALL ON TABLES FROM {role}';
        END IF; END $$""")


def downgrade():
    for table in ("rate_buckets", "operations", "evaluations", "answers", "questions", "interviews"):
        op.execute(f"DROP TABLE career_coach.{table}")
    op.execute("DROP SCHEMA career_coach")
