import base64
import binascii
import json
import re
import subprocess
import sys
from threading import BoundedSemaphore
from pathlib import Path

from fastapi import HTTPException
from .schemas import MAX_PDF_BYTES, MAX_TEXT, ReviewRequest
from .document import ResumeDocument, SourceBlock, text_document

# Bound parser memory per serverless process, even with concurrent request threads.
_PDF_SLOTS = BoundedSemaphore(1)


def validate_text(value):
    value = value.replace("\x00", "")
    value = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", value).strip()
    if not 100 <= len(value) <= MAX_TEXT:
        raise HTTPException(422, "Provide 100–30,000 characters of readable CV text. Scanned PDFs need OCR or pasted text.")
    if len(re.findall(r"[^\W\d_]", value, flags=re.UNICODE)) < 60 or value.count("\ufffd") > len(value) // 20:
        raise HTTPException(422, "The CV text is unreadable. Export a text-based PDF or paste readable text.")
    if len(re.findall(r"\(cid:\d+\)",value))>=5:
        raise HTTPException(422,"The PDF font mapping is unreadable. Export a fresh text-based PDF or paste its text.")
    return value


def extract_document(request: ReviewRequest):
    if request.cv_text is not None:
        return text_document(validate_text(request.cv_text))
    try:
        data = base64.b64decode(request.pdf_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The PDF upload is invalid. Select the file again.") from None
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "Choose a PDF no larger than 3 MiB.")
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-4096:]:
        raise HTTPException(422, "This file is not a complete PDF. Export a fresh PDF or paste its text.")
    if not _PDF_SLOTS.acquire(blocking=False):
        raise HTTPException(503,"PDF extraction is busy. Wait a moment and retry the same review.",headers={"Retry-After":"3"})
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("pdf_worker.py"))],
            input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8, check=False)
        if result.returncode != 0 or len(result.stdout) > 1_500_000:
            raise ValueError("Extraction failed")
        output = json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        raise HTTPException(422, "PDF extraction took too long. Simplify the PDF or paste its text.") from None
    except (ValueError, OSError):
        raise HTTPException(422, "This PDF could not be read safely. Paste its text instead.") from None
    finally:
        _PDF_SLOTS.release()
    if "error" in output:
        raise HTTPException(422, output["error"])
    document=ResumeDocument(**{**output,"blocks":[SourceBlock(**block) for block in output["blocks"]]})
    validate_text(document.text)
    return document


def extract(request: ReviewRequest):
    """Compatibility wrapper for callers that only need the extracted text."""
    document=extract_document(request)
    return document.text,document.source,document.page_count
