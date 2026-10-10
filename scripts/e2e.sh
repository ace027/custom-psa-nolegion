#!/usr/bin/env bash
# Run Playwright specs against a throwaway stack: its own database, API and Vite dev server on free ports.
# Usage: scripts/e2e.sh [playwright args or specs...]     e.g. scripts/e2e.sh e2e/dispatch.spec.ts
# Optional env: E2E_PSQL (superuser psql command), CHROMIUM_PATH (browser binary).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="psa_e2e_$$"
LOGS="$(mktemp -d "${TMPDIR:-/tmp}/psa-e2e.XXXXXX")"
API_PID=""
WEB_PID=""
RESULT=1

if [ -n "${E2E_PSQL:-}" ]; then
  PSQL=($E2E_PSQL)
elif [ "$(id -u)" = "0" ]; then
  PSQL=(runuser -u postgres -- psql)
else
  PSQL=(sudo -u postgres psql)
fi
psql_admin() { "${PSQL[@]}" -v ON_ERROR_STOP=1 -q "$@"; }

stop_group() { # kill a whole process group started with setsid
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT
  stop_group "$API_PID"
  stop_group "$WEB_PID"
  psql_admin -d postgres -c "DROP DATABASE IF EXISTS $DB WITH (FORCE)" >/dev/null 2>&1 \
    || echo "e2e: could not drop database $DB" >&2
  if [ "$RESULT" -ne 0 ]; then
    echo "e2e: failed (exit $RESULT). Logs: $LOGS/api.log $LOGS/web.log $LOGS/setup.log" >&2
  else
    rm -rf "$LOGS"
  fi
}
trap cleanup EXIT
trap 'RESULT=130; exit 130' INT TERM

# Roles, as in .github/workflows/ci.yml and backend/tests/conftest.py.
psql_admin -d postgres >"$LOGS/setup.log" 2>&1 <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'psa_owner') THEN
    CREATE ROLE psa_owner LOGIN PASSWORD 'owner_dev' CREATEDB BYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'psa_app') THEN
    CREATE ROLE psa_app LOGIN PASSWORD 'app_dev' NOSUPERUSER NOCREATEDB NOBYPASSRLS;
  END IF;
END $$;
SQL
psql_admin -d postgres -c "CREATE DATABASE $DB OWNER psa_owner" >>"$LOGS/setup.log" 2>&1

# Settings for the API process only.
api_env() {
  DATABASE_URL="postgresql+psycopg://psa_app:app_dev@localhost:5432/$DB" \
  MIGRATION_DATABASE_URL="postgresql+psycopg://psa_owner:owner_dev@localhost:5432/$DB" \
  DEV_LOGIN_ENABLED=true ENVIRONMENT=development "$@"
}
(cd "$ROOT/backend" && api_env alembic upgrade head && api_env python -m app.seed) >>"$LOGS/setup.log" 2>&1 \
  || { echo "e2e: migration or seed failed" >&2; cat "$LOGS/setup.log" >&2; exit 1; }

free_port() { python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'; }
API_PORT="$(free_port)"
WEB_PORT="$(free_port)"
while [ "$WEB_PORT" = "$API_PORT" ]; do WEB_PORT="$(free_port)"; done

( cd "$ROOT/backend" && export DATABASE_URL="postgresql+psycopg://psa_app:app_dev@localhost:5432/$DB" \
    MIGRATION_DATABASE_URL="postgresql+psycopg://psa_owner:owner_dev@localhost:5432/$DB" \
    DEV_LOGIN_ENABLED=true ENVIRONMENT=development && exec setsid uvicorn app.main:app --port "$API_PORT" ) >"$LOGS/api.log" 2>&1 &
API_PID=$!
( cd "$ROOT/frontend" && export E2E_API_PORT="$API_PORT" && exec setsid ./node_modules/.bin/vite --port "$WEB_PORT" --strictPort ) >"$LOGS/web.log" 2>&1 &
WEB_PID=$!

wait_for() { # url, name
  for _ in $(seq 1 120); do
    curl -fsS -o /dev/null "$1" 2>/dev/null && return 0
    sleep 0.5
  done
  echo "e2e: $2 did not come up within 60s ($1)" >&2
  return 1
}
wait_for "http://localhost:$API_PORT/healthz" "API" || exit 1
wait_for "http://localhost:$WEB_PORT/" "Vite" || exit 1

# CHROMIUM_PATH passes through. When unset and this Playwright's own browser build is missing,
# fall back to the chromium link under PLAYWRIGHT_BROWSERS_PATH (preinstalled images can lag a version).
if [ -z "${CHROMIUM_PATH:-}" ]; then
  BUNDLED=$(cd "$ROOT/frontend" && node -e "console.log(require('@playwright/test').chromium.executablePath())" 2>/dev/null || true)
  FALLBACK="${PLAYWRIGHT_BROWSERS_PATH:-}/chromium"
  if [ ! -x "$BUNDLED" ] && [ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ] && [ -x "$FALLBACK" ]; then
    export CHROMIUM_PATH="$FALLBACK"
    echo "e2e: Playwright's browser is not installed; using $CHROMIUM_PATH"
  fi
fi
set +e
( cd "$ROOT/frontend" && E2E_BASE_URL="http://localhost:$WEB_PORT" npx playwright test "$@" )
RESULT=$?
set -e
exit "$RESULT"
