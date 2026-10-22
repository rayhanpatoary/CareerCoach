# Job-Fit Analysis and Skills Gap Assessment

## Architecture and scope

`/job-fit` accepts a fresh PDF or pasted CV, job title, optional company, and a
required English/German posting. `/job-fit/results/[id]` shows source-backed
matches, transferable evidence, gaps, category contributions, actions and a
prioritized roadmap. The mock-interview action pre-fills the existing setup with
job criteria only; it never starts an interview automatically or replaces an
active/pending interview. The home page, navigation and CV Reviewer link here.

Existing CV feedback cannot reconstruct a resume. Raw CV retention has not been
enabled. Re-upload/paste is required. No authentication, provider, paid service,
chart library or dependency was added.

Backend modules under `backend/job_fit/` separate contracts, JD source clauses,
NVIDIA instructions, evidence gates, deterministic scoring, persistence and HTTP
routing. The implementation reuses `cv.extraction`, `cv.document`,
`cv.grounding.verify_source_quote`, the shared NVIDIA transport, private owner
credential, engine and rate buckets. `CvRepository` is parameterized with table
and response types so CV and job-fit share the same transaction/lease/ownership
implementation, with separate rows and rate namespaces. The Next.js CV and
job-fit routes share a bounded same-origin server proxy.

Changed files:

| Area | Files |
|---|---|
| New backend package | `backend/job_fit/{__init__,schemas,job_description,prompts,grounding,scoring,service,tables,repository,routes,maintenance}.py` |
| Shared backend integration | `backend/main.py`, `backend/cv/{grounding,repository}.py`, `backend/interviews/llm.py`, `backend/migrations/env.py` |
| Additive migration | `backend/migrations/versions/0003_job_fit.py` |
| New pages | `frontend/app/job-fit/page.tsx`, `frontend/app/job-fit/results/[id]/page.tsx`, `frontend/app/job-fit.css` |
| New UI | `frontend/components/job-fit/{workspace,resume-input,results}.tsx` |
| Contracts/client/proxy | `frontend/types/job-fit.ts`, `frontend/lib/{job-fit,analysis-proxy}.ts`, `frontend/app/api/job-fit/{[...segments],session}/route.ts` |
| Existing frontend integration | `frontend/app/{layout,page}.tsx`, `frontend/app/api/cv/[...segments]/route.ts`, `frontend/components/{layout/navbar,cv/workspace,interview/workspace}.tsx` |
| Tests and live diagnostic | `backend/tests/test_job_fit.py`, `backend/tests/test_job_fit_postgres.py`, `frontend/tests/job-fit.spec.ts`, `tools/check_job_fit_live.py` |
| Documentation | `JOB_FIT.md`, `README.md` |

The pre-existing local deletion of `PDF_RELIABILITY.md` is preserved. Existing
dependencies, environment files, CI workflows and deployment configuration are
unchanged. Generated browser screenshots/test outputs are ignored by Git.

## API

All FastAPI routes require the existing backend-only `Authorization: Bearer`
browser credential. The browser receives only the HttpOnly session cookie from
Next.js, never a database connection string, NVIDIA key or owner hash.

| Method | FastAPI path | Purpose |
|---|---|---|
| POST | `/api/job-fit/analyze` | Create/recover an analysis with `operation_id` UUID |
| GET | `/api/job-fit/history?limit=10&cursor=UUID` | Own unexpired summaries; maximum 20 |
| GET | `/api/job-fit/{id}` | Own saved feedback/status |
| DELETE | `/api/job-fit/{id}` | Delete own application row; HTTP 204 |

Next.js exposes the same paths and an additional
`POST /api/job-fit/session`, reusing the existing interview/CV cookie. Mutation
requests must originate from the same site. Other owners and expired IDs receive
404. History responses and proxied feedback use `Cache-Control: no-store`.

Request fields:

```json
{
  "operation_id": "a new UUID, reused verbatim on retries",
  "job_role": "Backend Developer",
  "company": "Optional company",
  "job_description": "Full posting, 100–8,000 characters",
  "cv_text": "CV text, 100–30,000 characters"
}
```

