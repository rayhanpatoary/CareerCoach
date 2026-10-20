# AI Career Coach

Next.js and FastAPI career coach with NVIDIA Nemotron mock interviews and
Supabase PostgreSQL persistence. See the [architecture](docs/mock-interview-architecture.md)
and [Supabase setup, migrations, testing and deployment guide](docs/mock-interview-operations.md).

## Run locally — Windows PowerShell

Requirements: Node.js 24 LTS, npm, and your existing Python environment with `fastapi`, `uvicorn`, `python-dotenv`, and `openai` installed.

In a terminal at the repository root:

```powershell
cd backend
# Activate your Python environment first, if applicable.
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

In a second terminal at the repository root:

```powershell
cd frontend
npm ci
# Only if .env.local does not already exist:
Copy-Item .env.example .env.local
npm run dev
```

Open [localhost:3000](http://localhost:3000). Navigation connects Home, Mock Interview (`/interview`), and CV Reviewer (`/cv-review`).

## Environment variables

Set `BACKEND_API_URL=http://127.0.0.1:8001` in `frontend/.env.local`. Restart Next.js after changing it. This server-only variable must not use the `NEXT_PUBLIC_` prefix. The committed `.env.example` contains safe local configuration.

Keep `NVIDIA_API_KEY` only in `backend/.env` locally, or in the backend hosting environment. Never copy it into frontend configuration. Environment files, dependencies, and generated outputs are ignored by Git.

## Functionality and architecture

- `frontend/app/`: pages, layout, styles, and `api/interview/start/route.ts`
- `frontend/components/layout/`: reusable navigation and footer
- `frontend/components/interview/`: interview setup and question workspace
- `frontend/components/cv/`: local PDF selection and planned feedback categories
- `frontend/lib/`: typed API client and runtime request/response validation
- `frontend/types/`: shared request and response types

The browser calls a same-origin Next.js proxy. Supabase credentials and the NVIDIA
key remain backend-only. Configure Supabase and apply Alembic migrations before
using the complete persistent interview workspace. It supports eight preset
roles, custom roles, three experience levels, technical/behavioral/mixed formats,
3/5/8 questions, optional job descriptions, contextual follow-ups and saved results.

The proxy times out after 70 seconds, and the browser after 80 seconds. Routes
retain the existing 90-second deployment duration. Persistent generation uses
two bounded NVIDIA attempts with 25-second request timeouts; the legacy generator
retains its existing behavior. Verify actual hosting duration limits before rollout.

Answer submission, early finish and structured feedback are implemented in the
interview flow. The results dashboard shows evidence, deterministic weighted
scores, per-answer reviews and a practice plan. CV analysis remains Coming Soon;
its existing local PDF selection is preserved. No fake AI evaluation is used.

## Validation

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
npm run start
```

Production builds work with the backend offline. GitHub Actions runs lint, type checks, and builds on pushes and pull requests using `npm ci`.

Dependency audit at implementation time reported five high-severity findings in the development-only ESLint → fast-glob → micromatch → braces chain. npm's proposed fix downgrades the Next.js ESLint configuration to version 14 and was not applied. Review upstream updates before deployment; these packages are not part of the production runtime.

Automated backend tests mock all NVIDIA traffic; Playwright tests the complete
interview and recovery flow on desktop/mobile. GitHub Actions also provides a
disposable PostgreSQL service for migrations and concurrency tests. Run
`npm run test:e2e` after `npx playwright install chromium`. See the operations
guide for bounded checks and required live-preview validation. No local mocked
test establishes production Supabase/NVIDIA behavior.

## Deploy frontend on Vercel

1. Import the repository as a new Vercel project.
2. Select `frontend` as the **Root Directory**, with the Next.js framework preset and default install/build commands.
3. Set server-side `BACKEND_API_URL` to the deployed backend's HTTPS origin, without the endpoint suffix, for Production and any Preview environments that need it.
4. Deploy or redeploy after environment changes.

The backend can be a separate project in the same repository, rooted at `backend`; backend hosting configuration remains a separate step. Configure `NVIDIA_API_KEY` only in that project's server environment. Confirm the backend host supports its Python dependencies and LLM request duration.

`127.0.0.1` on Vercel refers to the frontend server, so production requires a publicly reachable backend URL. Browser CORS changes are unnecessary because Next.js calls FastAPI server to server. No deployment or GitHub push is performed by this implementation.
