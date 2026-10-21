# AI CV Reviewer: architecture and release guide

For the current coordinate-aware PDF pipeline, normalization, source citations,
reference-resume acceptance and updated validation results, see
[PDF_RELIABILITY.md](PDF_RELIABILITY.md). It supersedes the original extraction
and strict-substring behavior described in the initial implementation report below.

## Architecture

`/cv-review` uses the existing Next.js same-origin API proxy and anonymous
HttpOnly session cookie. FastAPI's separate `cv` module reuses the interview
SQLAlchemy engine, owner credential validation, rate buckets and validated NVIDIA
transport. No authentication provider, storage service, or new paid service is
introduced. Production analysis always uses NVIDIA; test fixtures never replace
production behavior.

PDF bytes travel as base64 JSON through Next.js to Python. A 3 MiB binary limit
leaves room under [Vercel's 4.5 MB request limit](https://vercel.com/docs/functions/limitations).
Both servers reject JSON over 4,300,000 bytes. Python validates PDF signatures,
encryption, page count and readable extracted text. `pypdf` runs in an isolated
foreground subprocess, using pipes without temporary files, an 8-second wall
timeout, bounded decompression, and (on Linux/Vercel) CPU and memory limits.
There is no shell invocation, URL fetching, OCR or executable PDF content.
Only one PDF parser runs per serverless process at a time; concurrent parsing
requests get a retryable 503 instead of multiplying the parser's memory budget.

Limits: PDF 3 MiB / 1–10 pages; extracted or pasted text 100–30,000 characters;
role 2–100 characters; optional job description at most 8,000 characters.
Encrypted, malformed, scanned/blank and overly complex PDFs receive actionable
errors. Plain-text extraction cannot assess layout, fonts, columns or graphics.

Typed contracts live in `backend/cv/schemas.py` and `frontend/types/cv.ts`.
Analysis includes strengths, weaknesses, missing/partially evidenced skills,
unclear descriptions, content errors, suggested rewrites and prioritized steps.
Findings must quote actual source text; rewrites cannot introduce new numbers.
Prompts prohibit invented employers, skills, qualifications and achievements.
AI feedback still requires human verification; no ATS or hiring score is claimed.

## Endpoints

All backend endpoints require `Authorization: Bearer <anonymous session secret>`.
The browser never handles this secret directly: Next.js obtains it from the
shared HttpOnly cookie and forwards it server to server.

| FastAPI route | Behavior |
| --- | --- |
| `POST /api/cv/reviews` | Extract, analyze, save; retries use the same `operation_id` |
| `GET /api/cv/reviews?limit=10&cursor=<uuid>` | Owner-only metadata history; maximum 20 per page |
| `GET /api/cv/reviews/{id}` | Owner-only review and feedback |
| `DELETE /api/cv/reviews/{id}` | Delete an owned, unexpired review; returns 204 |

Next.js exposes these under the same paths plus `POST /api/cv/session`, reusing
the interview session setup. Writes require a matching browser Origin. Responses
containing review data use `Cache-Control: no-store`. Foreign, missing and expired
IDs all return 404. CV contents never appear in URLs, localStorage or sessionStorage;
only the current review UUID is saved in sessionStorage to restore the dashboard.

POST accepts JSON:

```json
{
  "operation_id": "b125527f-9f98-4490-937c-c5ba50dc216f",
  "job_role": "Python Developer",
  "job_description": "Optional job requirements",
  "cv_text": "At least 100 characters of real CV text..."
}
```

Provide exactly one of `cv_text` or `pdf_base64`. For PDF input send only the
base64 bytes, without the data URL prefix. See `/docs` for full response schemas.
Reuse the same UUID and unchanged inputs after a transport failure: completed
results are cached, active work returns 409 with Retry-After, and failed work can
be retried. Edited inputs need a new UUID. Transactional row locks, a primary key,
request hashes, leases and fencing prevent duplicate saved results and stale writes.
Never hold a database transaction while waiting for NVIDIA. On rare server
termination a retry may call NVIDIA again after the 100-second lease, but only
one result can commit. Exactly-once billing cannot be guaranteed by a database lock.
Limits are 10 new reviews / 20 attempts per browser owner per hour, and 100 new
reviews / 200 attempts globally per hour. Multiple browsers can evade per-owner
limits; the global limit bounds usage. These anonymous controls are not identity.

## Sensitive data and retention

No raw PDF, filename, full extracted/pasted CV or job description is saved to
PostgreSQL. Source data remains in request memory only (including a retry payload
while the page is open). It is sent to NVIDIA to perform the analysis, so disclose
that transfer and review NVIDIA's applicable data terms before collecting real CVs.
Disable request-body/session-replay logging in any external monitoring tool.

`career_coach.cv_reviews` stores owner hash, salted request fingerprint, target role,
source type, character/page counts, timestamps, processing lease and structured
feedback. **Feedback includes CV excerpts and is itself personal information.**
The role field can also contain personal information; do not log arbitrary inputs.
There is no public share URL. Losing the browser cookie loses access; clearing it
does not itself delete saved rows. Reviews become inaccessible after 7 days.

Physical expiry cleanup must be scheduled daily by the operator (no scheduler or
paid service is silently provisioned):

```powershell
cd backend
.\.venv\Scripts\python.exe -m cv.maintenance
```

With daily execution, expired rows can remain physically present for up to one
additional day. Until a scheduler is configured, they remain inaccessible but
physically stored. Monitor the maintenance job; do not promise exact seven-day
physical deletion without it. The command deletes only expired CV rows. The
existing interview cleanup separately removes old shared rate buckets.
For Supabase-native scheduling, an operator may use the existing database Cron
capability, if available, to run only this statement daily with privileged access:

```sql
DELETE FROM career_coach.cv_reviews WHERE expires_at <= now();
```

The UI's confirmed deletion immediately removes the selected application row.
In-flight workers cannot recreate it. Historical backups and NVIDIA's retention
are separate; document the configured provider backup expiry in your privacy policy.
No deletion action removes interview records. No broad reset or TRUNCATE is used
outside guarded disposable integration tests.

## Migration and deployment

Migration `0002` adds only the private CV table and indexes; it preserves interview
tables and data. It is prepared locally and **has not been applied to the deployed
database by this implementation**. No code was pushed or deployed.

No new environment variable is required:

| Project | Variable | Configuration |
| --- | --- | --- |
| Backend | `NVIDIA_API_KEY` | Existing NVIDIA secret |
| Backend | `NVIDIA_MODEL` | Optional existing Nemotron model override |
| Backend | `DATABASE_URL` | Existing Supabase transaction pooler, port 6543, SSL required |
| Migration runner only | `DIRECT_DATABASE_URL` | Direct connection or session pooler, port 5432 |
| Frontend server | `BACKEND_API_URL` | Existing FastAPI HTTPS origin, no endpoint suffix |

Keep all secrets backend-only; never use a `NEXT_PUBLIC_` database/NVIDIA variable.
The shared engine retains Psycopg 3 `prepare_threshold=None`, SQLAlchemy NullPool,
5-second connect / 8-second statement / 3-second lock timeouts. Do not expose
`career_coach` through Supabase's Data API. Migration revokes table privileges
from PUBLIC and Supabase API roles. A dedicated backend database login needs
schema USAGE and SELECT/INSERT/UPDATE/DELETE on `cv_reviews` and `rate_buckets`.
Use the existing migration owner or explicitly grant those to the existing runtime
role; never grant them to `anon`, `authenticated` or `service_role`.

After approving the release, from the project root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

Expected head: `0002`. Alembic loads `backend/.env` locally; run from `backend`.
Use a bounded command runner if the network is unavailable:
`python ../tools/run_check.py 30 ./.venv/Scripts/python.exe -m alembic current`.
Never run downgrade/reset against deployed data. In Supabase's SQL editor verify:

```sql
SELECT to_regclass('career_coach.cv_reviews');
SELECT version_num FROM alembic_version;
```

Deploy the existing backend Vercel project first (root `backend`, existing FastAPI
preset and Python 3.12), then the existing frontend project (root `frontend`,
Next.js). Preserve the existing `next build --webpack` command. There is no need
to reintroduce Turbopack. Confirm the backend's function duration and memory allow
the bounded extraction worker and NVIDIA call; frontend route maxDuration is 90s,
upstream proxy timeout 70s and browser analysis timeout 80s. LLM transport allows
two bounded attempts within 55s, with 25s per request; CV structural errors can
use the second attempt for schema repair. PDF extraction
is foreground work, so no post-response/background execution is required.

On a preview deployment, use synthetic PDF/text CVs to test upload, persisted
history after refresh, cross-browser denial, retry, deletion and an interview
regression. Verify runtime-role privileges and expiry cleanup. A local build cannot
prove Vercel subprocess/runtime behavior; this preview check is a release gate.
Do not deploy production or push without the user's confirmation.

## Validation

```powershell
cd backend
python ../tools/run_check.py 120 ./.venv/Scripts/python.exe -m pytest tests -q
cd ../frontend
npm run lint
npm run typecheck
python ../tools/run_check.py 180 npm.cmd run build
python ../tools/run_check.py 180 npm.cmd run test:e2e
```

Backend tests block real outbound NVIDIA HTTP. PDF tests generate PDFs in memory.
Playwright mocks the API and exercises text/PDF submission, limits, loading,
dashboard, same-ID retry, restoration and deletion on desktop/mobile. Existing
interview regression tests remain intact. PostgreSQL tests use the existing CI
service; locally they require `TEST_DATABASE_URL` pointing to a **disposable local
database whose name ends in `_test`**. They refuse hosted Supabase connections
and clear test tables. Never use production credentials for tests.

An optional, explicitly live contract check uses synthetic text and no database:
`python ../tools/run_check.py 80 ./.venv/Scripts/python.exe ../tools/check_cv_live.py --live`
from `backend`. This spends NVIDIA quota and must stay out of CI.

## Implementation verification

The local backend suite passes (74 tests); 10 PostgreSQL integration tests are
skipped because a disposable local test database is not configured and Docker
Desktop's Linux engine is stopped. They remain wired into the existing CI
PostgreSQL service. Migration SQL was rendered successfully offline, without
applying it to deployed Supabase. Lint, TypeScript and the webpack production
build pass. All 18 browser tests pass (8 CV checks and 10 interview checks across
desktop/mobile). Loading assertions use controlled responses instead of fixed
delays to avoid timing-dependent failures under load. Existing CI workflow files
and deployment configurations are unchanged.

A live NVIDIA check using synthetic CV text passed the full service's response
validation, exact-source evidence checks and rewrite metric checks, returning
3 strengths and 5 practice steps without touching a database. Earlier checks
exposed and led to fixes for the shared schema helper dropping fields called
`title`, and inconsistent missing-skill keys. A regression test preserves title
properties, and CV structural repair is bounded and tested. This live check does
not verify deployed Vercel PDF execution or Supabase persistence; those remain
preview release checks after the migration is approved and applied.
