# AI Career Coach

Responsive Next.js frontend for the existing FastAPI / NVIDIA Nemotron interview service. The backend is unchanged.

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

The browser calls Next.js `POST /api/interview/start`, which forwards the validated request to FastAPI. All questions come from the real backend. Seven preset roles, a custom role, and three difficulty levels are supported, alongside loading, retry, restart, and error states.

The proxy times out after 70 seconds, and the browser after 80 seconds. The route requests a 90-second deployment duration; ensure your hosting plan supports it. The unchanged backend NVIDIA client has a 60-second timeout and may retry independently.

Answer submission, evaluation, and CV analysis are explicitly Coming Soon. CV selection supports PDF files up to 10 MB with drag/drop, filename display, and removal. Files stay in the browser and are never uploaded. Feedback categories describe future functionality without fabricated results.

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

Manual integration check: start both apps, choose a role and difficulty, then click Start Interview. Confirm a question appears with the selected settings. Generate another question and restart. Stop FastAPI and retry to check the unavailable error. Select and remove a PDF on CV Reviewer; analysis should remain disabled. Check navigation and mobile layouts.

## Deploy frontend on Vercel

1. Import the repository as a new Vercel project.
2. Select `frontend` as the **Root Directory**, with the Next.js framework preset and default install/build commands.
3. Set server-side `BACKEND_API_URL` to the deployed backend's HTTPS origin, without the endpoint suffix, for Production and any Preview environments that need it.
4. Deploy or redeploy after environment changes.

The backend can be a separate project in the same repository, rooted at `backend`; backend hosting configuration remains a separate step. Configure `NVIDIA_API_KEY` only in that project's server environment. Confirm the backend host supports its Python dependencies and LLM request duration.

`127.0.0.1` on Vercel refers to the frontend server, so production requires a publicly reachable backend URL. Browser CORS changes are unnecessary because Next.js calls FastAPI server to server. No deployment or GitHub push is performed by this implementation.
