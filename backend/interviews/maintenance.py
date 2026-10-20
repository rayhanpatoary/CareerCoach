"""Run explicitly from an approved scheduler: python -m interviews.maintenance."""
from .database import get_engine
from .repository import PostgresRepository

if __name__ == "__main__":
    PostgresRepository(get_engine()).cleanup()
    print("Expired interview and rate-limit records removed.")
