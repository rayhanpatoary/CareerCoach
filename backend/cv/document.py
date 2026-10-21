"""In-memory source representation. Never persist this document or log its text."""
import re
import unicodedata
from dataclasses import dataclass, field

# These productive compound prefixes need their hyphen even at a line wrap.
COMPOUND_PREFIXES = {"full", "part", "real", "cross", "open", "end", "client", "server",
                     "well", "high", "low", "long", "short", "state", "front", "back"}
TRANSLATION = str.maketrans({"“":'"', "”":'"', "„":'"', "‘":"'", "’":"'",
    "–":"-", "—":"-", "−":"-", "•":"-", "●":"-", "▪":"-", "◦":"-",
    "\u200b":"", "\ufeff":"", "\u00a0":" "})


def normalize_text(value, *, fold=False):
    value = unicodedata.normalize("NFKC", value).translate(TRANSLATION)
    value = re.sub(r"\u00ad\s*\n\s*", "", value).replace("\u00ad", "")
    def unwrap(match):
        left, right = match.group(1), match.group(2)
        # Unknown capitalized continuations may be intentional compound nouns.
        camel_suffix = right in {"Lib", "Kit", "Script", "Chain", "Core", "Net"}
        keep = left.casefold() in COMPOUND_PREFIXES or left.isupper() or right.isupper() or (right[0].isupper() and not camel_suffix)
        return left + ("-" if keep else "") + right
    value = re.sub(r"([^\W\d_]{2,})-\s*\n\s*([^\W\d_]{2,})", unwrap, value)
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.casefold() if fold else value


HEADINGS = {
    "summary": {"summary", "professional summary", "profile", "profil", "kurzprofil", "about me"},
    "experience": {"professional experience", "work experience", "experience", "experiences", "employment", "employment history", "berufserfahrung", "beruflicher werdegang"},
    "education": {"education", "ausbildung", "studium", "academic background"},
    "skills": {"skills", "technical skills", "technische kenntnisse", "kenntnisse", "technologien", "problem solving & algorithms"},
    "projects": {"project", "projects", "projekte", "projektarbeit"},
    "projects_training": {"projects & training", "project & training", "projekte & weiterbildung"},
    "training": {"training", "weiterbildung", "fortbildungen", "courses", "kurse"},
    "certifications": {"certifications", "certificates", "zertifikate", "zertifizierungen"},
    "publications": {"publication", "publications", "publikationen", "veröffentlichungen"},
    "languages": {"languages", "language skills", "sprachen", "sprachkenntnisse"},
}


def section_heading(text):
    key = normalize_text(text, fold=True).strip(" :-|")
    # Common heading suffixes such as "Experience · 4 years" are not entry dates.
    key=re.sub(r"\s*[\ufffd:|·-]?\s*\d+(?:[.,]\d+)?\s*(?:years?|jahre?)\s*$","",key).strip()
    compact=lambda v:re.sub(r"[^\w]","",v)
    return next((name for name, labels in HEADINGS.items() if compact(key) in {compact(v) for v in labels}), None)


@dataclass
class SourceBlock:
    source_id: str
    original: str
    text: str
    section: str = "unclassified"
    page: int | None = None
    column: int | None = None
    bbox: list[float] | None = None
    # Each original line retains its own coordinates, including wrapped words.
    lines: list[dict] = field(default_factory=list)


@dataclass
class ResumeDocument:
    blocks: list[SourceBlock]
    source: str
    page_count: int | None = None
    confidence: str = "high"
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self):
        return "\n\n".join(block.text for block in self.blocks)

    def payload(self):
        return {"layout_confidence": self.confidence, "warnings": self.warnings,
            "sections": {name:[block.source_id for block in self.blocks if block.section == name]
                         for name in dict.fromkeys(b.section for b in self.blocks)},
            "sources": [{"source_id":b.source_id, "section":b.section, "text":b.text,
                         "page":b.page, "column":b.column} for b in self.blocks]}


def text_document(text):
    blocks, section, pending = [], "unclassified", []
    def flush():
        if not pending:return
        raw = "\n".join(pending)
        blocks.append(SourceBlock(f"text_{len(blocks)+1:03d}", raw, normalize_text(raw), section))
        pending.clear()
    for line in text.splitlines():
        heading = section_heading(line)
        if heading:
            flush(); section = heading
        elif not line.strip():
            flush(); continue
        if sum(len(v) for v in pending)+len(line)>1800:flush()
        # One oversized pasted line is split at whitespace, never silently truncated.
        while len(line)>1800:
            cut=line.rfind(" ",0,1800)
            if cut<1:cut=1800
            pending.append(line[:cut]);flush();line=line[cut:].lstrip()
        pending.append(line)
    flush()
    return ResumeDocument(blocks,"text")
