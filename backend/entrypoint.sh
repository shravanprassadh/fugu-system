#!/usr/bin/env bash
set -euo pipefail

WEB_WORKERS_COUNT="${WEB_WORKERS_COUNT:-${WEB_CONCURRENCY:-2}}"
SERVER_BIND_HOST="${SERVER_BIND_HOST:-0.0.0.0}"
SERVER_BIND_PORT="${SERVER_BIND_PORT:-${PORT:-8000}}"
SERVER_KEEP_ALIVE_SECONDS="${SERVER_KEEP_ALIVE_SECONDS:-5}"
SERVER_GRACEFUL_SHUTDOWN_SECONDS="${SERVER_GRACEFUL_SHUTDOWN_SECONDS:-30}"
SERVER_LOG_LEVEL="${SERVER_LOG_LEVEL:-info}"
TRUST_PROXY_HEADERS="${TRUST_PROXY_HEADERS:-false}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"

require_positive_integer() {
  local variable_name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    printf 'ERROR: %s must be a positive integer.\n' "$variable_name" >&2
    exit 64
  fi
}

require_boolean() {
  local variable_name="$1"
  local value="$2"
  if [[ "$value" != "true" && "$value" != "false" ]]; then
    printf 'ERROR: %s must be true or false.\n' "$variable_name" >&2
    exit 64
  fi
}

require_positive_integer "WEB_WORKERS_COUNT" "$WEB_WORKERS_COUNT"
require_positive_integer "SERVER_BIND_PORT" "$SERVER_BIND_PORT"
require_positive_integer "SERVER_KEEP_ALIVE_SECONDS" "$SERVER_KEEP_ALIVE_SECONDS"
require_positive_integer \
  "SERVER_GRACEFUL_SHUTDOWN_SECONDS" \
  "$SERVER_GRACEFUL_SHUTDOWN_SECONDS"
require_boolean "TRUST_PROXY_HEADERS" "$TRUST_PROXY_HEADERS"
require_boolean "RUN_MIGRATIONS" "$RUN_MIGRATIONS"

if [[ "$RUN_MIGRATIONS" == "true" ]]; then
  printf 'INFO: Applying serialized Alembic migrations before server startup.\n'
  python -m fugu.boot.migrations
  printf 'INFO: Database schema is at the current Alembic head.\n'
fi

uvicorn_arguments=(
  fugu.main:app
  --host "$SERVER_BIND_HOST"
  --port "$SERVER_BIND_PORT"
  --workers "$WEB_WORKERS_COUNT"
  --timeout-keep-alive "$SERVER_KEEP_ALIVE_SECONDS"
  --timeout-graceful-shutdown "$SERVER_GRACEFUL_SHUTDOWN_SECONDS"
  --log-level "$SERVER_LOG_LEVEL"
  --no-server-header
)

if [[ "$TRUST_PROXY_HEADERS" == "true" ]]; then
  uvicorn_arguments+=(
    --proxy-headers
    --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
  )
else
  uvicorn_arguments+=(--no-proxy-headers)
fi

printf 'INFO: Starting Fugu with %s worker(s) on %s:%s.\n' \
  "$WEB_WORKERS_COUNT" \
  "$SERVER_BIND_HOST" \
  "$SERVER_BIND_PORT"

exec python -m uvicorn "${uvicorn_arguments[@]}"
