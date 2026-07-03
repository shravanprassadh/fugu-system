# Render backend deployment

The Fugu backend must start from the packaged application entry point `fugu.main:app`. The removed legacy command `uvicorn main:app` is invalid and will fail with `Could not import module "main"`.

## Existing Render web service

Configure the service with these settings:

- Runtime: Python
- Root Directory: `backend`
- Build Command:

```bash
python -m pip install --upgrade "pip==26.1.1" && python -m pip install --requirement requirements-runtime.txt && python -m pip install --no-deps .
```

- Start Command:

```bash
bash ./entrypoint.sh
```

- Health Check Path: `/api/health/live`
- Python version environment variable: `PYTHON_VERSION=3.11.11`

The entrypoint reads Render's injected `PORT` and `WEB_CONCURRENCY` values, applies serialized Alembic migrations, and starts `fugu.main:app`.

## Required environment variables

Set these as secret or private environment values in Render:

- `MASTER_ROUTER_DB_URL`
- `METADATA_SIDEBAR_DB_URL`
- `TRANSACTIONAL_LOGS_DB_URL`
- `SYSTEM_SESSION_SECRET`
- `VAULT_ENCRYPTION_KEY`
- `ALLOWED_ORIGINS`

Also set:

```text
RUNTIME_ENVIRONMENT=production
WEB_WORKERS_COUNT=1
RUN_MIGRATIONS=true
VERIFY_DATABASES_ON_STARTUP=true
```

Production `ALLOWED_ORIGINS` must contain the exact HTTPS frontend origin, without a path or wildcard.

## Blueprint deployment

The repository-root `render.yaml` contains the same service contract. A newly created Render Blueprint can use it directly. Existing manually configured services must still update their dashboard settings to match the values above.

## First administrator

After the deployment succeeds and migrations complete, open the Render Shell for the backend service and run:

```bash
fugu-create-user --username admin --role admin
```

Enter the password twice when prompted. Do not place the password in Render environment variables or GitHub.
