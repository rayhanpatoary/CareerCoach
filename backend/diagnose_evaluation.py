"""Explicit live diagnostic for our synthetic verification record only.

Reads an existing record, makes ONE real evaluation call, and performs no writes.
Never logs transcript content or credentials. Not part of CI.
"""
import json
import sys
from pathlib import Path
from uuid import UUID
from unittest.mock import patch

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv(Path(__file__).with_name(".env"))

from main import get_client
from interviews.database import get_engine
from interviews.llm import NvidiaInterviewer
from interviews.schemas import Configuration, EvaluationOutput, weighted_score
from interviews.tables import Answer, Interview, Question

try:
    with Session(get_engine()) as db:
        row = db.get(Interview, UUID(sys.argv[1]))
        if not row or not row.configuration.get("job_description", "").startswith("Automated live verification interview."):
            raise ValueError("Only an explicitly marked synthetic verification record is allowed")
        configuration = Configuration(**row.configuration)
        transcript = [{"question_id":str(q.id), "id":str(q.id), "question":q.text, "answer":a.text}
            for q,a in db.execute(select(Question,Answer).join(Answer,Answer.question_id == Question.id).where(
                Question.interview_id == row.id).order_by(Question.position))]
    original_validator = EvaluationOutput.model_validate_json
    def capture_and_validate(content):
        # This helper is restricted above to our synthetic verification record.
        # Save the single response locally so schema fixes can be tested offline.
        target = Path(__file__).resolve().parents[1] / "frontend/test-results/live/evaluation-response.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        parsed = json.loads(content)
        print(json.dumps({"synthetic_response_top_level_fields":list(parsed) if isinstance(parsed,dict) else type(parsed).__name__}))
        return original_validator(content)
    with patch.object(EvaluationOutput, "model_validate_json", side_effect=capture_and_validate):
        output = NvidiaInterviewer(get_client).evaluate(configuration, transcript)
    score, coverage = weighted_score(output.categories)
    print(json.dumps({"evaluation_schema":"passed", "review_count":len(output.reviews),
                      "overall_score":score, "evidence_coverage":coverage, "database_writes":0}))
except Exception as error:
    print(json.dumps({"evaluation_schema":"failed", "error_type":type(error).__name__}))
    raise SystemExit(1)
