# Deployment Runbook

This runbook defines the current deployment and operating contract for Fugu System.

## Services

| Layer | Service | Notes |
| --- | --- | --- |
| Frontend | Vercel | Builds `frontend/` and requires `NEXT_PUBLIC_FUGU_API_BASE_URL` |
| Backend | Render | Runs `backend/entrypoint.sh` and starts FastAPI/Uvicorn |
| Database | Neon PostgreSQL | Used by Alembic and all runtime database pools |
| CI | GitHub Actions | Secret scan, backend validation, frontend validation, production container validation |

## Backend startup sequence

The backend starts through `backend/entrypoint.sh`:

1. Validate worker, port, timeout, proxy, and migration environment values.
2. Run serialized Alembic migrations when `RUN_MIGRATIONS=true`.
3. Acquire a PostgreSQL advisory lock through `python -m fugu.boot.migrations`.
4. Run `alembic upgrade head` while the advisory lock is held.
5. Release the lock after Alembic succeeds or fails.
6. Start Uvicorn only after the schema reaches the current migration head.

The advisory lock serializes migrations when several replicas start at the same time. A replica exits instead of serving traffic when migration execution fails or the lock cannot be acquired within `MIGRATION_LOCK_TIMEOUT_SECONDS`.

Set `RUN_MIGRATIONS=false` only when migrations are executed by a separate mandatory deployment job. Do not disable migrations without an equivalent pre-traffic schema gate.

## Render backend configuration

Required Render environment values:

```text
RUNTIME_ENVIRONMENT=production
MASTER_ROUTER_DB_URL=postgresql://...
METADATA_SIDEBAR_DB_URL=postgresql://...
TRANSACTIONAL_LOGS_DB_URL=postgresql://...
SYSTEM_SESSION_SECRET=<at-least-32-characters>
VAULT_ENCRYPTION_KEY=<fernet-key>
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
RUN_MIGRATIONS=true
VERIFY_DATABASES_ON_STARTUP=true
SERVER_BIND_HOST=0.0.0.0
SERVER_BIND_PORT=8000
TRUST_PROXY_HEADERS=false
```

Render may provide `PORT`; the entrypoint falls back to it when `SERVER_BIND_PORT` is not set.

## Database URL rules

The backend accepts these PostgreSQL schemes and normalizes them internally:

```text
postgresql://...
postgres://...
postgresql+asyncpg://...
```

For Neon SSL, `sslmode=require` is acceptable in the incoming URL. The application translates SSL options into the form needed by SQLAlchemy/asyncpg.

Do not use SQLite URLs in production. Runtime migrations are PostgreSQL-only.

## Vercel frontend configuration

Set this environment variable on Vercel:

```text
NEXT_PUBLIC_FUGU_API_BASE_URL=https://your-render-backend.onrender.com
```

Do not append `/api`. The frontend already builds API calls with `/api/...` paths.

Correct:

```text
https://your-render-backend.onrender.com
```

Incorrect:

```text
https://your-render-backend.onrender.com/api
```

After changing this variable, redeploy the frontend. Next.js public environment variables are baked into the build.

## CORS and browser boundary

Render must allow the exact Vercel origin in `ALLOWED_ORIGINS`.

Use origins only:

```text
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

Do not use:

```text
ALLOWED_ORIGINS=*
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app/api
```

Production origins must use HTTPS and cannot include paths, queries, fragments, usernames, or passwords.

The API permits only:

- Exact origins from `ALLOWED_ORIGINS`
- Methods `GET`, `POST`, and `OPTIONS`
- Headers `Authorization` and `Content-Type`

Credentialed browser CORS is disabled because the current Studio uses an in-memory bearer credential rather than a cross-origin cookie. Untrusted origins receive no `Access-Control-Allow-Origin` header.

## Health and readiness

The backend root path `/` is not defined and can return `404 Not Found`. That is not itself a failure.

Use these routes:

```text
GET /api/health/live
GET /api/health/ready
GET /api/docs
```

Expected liveness response:

```json
{"status":"alive"}
```

Readiness executes bounded checks against the master, metadata, and logs connection pools. Any unavailable pool returns HTTP 503 with sanitized target states. Database exception messages are never included in the response.

The application also verifies all pools before completing startup when `VERIFY_DATABASES_ON_STARTUP=true`. A failed startup check prevents traffic from reaching the worker.

## First admin user

The database does not contain a default user after a reset.

### Preferred path when a shell is available

Run this in the backend environment:

```bash
fugu-create-user --username admin --role admin
```

The command prompts for a password and writes an Argon2-hashed password to the `users` table.

### Render Free path without shell

Render Free does not provide a service shell. Use Neon SQL only after confirming you are connected to the same database used by `MASTER_ROUTER_DB_URL`.

Generate an Argon2id password hash outside the database using the backend security code or another trusted local environment. Then insert it with this shape:

```sql
INSERT INTO users (
    username,
    password_hash,
    role,
    is_active,
    token_version
)
VALUES (
    'admin',
    '<argon2id-password-hash>',
    'admin',
    true,
    0
)
ON CONFLICT (username)
DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    role = 'admin',
    is_active = true,
    token_version = users.token_version + 1;
