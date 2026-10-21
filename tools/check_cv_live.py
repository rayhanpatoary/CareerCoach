"""Opt-in NVIDIA contract smoke check using synthetic text, without a database.

Run from backend: python ../tools/run_check.py 80 python ../tools/check_cv_live.py --live
Never run this in CI. No CV, key, response text or connection string is printed.
"""
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))


def main():
    if sys.argv[1:] != ["--live"]:
        raise SystemExit("Pass --live to authorize a real, billable NVIDIA request using synthetic text.")
    from fastapi import HTTPException
    from main import get_client
    from interviews.llm import NvidiaInterviewer
    from cv.schemas import ReviewRequest
    from cv.service import CvService

    class MemorySink:
        # Deliberately never connects to storage. Only the analysis transport is checked.
        def claim(self,*args):return None,uuid4()
        def complete(self,review_id,owner,fence,analysis):return analysis
        def release(self,*args):pass

    source=("Professional Experience\nBackend developer. Built a Python and FastAPI task tracking API with PostgreSQL. "
        "Wrote pytest unit tests for validation and documented the API setup. "
        "Collaborated with a designer to clarify error messages. Education: software development bootcamp. "
        "\nTechnical Skills\nPython, SQL, Git, FastAPI and PostgreSQL.\nProjects\nCreated a Next.js task dashboard for the API.")
    request=ReviewRequest(operation_id=uuid4(),job_role="Full Stack Developer",
        job_description="Entwickle Python APIs und Angular/Next.js Anwendungen. PostgreSQL-Kenntnisse, automatisierte Tests und CI/CD sind erwünscht. Collaborate with designers.",cv_text=source)
    try:
        result=CvService(MemorySink(),NvidiaInterviewer(get_client)).review(request,"synthetic-smoke-owner")
    except HTTPException as e:
        raise SystemExit(f"NVIDIA smoke check failed with HTTP {e.status_code}: {e.detail}") from None
    print(f"Live NVIDIA CV contract passed: {len(result.strengths)} strengths, {len(result.practice_plan)} practice steps; no database writes.")


if __name__=="__main__":main()
