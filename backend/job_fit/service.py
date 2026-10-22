import json
from dataclasses import asdict
from fastapi import HTTPException
from cv.extraction import extract_document
from cv.schemas import ExtractionInfo
from interviews.repository import digest
from interviews.llm import GenerationBudget
from .job_description import parse_job_description
from .grounding import validate_matches,validate_job
from .schemas import ModelOutput,JobFitAnalysis,AssessedRequirement,ParsedJob,ClassifiedMatches
from .scoring import calculate_score
from .prompts import JOB_INSTRUCTIONS,MATCH_INSTRUCTIONS

EXPLANATIONS={
    "matched":"The cited CV text directly supports this criterion. Verify its scope against the job quote.",
    "partial":"Related or transferable evidence is cited; the exact requirement or its scope is not fully demonstrated.",
    "not_evidenced":"No sufficient supporting evidence was identified in this CV. This does not establish your actual knowledge or ability.",
    "uncertain":"The available context is too ambiguous to establish a reliable match. Clarify the cited information if applicable.",
}


class JobFitService:
    def __init__(self,repository,llm):self.repository,self.llm=repository,llm

    def analyze(self,request,owner):
        document=extract_document(request)
        clauses=parse_job_description(request.job_description)
        if sum(c.isalpha() for c in request.job_description)<50 or len(request.job_description.split())<10:
            raise HTTPException(422,"Paste a readable job description with responsibilities and requirements (at least 10 words).")
        if len(clauses)>80:raise HTTPException(422,"This posting is too fragmented. Paste a focused description with up to 80 clauses.")
        fingerprint=digest(digest(owner)+json.dumps([request.job_role,request.company,request.job_description,document.text,document.source],ensure_ascii=False))
        cached,fence=self.repository.claim(request.operation_id,owner,fingerprint,request.job_role,document.source,len(document.text),document.page_count)
        if fence is None:return cached
        try:
            diagnostics=[];budget=GenerationBudget()
            def validate_parsed(value):
                result,warnings=validate_job(value,clauses);diagnostics.extend(warnings);return result
            # Stage 1 cannot see the CV. Stage 2 cannot invent requirements: it
            # returns classifications for fixed, validated criterion indices.
            job=self.llm.generate_json(JOB_INSTRUCTIONS,{"job_title":request.job_role,
                "job_sources":[asdict(c) for c in clauses]},ParsedJob,tokens=2500,validator=validate_parsed,budget=budget)
            validate_parsed(job)
            if not job.requirements:
                raise HTTPException(422,"No assessable job criteria were identified. Paste the posting's responsibilities and required or preferred qualifications.")
            def assemble(value):
                indices=[m.requirement_index for m in value.matches]
                if sorted(indices)!=list(range(len(job.requirements))):
                    raise ValueError("Match indices must cover each fixed requirement exactly once")
                by_index={m.requirement_index:m for m in value.matches}
                return ModelOutput(**job.model_dump(exclude={"requirements"}),
                    requirements=[{**r.model_dump(),**by_index[i].model_dump(exclude={"requirement_index"})} for i,r in enumerate(job.requirements)],
                    improvements=value.improvements,rewrites=value.rewrites)
            def validate_classifications(value):
                result,warnings=validate_matches(assemble(value),document,clauses);diagnostics.extend(warnings)
                # Keep backend corrections when assembling the final response.
                for i,item in enumerate(result.requirements):
                    match=next(m for m in value.matches if m.requirement_index==i)
                    match.status,match.evidence,match.action_kind=item.status,item.evidence,item.action_kind
                value.rewrites=result.rewrites
                return value
            classified=self.llm.generate_json(MATCH_INSTRUCTIONS,{"requirements":[dict(requirement_index=i,**r.model_dump()) for i,r in enumerate(job.requirements)],
                "cv":document.payload()},ClassifiedMatches,tokens=3500,validator=validate_classifications,budget=budget)
            output=assemble(classified)
            try:output,warnings=validate_matches(output,document,clauses)
            except ValueError as error:
                raise HTTPException(502,"The AI could not verify its job-fit evidence. No analysis was saved. Retry the same action.") from error
            analysis=JobFitAnalysis(company=request.company,language=output.language,
                requirements=[AssessedRequirement(**r.model_dump(),id=f"requirement_{i+1:02d}",explanation=EXPLANATIONS[r.status]) for i,r in enumerate(output.requirements)],
                score=calculate_score(output.requirements,coverage_complete=output.coverage_complete,layout_confidence=document.confidence),
                improvements=output.improvements,rewrites=output.rewrites,coverage_complete=output.coverage_complete,
                warnings=list(dict.fromkeys(diagnostics+warnings+document.warnings)),
                extraction=ExtractionInfo(confidence=document.confidence,warnings=document.warnings,source_block_count=len(document.blocks),page_count=document.page_count))
            return self.repository.complete(request.operation_id,owner,fence,analysis)
        except ValueError as error:
            self.repository.release(request.operation_id,owner,fence)
            raise HTTPException(502,"The AI could not verify its job-fit evidence. No analysis was saved. Retry the same action.") from error
        except Exception:
            self.repository.release(request.operation_id,owner,fence)
            raise
