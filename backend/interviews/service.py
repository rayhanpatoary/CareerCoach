from fastapi import HTTPException

from .repository import fingerprint, now
from .schemas import (Categories, Category, Configuration, Evaluation, WEIGHTS, weighted_score)


class InterviewService:
    def __init__(self, repository, llm):
        self.repository, self.llm = repository, llm

    def start(self, request, owner):
        configuration = Configuration(**request.model_dump(include=set(Configuration.model_fields)))
        return self._run(request.operation_id, owner, request.operation_id, "start",
                         configuration.model_dump(), configuration)

    def answer(self, interview_id, request, owner):
        return self._run(interview_id, owner, request.operation_id, "answer",
                         request.model_dump(mode="json", exclude={"operation_id"}))

    def finish(self, interview_id, request, owner):
        return self._run(interview_id, owner, request.operation_id, "finish", {})

    def _run(self, interview_id, owner, operation_id, kind, payload, configuration=None):
        state, fence = self.repository.claim(interview_id, owner, operation_id, kind, payload, configuration)
        if fence is None:
            return state
        try:
            config = Configuration(**state.model_dump(include=set(Configuration.model_fields)))
            turns = [turn.model_dump(mode="json") for turn in state.turns]
            question, feedback = None, None
            if kind == "answer":
                turns[-1]["answer"] = payload["answer"]
                turns[-1]["answered_at"] = now().isoformat()
            if kind == "finish":
                answered = [turn for turn in turns if turn["answer"] is not None]
                if answered:
                    output = self.llm.evaluate(config, [dict(turn, question_id=turn["id"]) for turn in answered])
                    ids = [str(review.question_id) for review in output.reviews]
                    if len(ids) != len(set(ids)) or set(ids) != {turn["id"] for turn in answered}:
                        raise HTTPException(502, "The AI returned incomplete question feedback. Retry this action.")
                    overall, coverage = weighted_score(output.categories)
                    feedback = Evaluation(**output.model_dump(), overall_score=overall, evidence_coverage=coverage,
                                          partial=len(answered) < config.question_count,
                                          answered_count=len(answered), rubric=WEIGHTS).model_dump(mode="json")
                else:
                    feedback = Evaluation(categories=Categories(**{key: Category(score=None, evidence="No answers submitted.") for key in WEIGHTS}),
                                          summary="There are no submitted answers to evaluate.", strengths=[], improvements=[],
                                          knowledge_gaps=[], recommendations=[], practice_plan=["Start a new interview and submit an answer."],
                                          reviews=[], overall_score=None, evidence_coverage=0, partial=True,
                                          answered_count=0, rubric=WEIGHTS).model_dump(mode="json")
            elif kind == "start" or sum(turn["answer"] is not None for turn in turns) < config.question_count:
                question = self.llm.question(config, turns)
                if fingerprint(question) in {fingerprint(turn["question"]) for turn in turns}:
                    raise HTTPException(502, "The AI repeated a question. Retry this action; your answer has not been lost.")
            return self.repository.complete(interview_id, owner, operation_id, fence, kind, payload, question, feedback)
        except Exception:
            # An abandoned serverless invocation is recovered by lease/fencing instead.
            self.repository.release(interview_id, operation_id, fence)
            raise
