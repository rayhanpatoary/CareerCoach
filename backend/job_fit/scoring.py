"""The LLM never provides a percentage. All scoring is deterministic Python."""
from collections import Counter
from decimal import Decimal,ROUND_HALF_UP
from .schemas import Score,ScoreCategory

WEIGHTS={"mandatory":60,"preferred":25,"alignment":15}
POINTS={"matched":Decimal(1),"partial":Decimal("0.5"),"not_evidenced":Decimal(0),"uncertain":Decimal(0)}


def calculate_score(requirements, *, coverage_complete=True, layout_confidence="high"):
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
            contribution=round(float(contribution),4),**{s:counts[s] for s in POINTS}))
    n=len(requirements)
    uncertain=sum(r.status=="uncertain" for r in requirements)/n if n else 1
    reason="Equal weight per criterion within each category; matched=1, partial=0.5, not evidenced/uncertain=0. Unused category weights are redistributed proportionally."
    withheld=[]
    if n<3:withheld.append("fewer than three distinct criteria")
    if not present["mandatory"]:withheld.append("no mandatory criteria identified")
    if not coverage_complete:withheld.append("job-description coverage is incomplete")
    if uncertain>.4:withheld.append("more than 40% of criteria are uncertain")
    if layout_confidence=="low":withheld.append("CV reading order needs confirmation")
    if withheld:reason="Overall score withheld: "+"; ".join(withheld)+". Category values are provisional."
    return Score(overall=None if withheld else int(total.quantize(Decimal("1"),rounding=ROUND_HALF_UP)),
        reason=reason,categories=categories,evidence_coverage=round(100*sum(r.status in ("matched","partial") for r in requirements)/n,2) if n else 0,
        uncertain_share=round(uncertain*100,2))
