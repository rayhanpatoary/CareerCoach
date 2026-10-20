import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv

from interviews.database import build_engine, database_url
from interviews.tables import Base

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
raw = os.getenv("DIRECT_DATABASE_URL", "").strip()
if not raw:
    raise RuntimeError("Set DIRECT_DATABASE_URL to the direct or session-pooler PostgreSQL URL")

if context.is_offline_mode():
    context.configure(url=database_url(raw), target_metadata=Base.metadata,
                      literal_binds=True, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with build_engine(raw).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, include_schemas=True)
        with context.begin_transaction():
            # Serialize concurrent migration invocations. Transaction-local only.
            connection.exec_driver_sql("SELECT pg_advisory_xact_lock(78315624)")
            context.run_migrations()