Send exactly one of `cv_text` and `pdf_base64`. PDF limits remain 3 MiB,
1–10 pages and 30,000 extracted characters; JSON bodies are limited to 4,300,000
bytes. The existing isolated extraction worker, page/structure checks, bounded
concurrency and coordinate-aware column/section recovery are reused. Scans that
lack readable text need a selectable-text PDF or pasted text; no OCR service was
added. Errors contain instructions, not raw Pydantic inputs or provider output.

## Requirements, grounding and AI boundaries

The backend creates stable `jd_001` clause IDs without truncating the posting.
English/German headings and explicit required/preferred wording provide
importance hints. Mixed-importance clauses remain available for model reasoning.
Two source-separated NVIDIA stages extract atomic criteria from the posting
alone, then classify CV evidence against fixed validated requirement indices.
The matching stage cannot add CV-only skills as job requirements. It also
provides conditional actions and a short roadmap; it does not supply percentages.
The combined one-call design was rejected after synthetic provider checks showed
it invented job requirements from CV-only skills. Supported categories include technical skills,
tools, experience, education, responsibilities, domain, communication, language
and seniority. The output contract caps criteria at 16 and JD sources at 80.
Long or ambiguous postings may need a focused extract; incomplete coverage
withholds the overall score rather than presenting an inflated percentage.

Every criterion must cite an actual JD clause and excerpt; its final label must
occur in that excerpt. A generic added English action verb can be removed only
when the entire remaining phrase is copied from that exact JD excerpt; skills,
years and seniority are never translated or removed to force a match.
Required/preferred source hints are enforced. Duplicate labels,
invented sources/quotes and contradictory positive/absent evidence fail closed.
Each matched/partial item requires a verified CV quote from a single source block.
Source page and section are assigned by Python, not trusted from NVIDIA.
Normalization preserves C#/.NET, C++, Unicode and existing PDF reading order.

Direct skill/tool/language/education/seniority matches require literal support or
a small documented alias set. Related SQL Server experience can be partial
PostgreSQL evidence, never a direct PostgreSQL match. Unverified numerical scope
becomes uncertain; employment-context checks prevent projects/training from
automatically becoming professional experience. A keyword found elsewhere in the
CV cannot be presented as categorically absent. Optional rewrites use the CV
Reviewer's conservative substantive-word and number gate; unsupported new facts
are omitted. Recommendations distinguish wording, conditional truthful evidence,
learning and clarification. The UI says not evidenced is not proof of inability.

These gates verify provenance, not the truth of CV claims or all semantic
reasoning. Model classification, language detection and atomic requirement
coverage still need human review. Source-clause coverage cannot prove that every
criterion inside a long clause was extracted. Plain-text/PDF coordinates cannot
assess visual design. Advice is coaching, not a verified hiring judgment.

## Reproducible scoring: `job-fit-v1`

- Mandatory requirements: 60%; preferred qualifications: 25%; role alignment: 15%.
- Each distinct criterion has equal weight within its category.
- Matched = 1, partial = 0.5, not evidenced = 0, uncertain = 0.
- Uncertain and absent criteria stay in the denominator; they are never removed
  to improve a score. Zero describes missing document support, not lack of skill.
- A category absent from the posting has no score/weight. Remaining weights are
  divided by their sum (e.g. no preferred criteria means 80% mandatory/20% role).
- Category fraction × effective weight contributes points to the overall score.
  Python `Decimal` calculates the total; final rounding is half up to an integer.
- Overall score is withheld for fewer than three criteria, no mandatory criteria,
  incomplete posting coverage, more than 40% uncertain criteria, or low CV
  reading-order confidence. Category values are labeled provisional in this case.

Example: mandatory matched + partial = 75%; preferred absent = 0%; role matched =
100%. Overall = 0.60×75 + 0.25×0 + 0.15×100 = **60**. If the posting has no preferred
category, the same mandatory and role evidence produces **80**.

This estimates alignment between the two supplied documents. It is not hiring,
interview-selection or ATS probability, recruiter approval or objective quality.
Percentages are reproducible for the validated classifications; repeated LLM
interpretations can differ.

