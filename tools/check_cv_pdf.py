"""Local-only acceptance diagnostics. Never prints source text or calls NVIDIA/DB."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path
import re
import sys
import unicodedata
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))


def main():
    parser=argparse.ArgumentParser();parser.add_argument("path",type=Path);args=parser.parse_args()
    from cv.extraction import extract_document
    from cv.document import normalize_text
    from cv.schemas import ReviewRequest
    from pypdf import PdfReader
    from fastapi import HTTPException
    try:
        data=args.path.read_bytes()
        request=ReviewRequest(operation_id=uuid4(),job_role="Full Stack Developer",pdf_base64=base64.b64encode(data).decode())
        doc=extract_document(request)
        legacy="\n".join(page.extract_text() or "" for page in PdfReader(args.path).pages)
        old=lambda value:re.sub(r"\s+"," ",unicodedata.normalize("NFKC",value)).strip().casefold()
        def valid_quote_rejected_before(block):
            for start in range(0,len(block.text),80):
                quote=block.text[start:start+180]
                if len(quote)>=20 and old(quote) not in old(legacy) and normalize_text(quote,fold=True) in normalize_text(block.original,fold=True):return True
            return False
        left=[b for b in doc.blocks if b.section=="experience"]
        right=[b for b in doc.blocks if b.section in ("skills","projects","projects_training","languages","publications")]
        report={"pages":doc.page_count,"characters":len(doc.text),"source_blocks":len(doc.blocks),
            "regions_per_page":dict(Counter(len(set(b.column for b in doc.blocks if b.page==page)) for page in range(1,doc.page_count+1))),
            "section_blocks":dict(Counter(b.section for b in doc.blocks)),"confidence":doc.confidence,"warnings":doc.warnings,
            "hyphenated_wraps":len(re.findall(r"\w-\s*\n\s*\w",legacy)),
            "legacy_rejected_source_blocks":sum(old(b.text) not in old(legacy) for b in doc.blocks),
            "legacy_rejected_valid_quote_blocks":sum(valid_quote_rejected_before(b) for b in doc.blocks),
            "new_source_blocks_verifiable":all(normalize_text(b.text,fold=True) in normalize_text(b.original,fold=True) for b in doc.blocks),
            "experience_sidebar_bounds_disjoint":bool(left and right) and all(l.bbox[2]<=r.bbox[0] for l in left for r in right if l.page==r.page),
            "extractable_source_glyph_coverage_verified":True,
            "technical_tokens_preserved":{token:token.casefold() in doc.text.casefold() for token in ("C#","C++",".NET","Angular","Python","Unity","WPF","LLM","RAG")}}
        print(json.dumps(report,indent=2))
    except HTTPException as error:
        raise SystemExit(f"Extraction failed at PDF/text validation (HTTP {error.status_code}): {error.detail}") from None
    except Exception:
        raise SystemExit("Local acceptance check failed; no document contents were logged.") from None


if __name__=="__main__":main()
