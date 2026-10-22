"""Add private job-fit history; preserve all interview and CV data."""
from alembic import op
revision="0003"
down_revision="0002"
branch_labels=None
depends_on=None


def upgrade():
    op.execute("""CREATE TABLE career_coach.job_fit_analyses (
        id uuid PRIMARY KEY, owner_hash varchar(64) NOT NULL, request_hash varchar(64) NOT NULL,
        job_role varchar(100) NOT NULL, source varchar(8) NOT NULL CHECK(source IN ('pdf','text')),
        status varchar(16) NOT NULL CHECK(status IN ('processing','failed','finished')),
        character_count integer NOT NULL, page_count integer,
        created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
        lease_until timestamptz, fence uuid, analysis jsonb)""")
    op.execute("CREATE INDEX ix_career_coach_job_fit_analyses_owner_hash ON career_coach.job_fit_analyses(owner_hash)")
    op.execute("CREATE INDEX ix_career_coach_job_fit_analyses_expires_at ON career_coach.job_fit_analyses(expires_at)")
    op.execute("REVOKE ALL ON TABLE career_coach.job_fit_analyses FROM PUBLIC")
    for role in ("anon","authenticated","service_role"):
        op.execute(f"""DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE 'REVOKE ALL ON TABLE career_coach.job_fit_analyses FROM {role}';
        END IF; END; $$""")


def downgrade():
    op.execute("DROP TABLE career_coach.job_fit_analyses")
