# Real-world resume PDF extraction and grounded feedback

## Diagnosis

The old path passed `pypdf.page.extract_text()` content-stream order directly to
NVIDIA. Its evidence gate then compared a quote against the entire CV using only
NFKC, case folding and whitespace collapse. It did not reconstruct columns or
unwrap split words. Consequently `Ger-\nmany` did not match `Germany`, even though
the quote was legitimate. It also had no source IDs to distinguish separate
sections or an actual fabricated quote from a normalization mismatch.

`test_wrapped_source_quote_regression` was written and run **before** changing the
implementation; it failed on this exact mismatch. The privately supplied reference
also reproduces the issue: eight source blocks contain verifiable short quotes
that the old comparison rejects. This establishes real false-negative paths.
The original failed NVIDIA response was not retained, so its individual rejected
quote cannot be retrospectively identified. Genuine model paraphrases or invented
evidence remain possible causes; the fix does not assume every rejected quote was
valid or disable evidence validation.

## Smallest architecture change

The public upload/review/history/delete routes and database layout are unchanged.
The pipeline now adds an in-memory document representation:

1. Existing size/signature/encryption/decompression preflight using pypdf.
2. Coordinate extraction with `pdfminer.six`, inside the existing bounded child.
3. Dynamic whitespace cuts into reading regions, preserving spanning headings.
4. Same-region line reconstruction and connected-grid table row reconstruction.
5. Section blocks containing original text, normalized text, page, bounding box,
   original line geometry and stable per-request source IDs.
6. Source-ID-grounded NVIDIA feedback, deterministic citation verification and
   narrowly scoped safe corrections.
7. Save only validated feedback, citation identifiers and small diagnostic metadata
   through the existing owner-authorized repository.

There are no template coordinates or personal-resume text in the implementation.
Reading regions use observed text geometry, font-relative gap thresholds and
recursive whitespace cuts, supporting one, two and reasonably separated three
columns. Full-width headings divide horizontal bands before column ordering.
Justified word fragments are reunited only after region separation. Date-only
columns stay associated with employer rows. Explicit connected table grids retain
same-row cell associations. Ambiguous whitespace cells remain separate, lose
unproven section associations and produce a low-confidence warning. Extractable
source-character accounting rejects accidental loss or duplication.

Section aliases cover common English/German headings and duration suffixes.
Combined project/training headings remain combined; unknown sections remain
unknown. The representation preserves ordered section/entry spans rather than
guessing company, job title, degree or employment fields from incomplete data.
Coordinates recover text order; they do **not** establish visual design quality.
Images are ignored, hyperlinks are not followed, and OCR is not invoked.

## Dependency and licensing

