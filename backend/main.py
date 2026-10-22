import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI, OpenAIError, APITimeoutError
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from interviews.schemas import StartRequest
from interviews.routes import router, get_service, get_repository, owner_credential
from cv.routes import router as cv_router
from job_fit.routes import router as job_fit_router

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="AI Career Coach API")
app.include_router(router)
app.include_router(cv_router)
app.include_router(job_fit_router)


@app.middleware("http")
async def private_interview_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/interview", "/api/cv", "/api/job-fit")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
def storage_error(request, error):
    # Do not log connection URLs, SQL parameters, transcripts or upstream errors.
    return JSONResponse(status_code=503, content={"detail": "Career Coach storage is temporarily unavailable. Retry this action."})

# Allow Next.js development frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000"
    ).split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["POST", "GET", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

def get_client():
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="The AI service is not configured.")
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
        timeout=60.0,
        max_retries=0,
    )

class InterviewRequest(BaseModel):
    job_role: str = Field(min_length=2, max_length=100)
    difficulty: Literal[
        "beginner", "intermediate", "advanced"
    ] = "beginner"


@app.get("/")
def home():
    return {"message": "AI Career Coach API is running"}


@app.post("/api/interview/start")
def start_interview(request: StartRequest, response: Response, authorization: str = Header(default="")):
    response.headers["Cache-Control"] = "no-store"
    if request.persistent:
        owner = owner_credential(authorization)
        return get_service(get_repository()).start(request, owner)
    if os.getenv("LEGACY_INTERVIEW_ENABLED", "true").lower() == "false":
        raise HTTPException(410, "Use the interview workspace to start a persistent interview.")
    if os.getenv("DATABASE_URL", "").strip():
        get_repository().reserve_legacy_request()
    try:
        with get_client() as client:
            return generate_question(client, request)
    except APITimeoutError as error:
        raise HTTPException(
            status_code=504, detail="Question generation timed out. Please try again."
        ) from error
    except OpenAIError as error:
        raise HTTPException(
            status_code=502,
            detail="Unable to generate an interview question."
        ) from error


@app.get("/health")
def health():
    return {"status": "ok"}


def generate_question(client: OpenAI, request: InterviewRequest):
    response = client.chat.completions.create(
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional job interviewer. "
                    "Ask exactly one interview question. "
                    "Match the user's job role and difficulty. "
                    "For beginners, avoid advanced topics. "
                    "Do not provide the answer."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Job role: {request.job_role}\n"
                    f"Difficulty: {request.difficulty}\n"
                    "Start the interview."
                )
            }
        ],
        max_tokens=300,
        temperature=0.6,
        extra_body={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
    )

    question = response.choices[0].message.content if response.choices else None

    if not question or not question.strip():
        raise HTTPException(
            status_code=502,
            detail="The AI returned an empty response."
        )

    return {
        "job_role": request.job_role,
        "difficulty": request.difficulty,
        "question": question.strip()
    }
