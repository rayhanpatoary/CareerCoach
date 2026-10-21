"""Bounded foreground extraction child. Input/output are pipes, never files."""
import io
import json
import logging
import sys
from pathlib import Path
from dataclasses import asdict


def main():
    if sys.platform != "win32":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    from pypdf import PdfReader
    from pypdf import filters
    # Bound decompression before extract_text, not after allocating a huge stream.
    filters.ZLIB_MAX_OUTPUT_LENGTH = 8 * 1024 * 1024
    logging.getLogger("pypdf").disabled = True
    data = sys.stdin.buffer.read(3 * 1024 * 1024 + 1)
    reader = PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        return {"error":"Password-protected PDFs are not supported. Upload an unlocked copy or paste the text."}
    pages = len(reader.pages)
    if not 1 <= pages <= 10:
        return {"error":"Choose a CV with 1–10 pages."}
    for page in reader.pages:
        if page.get("/Annots") and len(page["/Annots"]) > 100:
            return {"error":"This PDF is too complex. Paste the CV text instead."}
        content = page.get_contents()
        if content is not None and len(content.get_data()) > 2 * 1024 * 1024:
            return {"error":"This PDF is too complex. Paste the CV text instead."}
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from cv.layout import extract_layout
    document=extract_layout(data)
    if "rotated_text_not_supported" in document.warnings:
        return {"error":"This PDF contains rotated text that cannot be read reliably. Paste its text in reading order instead."}
    return asdict(document)


if __name__ == "__main__":
    try:
        result = main()
    except Exception:
        result = {"error":"This PDF is malformed or unreadable. Export a fresh PDF or paste its text."}
    sys.stdout.write(json.dumps(result))
