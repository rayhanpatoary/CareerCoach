"""Source-grounded analysis contract and deterministic citation validation."""
import re
from typing import Literal
from pydantic import Field
from .document import normalize_text
from .schemas import CvAnalysis, Finding, Rewrite

Label = Literal["Relevant professional experience", "Relevant technical skills", "Practical project evidence",
    "Education or training", "Clear responsibility", "Unclear contribution", "Impact needs clarification",
    "Writing or consistency issue", "Role relevance", "Content to clarify", "Strength to retain"]


class GroundedFinding(Finding):
    # Labels describe coaching categories, not arbitrary invented candidate facts.
    title: Label
    source_id: str = Field(min_length=1,max_length=60)


class GroundedRewrite(Rewrite):
    source_id: str = Field(min_length=1,max_length=60)


class GroundedAnalysis(CvAnalysis):
    extraction: None = None
    strengths: list[GroundedFinding] = Field(max_length=5)
    weaknesses: list[GroundedFinding] = Field(max_length=5)
    unclear_descriptions: list[GroundedFinding] = Field(max_length=5)
    content_errors: list[GroundedFinding] = Field(max_length=5)
    rewrites: list[GroundedRewrite] = Field(max_length=4)


class GroundingError(ValueError):
    def __init__(self,code):
        self.code=code
        super().__init__("Source validation failed")


def _numbers(value):return set(re.findall(r"\d+(?:[.,]\d+)*%?",value))


# Rewrites may change connective wording; new substantive words are not facts.
CONNECTIVES=set("a an the and or of for to in on with by from as at this that these those my our their your its "
    "i we it was were is are be been being have has had "
    "through while including include focused focus responsible responsibilities scope "
    "der die das ein eine und oder mit für von im in am zu bei durch als sowie wurde wurden ist sind "
    "ich wir sie er es mein meine unsere ihre".split())


def _words(value):
    return set(re.findall(r"[\w+#]+(?:[./-][\w+#]+)*",normalize_text(value,fold=True)))


def verify_source_quote(document,source_id,quote):
    block=next((b for b in document.blocks if b.source_id==source_id),None)
    if block is None:raise GroundingError("unknown_source_id")
    if normalize_text(quote,fold=True) not in normalize_text(block.original,fold=True):
        raise GroundingError("quote_not_in_cited_source")
    return block


def validate_grounding(analysis,document):
    groups=(analysis.strengths,analysis.weaknesses,analysis.unclear_descriptions,analysis.content_errors)
    accepted_rewrites=[]
    for item in [v for group in groups for v in group]+list(analysis.rewrites):
        quote=item.original if isinstance(item,Rewrite) else item.evidence
        block=verify_source_quote(document,item.source_id,quote)
        item.source_page,item.source_section=block.page,block.section
        if isinstance(item,Rewrite):
            if (not _numbers(item.suggested).issubset(_numbers(item.original)) or
                    _words(item.suggested)-_words(item.original)-CONNECTIVES):
                # Optional wording can be omitted safely; never discard valid findings
                # or persist the fabricated wording. The dashboard discloses the omission.
                if "unsupported_rewrite_omitted" not in document.warnings:
                    document.warnings.append("unsupported_rewrite_omitted")
                continue
            item.rationale="This revision retains substantive words and numbers from the cited passage. Verify it before using it."
            accepted_rewrites.append(item)
        else:
            required={"Relevant professional experience":{"experience"},"Practical project evidence":{"projects"},
                      "Education or training":{"education","training","certifications"}}
            if item.title in required and block.section not in required[item.title]:
                raise GroundingError("section_claim_mismatch")
    analysis.rewrites=accepted_rewrites
    whole=normalize_text(document.text,fold=True)
    missing=[]
    for skill in analysis.missing_skills:
        term=normalize_text(skill.skill,fold=True)
        aliases={"aws":{"aws","amazon web services"},".net":{".net","dotnet"},
            "c#":{"c#","csharp","c sharp"},"c++":{"c++","cpp"},"next.js":{"next.js","nextjs"},
            "llm":{"llm","llms","large language model","large language models"},
            "rag":{"rag","retrieval augmented generation","retrieval-augmented generation"}}
        terms=next((values for values in aliases.values() if term in values),{term})
        present=any(re.search(r"(?<!\w)"+re.escape(value)+r"(?!\w)",whole) for value in terms)
        if skill.evidence_status=="not_evidenced" and present:
            # A skill demonstrably present cannot be reported as a missing keyword.
            # Remove that observation rather than infer any proficiency deficit.
            if "skill_presence_corrected" not in document.warnings:document.warnings.append("skill_presence_corrected")
            continue
        if not present:
            if skill.evidence_status!="not_evidenced" and "skill_presence_corrected" not in document.warnings:
                document.warnings.append("skill_presence_corrected")
            skill.evidence_status="not_evidenced"
        # Never turn absence in a document into a claim about the person's knowledge.
        skill.reason=("This skill is not evidenced in the supplied text or recognized aliases. This does not establish whether you possess it."
            if not present else "The skill is mentioned in the supplied text. Its proficiency level and professional context are not independently verified.")
        missing.append(skill)
    analysis.missing_skills=missing
    return analysis