## Private persistence and retention

Migration `0003` (parent `0002`) only adds
`career_coach.job_fit_analyses` and two indexes. It does not alter, drop, truncate
or backfill interview/CV tables. No production migration is applied automatically.
The private schema must stay outside Supabase Data API exposed schemas. Table
permissions explicitly revoke PUBLIC, anon, authenticated and service_role.
Backend SQL credentials need appropriate private-schema privileges; no Supabase
browser SDK or privileged frontend key is needed.

Rows contain an owner SHA-256 hash, request fingerprint, job title, input type and
counts, timestamps/status/lease/fence, and structured feedback. Complete source
documents are not stored as separate fields or files; feedback retains short CV
and JD excerpts, optional company and recommendations, which remain personal and
potentially confidential data. The entire original request exists only during
processing and in the current form's memory for retries. It is cleared after
success and is not written to localStorage/sessionStorage by job-fit.

IDs are primary keys. Claims and completions use transactions, row locks and
fencing tokens. The same UUID/content returns saved feedback without another
NVIDIA call; edited content with the same UUID conflicts. A 100-second processing
lease prevents concurrent calls, supports recovery after serverless termination
and rejects late workers. Deleting during a call cannot recreate the row.
Exactly-once provider billing cannot be guaranteed across a process crash after
NVIDIA responds but before the transaction commits.

Limits per hour, per feature: 10 new analyses/20 attempts per owner, 100 new/200
attempts globally, persisted in shared rate buckets. Anonymous sessions can be
replaced, so global caps are the backstop rather than a full abuse-prevention
system. Review budgets for all AI features together before public rollout.

Rows expire after seven days and immediately become inaccessible. To physically
purge expired rows, schedule this bounded operator command daily through existing
trusted infrastructure (no paid scheduler or serverless background task added):

```powershell
cd backend
python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m job_fit.maintenance
```

Deleting a result removes the application row immediately. Database backups and
NVIDIA retention are separate provider policies; do not promise immediate backup
erasure. Obtain appropriate user consent and review provider data terms before
submitting confidential CVs. Clearing cookies loses anonymous access and cannot
restore history; do not share a browser profile for private reviews.

## Environment and safe release

No new environment variables or dependencies are required.

| Project | Variable | Value |
|---|---|---|
| Backend only | `DATABASE_URL` | Supabase transaction pooler, port 6543, SSL |
| Migration environment only | `DIRECT_DATABASE_URL` | Supabase direct or session pooler, port 5432, SSL |
| Backend only | `NVIDIA_API_KEY` | Existing NVIDIA key |
| Backend only | `NVIDIA_MODEL` | Existing configured supported model |
| Frontend server only | `BACKEND_API_URL` | Corresponding backend HTTPS origin, no `/api` suffix |

Preserve existing CORS/legacy-interview settings. Never prefix any credential or
database URL with `NEXT_PUBLIC_`. The shared Psycopg engine retains `NullPool`,
`prepare_threshold=None`, SSL, 5-second connect, 8-second statement and 3-second
lock timeouts for transaction pooling. Migrations use the separate URL.

1. Review migration SQL offline before any database change:

   ```powershell
   cd backend
   python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m alembic upgrade 0002:head --sql
   ```

2. Provision/use an isolated Supabase preview database with the existing connection
   settings. For connection strings, use Supabase project's **Connect** dialog:
   transaction pooler at 6543 for `DATABASE_URL`, session pooler at 5432 for
   `DIRECT_DATABASE_URL` if direct IPv6 is unavailable. Copy the project-specific
   host/user exactly, URL-encode the password, and require SSL. Keep URLs in
   backend `.env`/backend Vercel settings only. Never paste them into logs.
3. After explicit approval to modify the selected database, check and upgrade:

   ```powershell
   cd backend
   python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m alembic current
   python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m alembic upgrade head
   python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m alembic current
   ```

   Expect revision `0003`. Verify the new table in the **private** schema. If using
   a restricted runtime login, grant only the needed USAGE on `career_coach` and
   SELECT/INSERT/UPDATE/DELETE on this table to that existing backend role; keep
   migration ownership separate. Do not grant Data API roles. Do not reset or
   downgrade an existing database as part of rollout.
