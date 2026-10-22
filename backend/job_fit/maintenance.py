"""Explicit operator-scheduled expiry cleanup: python -m job_fit.maintenance."""
from pathlib import Path
from dotenv import load_dotenv
from interviews.database import get_engine
from .repository import JobFitRepository

if __name__=="__main__":
    load_dotenv(Path(__file__).resolve().parents[1]/".env")
    JobFitRepository(get_engine()).cleanup()
    print("Expired job-fit analyses removed.")
