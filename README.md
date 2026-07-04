# Fugu System

Fugu System is a modular full-stack prototype for orchestrating authenticated execution flows over a PostgreSQL-backed FastAPI service and a Next.js frontend.

## Current status

The active deployment path is:

- **Backend:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL/Neon, Render
- **Frontend:** Next.js, Vercel
- **Authentication:** username/password login with short-lived bearer tokens
- **Migrations:** serialized Alembic startup migration runner using a PostgreSQL advisory lock
- **CI:** GitHub Actions gate for secret scanning, backend validation, frontend validation, and production container validation

The stale migration-startup PR #18 was closed unmerged. The active fix was merged through PR #19.

## Repository layout

```text
.
├── backend/                 # FastAPI backend, database models, migrations, tests
├── frontend/                # Next.js frontend
├── docs/                    # Deployment and operating notes
├── .github/workflows/       # CI gate
└── .env.example             # Shared environment variable template
```

## Backend API entry points

The backend intentionally does not expose a root `/` route. A plain browser request to the Render root can return `404 Not Found` even when the API is healthy.

Use these routes instead:

```text
GET  /api/health/live
GET  /api/health/ready
GET  /api/docs
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
```

## Required deployment configuration

The backend requires three PostgreSQL URLs, CORS origins, and two secrets. See `.env.example` and `docs/DEPLOYMENT.md` for the full list.

Important production rules:

- Database URLs may be supplied as `postgresql://`, `postgres://`, or `postgresql+asyncpg://`; the backend normalizes them to the asyncpg SQLAlchemy form.
- Render migrations use `MASTER_ROUTER_DB_URL`.
- `ALLOWED_ORIGINS` must contain exact frontend origins only. Do not include paths or wildcards.
- `NEXT_PUBLIC_FUGU_API_BASE_URL` belongs to the Vercel frontend build and must be the Render backend origin only, without `/api`.

Correct frontend API base example:

```text
NEXT_PUBLIC_FUGU_API_BASE_URL=https://your-render-backend.onrender.com
```

Incorrect example:

```text
NEXT_PUBLIC_FUGU_API_BASE_URL=https://your-render-backend.onrender.com/api
```

## First admin user

There is no default user after a fresh database reset.

Preferred path when a shell is available:

```bash
fugu-create-user --username admin --role admin
```

Render Free does not provide a service shell. For that case, use the controlled Neon SQL bootstrap process documented in `docs/DEPLOYMENT.md`.

## Local validation

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
python -m ruff format --check src tests
python -m ruff check --fix src tests
python -m mypy src
python -m pytest
python -m pip_audit --requirement requirements.txt --strict
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm exec vitest -- run
npm audit --audit-level=high
npm run build
```

## Deployment docs

- `docs/DEPLOYMENT.md` — Render, Vercel, Neon, migrations, admin bootstrap, and operational checks
