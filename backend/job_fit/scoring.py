"""The LLM never provides a percentage. All scoring is deterministic Python."""
from collections import Counter
from decimal import Decimal,ROUND_HALF_UP
from .schemas import Score,ScoreCategory

WEIGHTS={"mandatory":60,"preferred":25,"alignment":15}
POINTS={"matched":Decimal(1),"partial":Decimal("0.5"),"not_evidenced":Decimal(0),"uncertain":Decimal(0)}


def calculate_score(requirements, *, coverage_complete=True, layout_confidence="high",unassessed_count=None):
    if not requirements:
        raise ValueError("At least one validated job criterion is required for scoring")
    if unassessed_count is not None and (type(unassessed_count) is not int or not 0<=unassessed_count<=80):
        raise ValueError("Invalid unassessed group count")
    if any(r.importance not in WEIGHTS or r.status not in POINTS for r in requirements):
        raise ValueError("Score inputs must use validated categories and classifications")
    n=len(requirements)
    complete=bool(coverage_complete and not unassessed_count)
    gaps=0 if complete else unassessed_count if unassessed_count else None
    factor=Decimal(n)/Decimal(n+gaps) if gaps is not None else Decimal(1)
    scope="full_posting" if complete else "known_groups" if gaps else "assessed_requirements"
    present={k:[r for r in requirements if r.importance==k] for k in WEIGHTS}
    total_weight=sum(WEIGHTS[k] for k,items in present.items() if items)
    total=Decimal(0);categories=[]
    for key,items in present.items():
        counts=Counter(r.status for r in items)
        weight=Decimal(WEIGHTS[key])/Decimal(total_weight) if items and total_weight else Decimal(0)
        fraction=sum((POINTS[r.status] for r in items),Decimal(0))/len(items) if items else None
        contribution=weight*fraction*100 if fraction is not None else Decimal(0)
        total+=contribution
        categories.append(ScoreCategory(category=key,count=len(items),base_weight=WEIGHTS[key],
            effective_weight=round(float(weight*100),4),score=round(float(fraction*100),2) if fraction is not None else None,
            contribution=round(float(contribution*factor),4),**{s:counts[s] for s in POINTS}))
    uncertain=sum(r.status=="uncertain" for r in requirements)/n
    reason="Equal weight per criterion within each category; matched=1, partial=0.5, not evidenced/uncertain=0. Unused category weights are redistributed proportionally."
    concerns=[]
    if not complete:
        if gaps:
            concerns.append(f"{gaps} posting groups were not assessed and receive zero credit through a coverage adjustment.")
            reason+=f" Contributions are multiplied by {n}/{n+gaps} for known unassessed posting groups. A group may contain more than one criterion, so coverage is an estimate."
        else:
            concerns.append("The number of unassessed requirements is unknown. This score describes only assessed criteria, not the full posting.")
            reason+=" No missing count or penalty was invented. Full-posting coverage is unknown; interpret this as assessed-criteria alignment only."
    if layout_confidence=="low":concerns.append("CV reading order needs confirmation; source associations may be ambiguous.")
    elif layout_confidence=="medium":concerns.append("PDF reading order has moderate extraction confidence.")
    if uncertain:concerns.append(f"{sum(r.status=='uncertain' for r in requirements)} assessed criteria are uncertain and receive zero credit.")
    if n<3:concerns.append("This assessment contains fewer than three criteria; its scope is narrow.")
    confidence="low" if not complete or layout_confidence=="low" or uncertain>.4 else "moderate" if concerns else "high"
    provisional=not complete or layout_confidence=="low" or uncertain>0 or n<3
    return Score(overall=int((total*factor).quantize(Decimal("1"),rounding=ROUND_HALF_UP)),
        score_status="provisional" if provisional else "complete",confidence=confidence,confidence_reasons=concerns,
        scope=scope,assessed_count=n,unassessed_count=gaps,
        assessment_coverage=round(float(factor*100),2) if gaps is not None else None,
        assessed_alignment=round(float(total),4),coverage_factor=round(float(factor),8),
        reason=reason,categories=categories,evidence_coverage=round(100*sum(r.status in ("matched","partial") for r in requirements)/n,2) if n else 0,
        uncertain_share=round(uncertain*100,2))
