"""Validate JD provenance, CV citations and conservative direct-match gates."""
import re
from cv.document import normalize_text
from cv.grounding import GroundingError,verify_source_quote,validate_grounding
from cv.schemas import CvAnalysis

ALIASES=({"aws","amazon web services"},{".net","dotnet"},{"c#","csharp","c sharp"},
         {"c++","cpp"},{"postgresql","postgres"},{"next.js","nextjs"},{"ci/cd","continuous integration and delivery"})
NORM=lambda value:normalize_text(value,fold=True)
YEAR_WORDS={"one":"1","two":"2","three":"3","four":"4","five":"5","six":"6","seven":"7","eight":"8","nine":"9","ten":"10",
    "ein":"1","eine":"1","einem":"1","einen":"1","zwei":"2","drei":"3","vier":"4","fünf":"5","sechs":"6","sieben":"7","acht":"8","neun":"9","zehn":"10"}
YEARS=re.compile(r"\b(\d+(?:[.,]\d+)?|"+"|".join(YEAR_WORDS)+r")\s*(?:\+\s*)?(?:years?|jahre?|jahren)\b",re.I)


def durations(text):return {YEAR_WORDS.get(v,v).replace(",",".") for v in YEARS.findall(NORM(text))}


def mentioned(term,text):
    term=NORM(term);terms=next((values for values in ALIASES if term in values),{term})
    return any(re.search(r"(?<!\w)"+re.escape(value)+r"(?!\w)",NORM(text)) for value in terms)


def unassessed_job_sources(output,clauses):
    """Audit actual posting groups, never synthesize skills or classifications."""
    used={r.jd_source_id for r in output.requirements};context=set(output.context_source_ids)
    return [c.source_id for c in clauses if not c.heading and c.source_id not in used and
        (c.explicit_requirement or c.source_id not in context)]


def validate_job(output,clauses):
    sources={c.source_id:c for c in clauses};seen=set();used=set();warnings=[]
    for index,item in enumerate(output.requirements):
        source=sources.get(item.jd_source_id)
        if source is None:raise GroundingError("unknown_job_source")
        if source.heading:raise GroundingError("job_heading_is_not_requirement")
        if NORM(item.jd_quote) not in NORM(source.text):raise GroundingError("job_quote_not_in_source")
        if NORM(item.label) not in NORM(item.jd_quote):
            # Models sometimes prepend an English coaching verb to a copied
            # German noun phrase. Only remove that generic prefix when the
            # entire remaining phrase is literally present in the job quote.
            # Never translate skills, remove seniority/years, or accept a CV-only term.
            candidate=re.sub(r"^(?:develop|build|create|implement)\s+","",item.label,flags=re.I)
            if candidate!=item.label and len(candidate)>=2 and NORM(candidate) in NORM(item.jd_quote):
                item.label=candidate;warnings.append("requirement_label_source_normalized")
            else:raise GroundingError("requirement_label_not_in_quote",path=("requirements",index,"label"))
        label=NORM(item.label)
        if label in seen:raise GroundingError("duplicate_job_requirement")
        seen.add(label);used.add(item.jd_source_id)
        if source.importance_hint and item.importance!=source.importance_hint:
            raise GroundingError("job_importance_conflicts_with_source")
        if item.category=="responsibility" and not source.importance_hint and item.importance!="alignment":
            raise GroundingError("responsibility_should_use_alignment_weight")
    context=set(output.context_source_ids)
    if context-set(sources):raise GroundingError("unknown_context_source")
    if any(c.explicit_requirement and c.source_id not in used for c in clauses):
        output.coverage_complete=False;warnings.append("unassessed_explicit_job_clause")
    if set(sources)-used-context:output.coverage_complete=False;warnings.append("unassessed_job_clauses")
    return output,warnings


def validate_matches(output,document,clauses):
    output,warnings=validate_job(output,clauses)
    for index,item in enumerate(output.requirements):
        if item.status in ("matched","partial") and not item.evidence:
            raise GroundingError("positive_match_requires_cv_evidence")
        if item.status=="not_evidenced" and item.evidence:
            raise GroundingError("absent_match_has_contradictory_evidence")
        blocks=[]
        for citation_index,citation in enumerate(item.evidence):
            try:block=verify_source_quote(document,citation.source_id,citation.quote)
            except GroundingError as error:
                error.path=("matches",index,"evidence",citation_index,"source_id" if error.code=="unknown_source_id" else "quote")
                raise
            citation.page,citation.section=block.page,block.section;blocks.append(block)
        quoted=" ".join(c.quote for c in item.evidence)
        if item.status=="matched":
            # Literal skill/tool/language evidence is required for a direct match.
            # SQL Server is transferable evidence for PostgreSQL, never an exact match.
            if item.category in ("technical","tools","language","education","seniority") and not mentioned(item.label,quoted):
                item.status="partial";warnings.append("direct_match_downgraded")
            numbers=set(re.findall(r"\d+(?:[.,]\d+)*",item.jd_quote))
            if numbers-set(re.findall(r"\d+(?:[.,]\d+)*",quoted)):
                item.status="uncertain";warnings.append("quantitative_requirement_unverified")
            if durations(item.jd_quote)-durations(quoted):
                item.status="uncertain";warnings.append("experience_duration_unverified")
            if item.status=="matched" and item.category=="experience" and (not blocks or any(b.section!="experience" for b in blocks)):
                item.status="partial";warnings.append("professional_experience_context_unverified")
        if item.status=="not_evidenced" and item.category in ("technical","tools","language") and mentioned(item.label,document.text):
            # Presence elsewhere requires interpretation, not an invented full match.
            item.status="uncertain";warnings.append("present_keyword_requires_context")
        if item.status=="not_evidenced" and item.action_kind=="improve_wording":
            item.action_kind="add_truthful_evidence"
    if any(p.requirement_index>=len(output.requirements) for p in output.improvements):
        raise GroundingError("unknown_recommendation_requirement")
    rewrites=[]
    for rewrite in output.rewrites:
        try:verify_source_quote(document,rewrite.source_id,rewrite.original)
        except GroundingError:
            warnings.append("unsupported_rewrite_omitted")
            continue
        rewrites.append(rewrite)
    adapter=CvAnalysis(summary="Source-grounded rewrites",strengths=[],weaknesses=[],missing_skills=[],
        unclear_descriptions=[],content_errors=[],rewrites=rewrites,practice_plan=["Verify every change."])
    validate_grounding(adapter,document);output.rewrites=adapter.rewrites
    return output,list(dict.fromkeys(warnings))