4. With user approval to push/deploy, create backend and frontend **preview**
   deployments using the existing two Vercel projects and root directories
   (`backend` and `frontend`). Set each preview's corresponding backend URL and
   backend-only secrets. Keep the existing webpack build and CI workflows.
5. Verify both functions' actual hosting duration/memory allowances. Extraction
   occurs once. Both NVIDIA stages share one 55-second deadline and at most three
   attempts total (at most two per stage), with at most 25 seconds per SDK request
   and no nested SDK retries. Next.js proxy
   timeout is 70 seconds, browser 80 seconds, route duration 90 seconds. No work
   is delegated to an unreliable in-process background task.
6. In preview, test PDF and pasted text; English/German posting; direct and
   transferable evidence; provider errors and same-ID retry; reload/history;
   another browser's denied access; deletion; expiry/cleanup; interview prefill;
   and regression of both existing features. Inspect logs for accidental PII.
7. Only after CI, preview database integration and manual acceptance pass, obtain
   production migration/deployment approval. Apply the additive migration before
   releasing the new backend/frontend. No automatic push or deployment is made.

## Validation commands

```powershell
cd backend
python ../tools/run_check.py 150 ./.venv/Scripts/python.exe -m pytest tests -q
cd ../frontend
python ../tools/run_check.py 90 npm.cmd run lint
python ../tools/run_check.py 60 npm.cmd run typecheck
python ../tools/run_check.py 180 npm.cmd run build
python ../tools/run_check.py 240 npm.cmd run test:e2e
```

Backend tests block real NVIDIA HTTP. They cover JD parsing, provenance,
transferable evidence, conservative classification, deterministic scores, missing
categories, ambiguity, invalid output repair, extraction reuse, PDF columns,
API auth/validation, retry and no raw persistence. Browser tests mock the API on
desktop/mobile, exercise the production build and cover upload, posting
validation, loading, retry IDs, evidence, scores, history/deletion, denied access,
interview prefill and existing interview preservation. Existing CV/interview
tests run unchanged.

Database tests use only `TEST_DATABASE_URL` pointing at a local database whose
name ends in `_test`; they refuse hosted databases. Existing CI supplies
PostgreSQL 17 and applies all migrations. New tests exercise real persistence,
ownership, content conflicts, concurrent claims, fencing, pagination, retention,
deletion and rate limits. If no local test database exists they are explicitly
skipped; a skipped test is not proof that hosted Supabase works.

Optional live NVIDIA check (synthetic CV only, no database writes; never CI):

```powershell
cd backend
python ../tools/run_check.py 80 ./.venv/Scripts/python.exe ../tools/check_job_fit_live.py --live
```

`--diagnostics` additionally prints only mismatching labels from this tool's
synthetic posting. Never adapt it to log user CVs. A successful synthetic contract
check does not replace representative real-data acceptance and preview testing.

## Implementation validation record

- Backend: **148 passed, none skipped**, including migrations and all existing
  interview/CV database tests against an isolated local PostgreSQL 17 container.
- Frontend: lint and TypeScript passed; webpack production build passed;
  **32 desktop/mobile browser tests passed**, including existing-feature regression.
- Desktop upload and mobile results screenshots inspected for layout/readability.
- Offline `0002:head` SQL reviewed; migration `0003` applied successfully only to
  the disposable test database. Hosted Supabase was not modified.
- Live NVIDIA with synthetic CV and mixed English/German posting: **passed**,
  four validated criteria, overall score 53, complete coverage, no validation
  warnings, no database writes. Earlier combined-prompt checks failed safely and
  motivated the source-separated design. No personal resume was sent for this task.
- Only existing HTTPX/Starlette and Alembic configuration deprecation warnings
  remain in test output; no failing checks or hung processes remain.

Ready for final local/preview acceptance after applying the approved migration
to the selected database. Production readiness still requires that preview's
actual Supabase ownership/pooling/privilege checks, Vercel limits and manual
acceptance. CI has not been run remotely because no changes were pushed.
