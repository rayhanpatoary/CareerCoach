"""Safe stage diagnostics, independent of user documents and provider text."""
from contextlib import contextmanager
from fastapi import HTTPException
from pydantic import ValidationError
from cv.grounding import GroundingError

LABELS={"job_requirements":"Job-description analysis","cv_matching":"CV-to-job evidence matching"}


@contextmanager
def analysis_stage(stage):
    try:yield
    except (HTTPException,ValueError) as error:
        if isinstance(error,HTTPException) and error.status_code not in (502,504):raise
        cause=error.__cause__ if isinstance(error,HTTPException) else error
        code=cause.code if isinstance(cause,GroundingError) else "invalid_structure" if isinstance(cause,ValidationError) else "provider_timeout" if isinstance(error,HTTPException) and error.status_code==504 else "invalid_response"
        status=error.status_code if isinstance(error,HTTPException) else 502
        message=(f"{LABELS[stage]} took too long. Retry the same analysis; no feedback was saved." if status==504 else
            f"{LABELS[stage]} could not be verified. Retry the same analysis. No feedback was saved.")
        raise HTTPException(status,detail=message,headers={"X-Analysis-Stage":stage,"X-Analysis-Code":code}) from error
