import os
from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


def database_url(raw: str):
    url = make_url(raw)
    if url.get_backend_name() not in ("postgres", "postgresql"):
        raise ValueError("PostgreSQL is required")
    return url.set(drivername="postgresql+psycopg")


def build_engine(raw: str):
    # Supavisor transaction mode cannot keep session-level prepared statements.
    engine = create_engine(database_url(raw), poolclass=NullPool, hide_parameters=True,
                         connect_args={"prepare_threshold": None, "connect_timeout": 5,
                                       "sslmode": database_url(raw).query.get("sslmode", "require")})
    install_transaction_limits(engine)
    return engine


def install_transaction_limits(engine):
    @event.listens_for(engine, "begin")
    def limits(connection):
        # SET LOCAL is scoped to the transaction, safe with Supavisor pooling.
        connection.exec_driver_sql("SET LOCAL statement_timeout = '8000'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '3000'")


@lru_cache(maxsize=1)
def get_engine():
    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        raise HTTPException(503, "Interview storage is not configured.")
    try:
        return build_engine(raw)
    except (ValueError, TypeError):
        raise HTTPException(503, "Interview storage configuration is invalid.") from None