New direct dependency: `pdfminer.six==20260107`, declared MIT in the
[official package metadata](https://pypi.org/project/pdfminer.six/20260107/) and
[upstream license](https://github.com/pdfminer/pdfminer.six/blob/master/LICENSE).
Retain the supplied license notices in distributions. Its required dependencies
include charset-normalizer and cryptography; no optional image/OCR extras are
installed. The pure-Python layout layer avoids a rendering engine or new service.
`pdfplumber` was evaluated: it is also MIT and provides convenient coordinate APIs,
but direct pdfminer use supplies the geometry needed here without its additional
rendering/image dependency stack.

This pinned pdfminer release follows the removal of pickle-based CMap loading in
20251230, which addressed CVE-2025-64512; see the
[official release notes](https://github.com/pdfminer/pdfminer.six/releases).
Do not substitute an old vulnerable pdfminer release. Existing pypdf remains the
PDF preflight library. Normal dependency/security updates still need review.

## Normalization and evidence

Original and normalized block representations coexist only in request memory.
NFKC expands ligatures; whitespace, common quotation marks, dash/bullet variants,
soft hyphens and zero-width spaces are normalized. Line-end word hyphenation is
unwrapped conservatively. Productive compounds such as Full-Stack and unknown
capitalized continuations retain their hyphen; common CamelCase software suffixes
support wrapped identifiers such as VisionLib. Mid-line hyphens and technical
punctuation in C#, C++, C#/.NET, .NET, Next.js, LangChain and AI/ML are preserved.
Ambiguous spelling is not repaired with fuzzy similarity or a language model.

Every new finding/rewrite must cite a backend-generated `source_id`. Quotes must
match **that block's original text** after the same safe normalization. Unknown IDs,
paraphrased quotations, cross-block splicing and section claims that turn training
into professional employment are rejected. Coaching labels are a constrained
taxonomy, preventing titles from inventing credentials or years of experience.
The summary is assembled by the backend from verified observation counts and the
selected role, rather than accepting unrestricted factual claims from the model.

Recommendations are explicitly coaching suggestions, not quotations or proof of
existing experience. Missing-skill status is derived from literal source presence
and a small general alias set: a present skill cannot be reported as an absent
keyword, and an absent skill cannot be claimed as partially present. Explanations
describe the document, never assert that its author has no knowledge of a skill.
This is not a general semantic entailment engine or independent verification of
CV truth. It intentionally accepts factual evidence as source quotations instead
of treating arbitrary paraphrased employment assertions as verified facts.

An optional rewrite with new substantive words or numbers is omitted, with a
visible dashboard notice. Its unsupported wording is never saved. This safe local
correction avoids discarding otherwise valid feedback. Bad factual citations and
malformed model output instead receive at most one corrective model attempt,
sharing the existing two-attempt / 55-second budget. CV temperature is 0.2 and
output is capped at 3,000 tokens; interview temperature/behavior are preserved.
Persistent invalid citations return an actionable 502: retry once or paste CV text
in reading order. No unverified feedback is saved.

## Privacy and serverless limits

No new environment variables, authentication, external services or database
migrations are required for this change. Existing session authorization, private
schema, transactions, idempotency, retention and deletion are preserved.
Only feedback/excerpts, citations and diagnostic counts are persisted; source
blocks, raw PDFs, complete extracted text and coordinates are not persisted.
No raw CV text, provider output, name, email or phone number is logged.
Diagnostic logs use fixed structural failure codes only.

Limits remain 3 MiB PDF, 10 pages, 30,000 extracted characters, bounded decoded
streams, one parser per process, an 8-second extraction wall timeout and Linux
CPU/memory limits. A child process provides resource isolation, not a complete OS
security sandbox. No post-response background work is required. Too many source
characters, unreadable mappings, rotated text, malformed/encrypted or scanned PDFs
receive safe errors. Highly overlapping text, complex borderless tables, unusual
fonts and arbitrary magazine layouts may still need manually ordered pasted text.
There is no extracted-text preview/editor in this release; the existing paste-text
flow is the correction path. No visual-layout or universal ATS readability claims
are made, and no CV or hiring-probability score is introduced.

Root-level manual PDF inputs and `private-test-inputs/` are ignored by Git. The
reference PDF is not tracked; all committed PDF fixtures are synthetic and generated
in memory. The manual checker prints only structural counts and booleans:

```powershell
python tools/run_check.py 25 backend/.venv/Scripts/python.exe tools/check_cv_pdf.py "<local-resume.pdf>"
```

## Verification and acceptance

Local reference result: one page, 2,675 normalized characters, 14 source blocks,
medium reading-order confidence and no extraction warnings. The two body columns
are separate; spanning header bands account for additional reading regions.
Experience/sidebar bounding boxes are disjoint. Summary, experience, education,
skills, languages, projects/training and publication sections are recognized.
All source blocks verify against their originals; source-character coverage is
complete. Twelve legacy hyphenated wraps were found. C#, C++, .NET, Angular,
Python, Unity, WPF, LLM and RAG remain identifiable. No personal content appears
in the report or automated fixtures.

Live NVIDIA acceptance with a **synthetic** CV and German/English Full Stack
Developer job description passed, returning two strengths and four practice steps
through the real source validator without database writes. Earlier live attempts
identified optional rewrite and skill-status inconsistencies; these now receive
the safe local treatment described above. One earlier provider generation timed
out; a bounded model-list check confirmed connectivity/model availability before
retrying with the shorter output contract.

The actual reference PDF was used only for local extraction/verification. It was
not uploaded to NVIDIA or written to Supabase. Actual-person AI feedback and its
live history/deletion acceptance remain pending explicit upload authorization and
a preview verification; do not claim those checks have run.

Automated backend coverage includes single/two/three columns, sidebars, bordered
tables and employer/date rows, ten pages, mixed German/English, actual PDF ligature
mapping, hyphen wraps, technical punctuation, bullets, images, links, scans,
malformed/encrypted PDFs, wrong source IDs, fabricated quotes, wrong-section
claims, unsafe rewrites, skills/aliases and bounded correction. CI mocks NVIDIA.
The existing guarded local-only PostgreSQL suite now includes the full PDF →
grounded feedback → read/retry/delete workflow. Hosted Supabase is never used by
the destructive disposable test fixtures.

Validation: 98 backend tests pass; 11 PostgreSQL tests skip locally because no
disposable local test database is configured (existing CI supplies PostgreSQL).
All 18 desktop/mobile browser tests pass, including citation and confidence
display, existing history/deletion and interview regressions. TypeScript, ESLint
and the webpack production build pass. An initial 60-second lint timeout was
investigated: diagnostic logs showed slow file reads, with rule processing itself
fast. The isolated bounded run passed. Existing CI workflow files are unchanged.

## Files and release steps

New modules: `backend/cv/document.py`, `layout.py`, `grounding.py`;
new synthetic tests: `backend/tests/test_cv_documents.py`;
new local-only diagnostic tool: `tools/check_cv_pdf.py`.
Modified: CV extraction/worker/schemas/service; shared NVIDIA transport; backend
requirements and CV tests; frontend CV workspace/client/types/browser tests;
synthetic live checker, ignore rules and documentation. No interview endpoint,
Vercel project layout or CI workflow is replaced.

After release approval:

1. Install backend requirements using Python 3.12:
   `backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt`.
2. Run bounded backend tests; run frontend lint, typecheck, build and Playwright.
3. Deploy the existing backend project to a Vercel preview, then the frontend
   preview, using the existing environment variables and webpack build command.
4. Check synthetic PDFs, citations, persisted history, safe retry and deletion on
   preview; confirm subprocess execution and duration/memory limits there. Check
   an interview regression. Use the personal PDF with NVIDIA only if authorized.
5. Promote/deploy production only after confirmation.

No additional Alembic migration is introduced; the existing CV migration 0002 is
still the prerequisite if it has not already been applied in the chosen environment.
Normalization changes request fingerprints. Refresh old open tabs and reselect
the CV to start a fresh operation if retrying a pre-update failed request returns
a content-conflict 409. Existing saved reviews remain readable; deployment never
automatically regenerates or deletes them.
Retain backend-only `DATABASE_URL`, `DIRECT_DATABASE_URL`, `NVIDIA_API_KEY` and
optional `NVIDIA_MODEL`; retain frontend-server-only `BACKEND_API_URL`. Never use
`NEXT_PUBLIC_` for these secrets. Keep the existing expiry maintenance schedule.
No GitHub push, preview deployment or production deployment was performed here.
