"""Opt-in synthetic NVIDIA job-fit contract check. No database connection or writes.

From backend: python ../tools/run_check.py 80 ./.venv/Scripts/python.exe ../tools/check_job_fit_live.py --live
Never invoked by CI. Prints aggregate diagnostics only.
"""
import sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))


def main():
    if sys.argv[1:] not in (["--live"],["--live","--diagnostics"]):raise SystemExit("Pass --live to send synthetic text to the configured NVIDIA provider.")
    from fastapi import HTTPException
    from main import get_client
    from interviews.llm import NvidiaInterviewer
    from job_fit.schemas import JobFitRequest
    from job_fit.service import JobFitService

    class SyntheticDiagnosticTransport(NvidiaInterviewer):
        def generate_json(self,*args,**kwargs):
            original=kwargs["validator"]
            def validate(value):
                try:return original(value)
                except ValueError:
                    # This tool constructs its own synthetic sources below. Never
                    # enable this diagnostic transport for a user-submitted CV.
                    from cv.document import normalize_text
                    for item in getattr(value,"requirements",[]):
                        if normalize_text(item.label,fold=True) not in normalize_text(item.jd_quote,fold=True):
                            print(f"Synthetic label mismatch: {item.label!r}; job excerpt: {item.jd_quote!r}")
                    raise
            kwargs["validator"]=validate
            return super().generate_json(*args,**kwargs)

    class MemorySink:
        def claim(self,*args):return None,uuid4()
        def complete(self,i,o,f,analysis):return analysis
        def release(self,*args):pass

    cv=("Professional Experience\nBackend developer at Example Company. Built Python and FastAPI APIs with SQL Server. "
        "Wrote pytest tests and documented the setup. Collaborated with designers on clear error messages.\n"
        "Technical Skills\nPython, FastAPI, SQL Server, Git.\nProjects\nCreated a Next.js task dashboard.")
    jd=("Required skills:\nPython is required for backend development.\nPostgreSQL is required for relational data.\n"
        "Preferred qualifications:\nDocker is preferred for packaging services.\nResponsibilities:\nCollaborate with designers.\n"
        "Aufgaben: Entwickle wartbare APIs für interne Anwendungen.")
    request=JobFitRequest(operation_id=uuid4(),job_role="Backend Developer",company="Synthetic Example",cv_text=cv,job_description=jd)
    transport=SyntheticDiagnosticTransport if "--diagnostics" in sys.argv else NvidiaInterviewer
    try:analysis=JobFitService(MemorySink(),transport(get_client)).analyze(request,"synthetic-job-fit-owner")
    except HTTPException as error:raise SystemExit(f"Synthetic NVIDIA contract failed: HTTP {error.status_code}: {error.detail}") from None
    print(f"Synthetic NVIDIA job-fit contract passed: {len(analysis.requirements)} criteria; score {analysis.score.overall}; coverage {analysis.coverage_complete}; {len(analysis.warnings)} validation warnings; no database writes.")


if __name__=="__main__":main()
