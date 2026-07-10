# Fugu baseline contract

Baseline date: 2026-07-10

This document records the stable starting point required before provider-control and pipeline-versioning work begins.

## Enforced repository baseline

The machine-readable contract is stored at:

```text
docs/baseline/system-contract.json
```

It records:

- FastAPI title and version
- every documented HTTP method and path
- the single Alembic head
- the complete linear migration chain
- the SQLAlchemy table set
- the three configured database pool names
- the current table-routing target

Run the local verification from `backend/`:

```bash
python scripts/verify_baseline.py
```

The backend test suite also runs this comparison. Any API, table, migration, or target change must therefore update the implementation and baseline contract deliberately in the same pull request.

## API baseline

The current API is `Fugu Modular Kernel API` version `1.0.0`.

Canonical runtime documents:

```text
/api/openapi.json
/api/docs
```

The committed operation list is in `docs/baseline/system-contract.json`. Authentication uses bearer tokens. Public endpoints are limited to login and health documentation/probes; user, thread, execution, memory, and administrative routes enforce authenticated identity or administrator role through FastAPI dependencies.

## Migration baseline

The migration graph is linear:

```text
0001_initial_schema
  -> 0002_user_token_version
  -> 0003_pipeline_step_run_identity
  -> 0004_thread_memories
```

Current head:

```text
0004_thread_memories
```

Current tables:

```text
users
provider_credentials
pipeline_steps
threads
messages
thread_memories
pipeline_runs
pipeline_step_runs
```

Alembic defaults to `MASTER_ROUTER_DB_URL`. A different database can only be targeted through the explicit Alembic `database_url` override.

## Database routing reality

Fugu requires three configured connection pools:

| Runtime target | Environment variable | Current use |
| --- | --- | --- |
| `master` | `MASTER_ROUTER_DB_URL` | System of record for all current tables and repository operations |
| `metadata` | `METADATA_SIDEBAR_DB_URL` | Configured and readiness-tested, but no application repositories currently route data here |
| `logs` | `TRANSACTIONAL_LOGS_DB_URL` | Configured and readiness-tested, but no application repositories currently route data here |

This distinction matters. The labels “metadata” and “logs” describe the intended architecture, not the current persistence implementation. Users, credentials, pipeline definitions, threads, messages, memory, pipeline runs, and step traces are currently persisted through the master session.

Do not treat the three URLs as three populated application databases. Moving tables or writes to the metadata and logs targets later is a data-routing and migration change, not a configuration-only change.

## CI baseline

Every pull request targeting `main` must pass:

- Security & Secret Auditing
- Backend Lint, Type Check, Tests & Audit
- Frontend Lint, Tests, Build & Audit
- Browser End-to-End Smoke Tests
- Production Container & Runtime Validation
- Required CI Gate

The browser smoke test runs against a production Next.js build and verifies:

```text
login
  -> protected chat
  -> thread creation
  -> message submission
  -> SSE response completion
  -> persistent memory rebuild
  -> logout
  -> protected-route rejection
```

## Production verification

The public deployment can be verified without exposing credentials:

```bash
cd backend
python scripts/verify_production.py \
  --frontend-url https://myfugu.vercel.app \
  --backend-url https://fugu-system.onrender.com
```

The command verifies:

- the Vercel frontend returns HTML over HTTPS
- Render liveness returns `alive`
- Render readiness returns `ready`
- `master`, `metadata`, and `logs` pools all report `connected`
- the deployed OpenAPI contract exactly matches the committed baseline

The verifier prints only public origins and sanitized health states.

## Dashboard-only checks

Public probes cannot prove the exact secret values configured in Vercel, Render, or Neon. An administrator must separately confirm:

1. Vercel `NEXT_PUBLIC_FUGU_API_BASE_URL` equals the intended Render origin and does not include `/api`.
2. Render contains the required production environment variables documented in `docs/DEPLOYMENT.md`.
3. The masked database hosts and database names returned by the Fugu database administration screen match the intended Neon projects/databases.
4. The stored Render service ID and token pass the Render control-plane Test action.
5. Each current database target passes its independent Test action.

Do not mark these items verified from repository configuration alone.

## Change procedure

When a deliberate API or schema change is made:

1. Change the implementation and migration.
2. Update `docs/baseline/system-contract.json` in the same branch.
3. Run `python scripts/verify_baseline.py`.
4. Run the full backend and frontend test suites.
5. Run `python scripts/verify_production.py` after deployment.
6. Record any platform-dashboard configuration change without recording secret values.
