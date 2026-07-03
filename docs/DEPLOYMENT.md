# Production deployment contract

This document defines the production assumptions for the Fugu backend on the `feature/modular-kernel-core` branch.

## Container startup sequence

The backend image starts through `backend/entrypoint.sh`:

1. Validate worker, port, timeout, proxy, and migration environment values.
2. Acquire a PostgreSQL advisory lock through `python -m fugu.boot.migrations`.
3. Run `alembic upgrade head` while the advisory lock is held.
4. Release the lock after Alembic succeeds or fails.
5. Start Uvicorn only after the schema reaches the current migration head.

The advisory lock serializes migrations when several replicas start at the same time. A replica exits instead of serving traffic when migration execution fails or the lock cannot be acquired within `MIGRATION_LOCK_TIMEOUT_SECONDS`.

Set `RUN_MIGRATIONS=false` only when migrations are executed by a separate, mandatory deployment job. Do not disable migrations without an equivalent pre-traffic schema gate.

## Required environment values

Inject secrets and connection strings through the deployment platform. Do not bake them into images, compose files, or repository variables visible to untrusted workflows.

Required values:

- `MASTER_ROUTER_DB_URL`
- `METADATA_SIDEBAR_DB_URL`
- `TRANSACTIONAL_LOGS_DB_URL`
- `SYSTEM_SESSION_SECRET`
- `VAULT_ENCRYPTION_KEY`
- `ALLOWED_ORIGINS`

Set `RUNTIME_ENVIRONMENT=production` in production. Production CORS origins must be exact HTTPS origins without paths, wildcards, query strings, fragments, credentials, or loopback hosts.

## CORS and browser boundary

The API permits only:

- Exact origins from `ALLOWED_ORIGINS`
- Methods `GET`, `POST`, and `OPTIONS`
- Headers `Authorization` and `Content-Type`

Credentialed browser CORS is disabled because the current Studio uses an in-memory bearer credential rather than a cross-origin cookie. Untrusted origins receive no `Access-Control-Allow-Origin` header.

The reverse proxy must preserve the browser `Origin` header. It must not inject permissive CORS headers of its own.

## Health and readiness

Use separate orchestration probes:

- Liveness: `GET /api/health/live`
- Readiness: `GET /api/health/ready`

Liveness confirms that the process and event loop respond. It does not query external dependencies.

Readiness executes bounded `SELECT 1` checks against the master, metadata, and logs connection pools. Any unavailable pool returns HTTP 503 with sanitized target states. Database exception messages are never included in the response.

The application also verifies all pools before completing startup when `VERIFY_DATABASES_ON_STARTUP=true`. A failed startup check prevents traffic from reaching the worker.

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

The proxy must:

- Terminate TLS
- Preserve streaming responses without buffering
- Disable response buffering for the SSE execution route
- Apply request-body and header-size limits
- Use a timeout longer than the maximum permitted pipeline execution time
- Route traffic only to replicas whose readiness probe succeeds

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

## Rolling deployment sequence

A safe rollout is:

1. Build and scan the immutable image.
2. Inject production configuration and secrets.
3. Start the first replacement replica.
4. Allow the entrypoint to serialize and apply migrations.
5. Wait for `/api/health/ready` to return 200.
6. Add the replica to the load balancer.
7. Drain and terminate an old replica within the configured grace period.
8. Repeat until the rollout completes.

Database migrations must remain backward-compatible for the duration of a rolling deployment. Destructive column removal should use an expand-and-contract sequence across separate releases.

## Branch and deployment policy

CI reports objective validation through `Infrastructure Continuous Integration Gate / Required CI Gate`. Branch protection and deployment approval remain repository or environment policy. Production deployment should require the final CI gate, an immutable image digest, and environment approval.
