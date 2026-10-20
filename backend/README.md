# CareerCoach FastAPI backend

The backend now also supports durable mock interviews using **Supabase
PostgreSQL, SQLAlchemy, Psycopg 3 and Alembic**. Follow the
[Supabase operations guide](../docs/mock-interview-operations.md) for exact
connection strings, migration commands, schema privileges, tests, retention and
preview deployment. The legacy stateless start contract below is preserved.
Do not deploy the persistent flow before configuring storage and applying the
migration. Database credentials belong only in the backend environment.

The existing NVIDIA interview integration remains in `main.py:app`. The NVIDIA
base URL is `https://integrate.api.nvidia.com/v1` and the model is
`nvidia/nemotron-3.5-lightning-30b-a3b`. The OpenAI Python SDK is only the
compatible client for NVIDIA; requests do not go to OpenAI.

## Local development (Windows PowerShell)

Use Python 3.12, matching `.python-version` and Vercel's supported runtime.
From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env  # Only if you do not already have .env
# Edit .env and replace the placeholder NVIDIA_API_KEY with your own key.
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

If activation is restricted, use `.\.venv\Scripts\python.exe` directly in place
of `python`. Do not overwrite an existing `.env`. The app loads `backend/.env`
without overriding existing environment variables. Importing `main` starts no
server and requires no API key; generating a question requires a key.

Open Postman: POST `http://127.0.0.1:8001/api/interview/start`, choose Body → raw →
JSON, and send:

```json
{"job_role":"Python Developer","difficulty":"beginner"}
```

Expect HTTP 200 and `job_role`, `difficulty`, `question`. The question comes from
NVIDIA. Difficulty defaults to beginner; supported values are beginner,
intermediate, advanced. The role must have 2–100 characters.

For automated tests (no real NVIDIA calls or key required):

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Vercel dashboard setup and redeployment

1. Open the backend Vercel project connected to the CareerCoach GitHub repository
   (or import that repository as a separate backend project).
2. In Settings → Build and Deployment, set Root Directory to `backend`.
3. Use the **FastAPI** Framework Preset. Automatic detection uses the FastAPI
   dependency in `requirements.txt`. If the old project says Other or Next.js,
   change it to FastAPI.
4. Leave Install Command, Build Command, and Output Directory overrides disabled.
   Vercel installs `requirements.txt`; no static build, `uvicorn` start command,
   output directory, `app.py` wrapper, or legacy rewrite configuration is needed.
5. Python is pinned to 3.12 by `.python-version`.
6. Under Settings → Environment Variables, add `NVIDIA_API_KEY` to Production
   and to Preview if you will test previews. Never prefix it with NEXT_PUBLIC_.
   A physical `.env` file is unnecessary in production.
7. Optional: set `CORS_ORIGINS` to comma-separated exact browser origins, such as
   `http://localhost:3000,https://your-frontend.vercel.app`, with no trailing slash.
   The existing Next.js server proxy does not require CORS. Wildcards are not needed.
8. Ensure the function duration allowed by your plan/settings exceeds the backend's
   60-second upstream timeout with overhead. SDK retries are disabled to avoid
   extending requests beyond the frontend proxy's existing 70-second timeout.
9. Once you approve committing and pushing these files, push to the connected
   production branch. This triggers a new deployment. For settings/secret changes,
   use Deployments → latest deployment → Redeploy. A redeploy of an old commit
   cannot include local code changes. If detection appears stale, redeploy with
   the build cache disabled.
10. Confirm Settings → Domains associates `careercoach-backend.vercel.app` with
    this backend project and its current Production deployment.

Keep the frontend as another Vercel project with Root Directory `frontend` and
Framework Preset Next.js. Set its server-only `BACKEND_API_URL` to
`https://careercoach-backend.vercel.app` (no `/api` suffix), then redeploy that
project. Its existing proxy appends `/api/interview/start`. No frontend code
change is required, and the NVIDIA key belongs only in the backend project.

Official references:
[FastAPI entrypoints](https://vercel.com/docs/frameworks/backend/fastapi),
[Python runtime and dependencies](https://vercel.com/docs/functions/runtimes/python).
`main.py` is a supported entrypoint, so the project needs no `vercel.json`.

## Production checks

Use `https://careercoach-backend.vercel.app` as the base URL:

| Request | Expected result |
| --- | --- |
| GET `/` | 200 with the existing running message |
| GET `/health` | 200 with `{"status":"ok"}` |
| GET `/docs` | 200 with interactive Swagger docs |
| POST `/api/interview/start` | 200 with a real NVIDIA question when configured |

Use the same Postman JSON above for the POST, or Swagger's Try it out. These
production checks must be performed after deployment; local mocked tests do not
prove live NVIDIA access. Health is a process check, not an NVIDIA readiness test.
Sending GET to the POST endpoint should return 405, not a platform 404.

## Troubleshooting

- **Vercel 404 NOT_FOUND:** verify Root Directory `backend`, FastAPI preset,
  dependency installation, deployed commit, and domain assignment. A platform
  404 usually means routing/discovery rather than NVIDIA failure. A FastAPI JSON
  `{"detail":"Not Found"}` instead means the app was reached with an unknown path.
  Use `/api/interview/start`, never `/api/api/interview/start`.
- **500 or function invocation failure:** inspect the deployment's Build Logs for
  install/import errors, then the project's Logs view filtered to the deployment
  for runtime failures. Verify Python 3.12 and required dependencies.
- **503, AI service is not configured:** add a nonempty `NVIDIA_API_KEY` in the
  correct Vercel environment and redeploy. Public routes remain usable without it.
- **502:** NVIDIA connection, authentication, rate-limit, upstream status, or empty
  response problem. Check NVIDIA key validity, model access and service availability.
  Client responses intentionally omit upstream details and secrets.
- **504 or Vercel timeout:** NVIDIA exceeded the SDK timeout or Vercel's function
  duration is too short. Check runtime logs and function duration. A Vercel-enforced
  termination may occur before the application can return its JSON error.
- **422:** invalid JSON fields; check role length and difficulty.
- **Browser CORS issue:** configure the exact frontend origin only if calling the
  backend directly from the browser. Server-to-server proxy calls need no CORS.

## Secrets and Git

Root `.gitignore` excludes `.env` variants (except `.env.example`), virtual
environments, Python bytecode, pytest artifacts, and Vercel generated files.
The local `.env` is not tracked in the current Git index. However, a historical
root `.env` contains an NVIDIA key-like value. Treat that historical key as exposed
and revoke/rotate it at NVIDIA if you have not already done so. Its value was not
printed during this review. Git history was left unchanged. Never log or commit the
key. If a secret is currently tracked, remove the
file from tracking (`git rm --cached backend/.env`), and coordinate history cleanup
if necessary. Ignoring a file does not remove it from prior commits.