```

Do not commit bootstrap passwords or password hashes to the repository.

## Disposable database reset

Only use this for prototype, staging, or disposable databases. Do not run this against production data that must be preserved.

First confirm the target database:

```sql
SELECT
  current_database() AS database_name,
  current_user AS database_user,
  current_schema() AS current_schema,
  current_setting('search_path') AS search_path;
```

Then inspect existing tables:

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND table_type = 'BASE TABLE'
ORDER BY table_schema, table_name;
```

For a clean disposable reset, drop all public tables:

```sql
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT schemaname, tablename
    FROM pg_tables
    WHERE schemaname = 'public'
  LOOP
    EXECUTE format('DROP TABLE IF EXISTS %I.%I CASCADE', r.schemaname, r.tablename);
  END LOOP;
END $$;
```

Verify no application tables remain, then trigger a Render manual deploy. Alembic should recreate the schema.

## Worker and connection-pool budget

Each Uvicorn worker owns three independent SQLAlchemy pools. The maximum theoretical PostgreSQL connections per backend replica are:

```text
WEB_WORKERS_COUNT × DB_POOL_MAX_CONNECTIONS × 3
```

For example, two workers with a maximum of ten connections per pool can consume up to sixty database connections per replica. Multiply that value by the maximum replica count and leave capacity for migrations, administration, monitoring, and failover.

Do not increase workers independently of the database connection budget. Horizontal replicas are generally preferable to a high worker count inside one container.

## Reverse proxy trust

`TRUST_PROXY_HEADERS` defaults to `false`. Enable it only when every request reaches Uvicorn through a trusted proxy.

When enabled, restrict `FORWARDED_ALLOW_IPS` to the proxy network or explicit addresses. Do not use a wildcard unless the container network itself provides a strong trust boundary.

## Graceful shutdown

`SERVER_GRACEFUL_SHUTDOWN_SECONDS` controls Uvicorn's shutdown allowance. During shutdown the application:

1. Marks itself unavailable for readiness.
2. Allows Uvicorn to drain active requests within the configured timeout.
3. Clears cached execution services.
4. Disposes all three database pools.

The deployment platform termination grace period must exceed `SERVER_GRACEFUL_SHUTDOWN_SECONDS`.

## Image and filesystem assumptions

The backend image:

- Runs as non-root UID/GID `10001:10001`
- Contains runtime dependencies only
- Does not copy tests, caches, `.env` files, or repository metadata
- Exposes port 8000
- Includes a process-level liveness health check

The root filesystem can be mounted read-only. No application path requires persistent local writes.

## Common failures

### Frontend login returns 404

The frontend is probably calling the Vercel origin instead of the Render backend.

Check Vercel:

```text
NEXT_PUBLIC_FUGU_API_BASE_URL=https://your-render-backend.onrender.com
```

Then redeploy Vercel.

### Backend root returns 404

This is expected. Use `/api/health/live`, `/api/health/ready`, or `/api/docs`.

### Alembic reports duplicate tables

The database has tables but no matching Alembic version state, or Render points to a different Neon database than the one you reset. Confirm `MASTER_ROUTER_DB_URL` and inspect `information_schema.tables` in the exact target database.

### Alembic reports multiple heads

The migration graph has diverged. The intended migration graph is linear. Do not add another migration with the same `down_revision` as an existing revision unless you also create a merge migration.

### Login returns 401

The backend route is reachable, but credentials are invalid or the user is inactive.

### Login returns 404

The frontend is calling the wrong origin/path. A bad password gives `401`, not `404`.

## CI expectations

The required GitHub Actions gate covers:

- Secret scanning
- Backend Ruff formatting/linting, mypy, pytest, dependency audit
- Frontend ESLint, Vitest, npm audit, Next.js build
- Backend production container validation

Do not merge deployment changes until the required gate is green.

## Branch and deployment policy

Production deployment should require the final CI gate, an immutable image digest, and environment approval. Stale branches should be closed rather than merged after a replacement PR has already landed on `main`.
