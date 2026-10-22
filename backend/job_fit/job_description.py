"""Small traceable JD clauses; no job text is persisted by this parser."""
import re
from dataclasses import dataclass
from cv.document import normalize_text

PREFERRED=re.compile(r"\b(preferred|optional|nice.to.have|a plus|desirable|wünschenswert|von vorteil|idealerweise|pluspunkt)\b",re.I)
MANDATORY=re.compile(r"\b(must|required|mandatory|essential|erforderlich|voraussetzung|zwingend|muss|müssen)\b",re.I)
RESPONSIBILITY=re.compile(r"^(responsibilities|your responsibilities|your tasks|aufgaben|deine aufgaben|ihre aufgaben)\s*:?$",re.I)
PROFILE=re.compile(r"^(requirements|qualifications|your profile|profile|anforderungen|dein profil|ihr profil)\s*:?$",re.I)
HEADING=re.compile(r"^(?:(?:required|mandatory|preferred|essential)\s+(?:skills|qualifications|requirements)|requirements|qualifications|your profile|profile|anforderungen|dein profil|ihr profil|wünschenswert|optional|nice.to.have|benefits|about us|über uns|wir bieten)\s*:?$",re.I)


@dataclass
class JobClause:
    source_id: str
    text: str
    importance_hint: str | None
    explicit_requirement: bool
    heading: bool = False


def parse_job_description(text):
    clauses=[];hint=None
    for line in text.splitlines():
        line=line.strip().lstrip("•●▪- ")
        if not line:continue
        heading=bool(HEADING.fullmatch(line) or RESPONSIBILITY.fullmatch(line))
        if heading:
            if PREFERRED.search(line):hint="preferred"
            elif MANDATORY.search(line) or PROFILE.fullmatch(line):hint="mandatory"
            elif RESPONSIBILITY.match(line):hint="alignment"
            elif re.fullmatch(r"(benefits|about us|über uns|wir bieten):?",line,re.I):hint=None
        for sentence in re.split(r"(?<=[.!?;])\s+(?=[A-ZÄÖÜ])",line):
            # Bound individual sources without dropping long clauses.
            while sentence:
                cut=len(sentence) if len(sentence)<=500 else sentence.rfind(" ",0,500)
                if cut<1:cut=min(500,len(sentence))
                chunk=normalize_text(sentence[:cut]);sentence=sentence[cut:].lstrip()
                preferred,mandatory=bool(PREFERRED.search(chunk)),bool(MANDATORY.search(chunk))
                # A mixed sentence can contain criteria with different importance.
                # Preserve it for the model instead of forcing one weight on all items.
                local=None if preferred and mandatory else "preferred" if preferred else "mandatory" if mandatory else hint
                explicit=not heading and bool(PREFERRED.search(chunk) or MANDATORY.search(chunk))
                clauses.append(JobClause(f"jd_{len(clauses)+1:03d}",chunk,local,explicit,heading))
    return clauses
