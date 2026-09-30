# Development setup

## PostgreSQL (local, no Docker needed)
Two roles matter. Create them once (as a Postgres superuser):
```sql
-- Owner: runs migrations, pg_dump, restore. BYPASSRLS is required, see "RLS and backups" below.
CREATE ROLE psa_owner LOGIN PASSWORD 'owner_dev' CREATEDB BYPASSRLS;
-- Runtime role used by the API. NOT owner, no BYPASSRLS => row-level security applies to it.
CREATE ROLE psa_app LOGIN PASSWORD 'app_dev' NOSUPERUSER NOCREATEDB NOBYPASSRLS;
CREATE DATABASE psa OWNER psa_owner;
CREATE DATABASE psa_test OWNER psa_owner;
```
(In docker-compose the image's `POSTGRES_USER` is a superuser, so this happens automatically.)

## Backend
```sh
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head          # as psa_owner (MIGRATION_DATABASE_URL)
python -m app.seed            # demo data: 4 users (one per role), 3 orgs
uvicorn app.main:app --reload
```
Interactive API docs: http://localhost:8000/api/docs

Lint/format: `ruff check app tests && ruff format app tests`

### Tests
`pytest` runs against a real PostgreSQL database `psa_test` (never SQLite: RLS must be exercised).
Override with `PSA_TEST_DB_HOST/PORT/NAME`. The suite drops and recreates the `public` schema of that
database, so never point it at anything you care about.

The suite also enforces API hygiene: every route must have a summary, tag and permission
(`tests/test_zz_api_contract.py`), and every route must be called by at least one test.

## Frontend
```sh
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to :8000
npm test           # vitest
npm run build      # typecheck + production build
```
In development mode the login page shows a "Dev login" form (API needs `DEV_LOGIN_ENABLED=true`,
and is refused when `ENVIRONMENT=production`). Sign in as `admin@example.com`, `tech@example.com`,
`billing@example.com` or `readonly@example.com` after seeding.

### Browser smoke test
With the API and `npm run dev` running and seed data loaded:
`cd frontend && npx playwright test` (set `CHROMIUM_PATH` if the bundled browser is not installed).

## Conventions
- Schema changes = new Alembic migration in `backend/alembic/versions/`. Never edit an applied one.
- Every route: `ctx: Ctx = require(P.SOME_PERMISSION)`. Add new permissions in `app/permissions.py`.
- Every write goes through `app/services.py` and calls `audit.record(...)`.
- Every query for client-owned data goes through `app/repositories.py` with a `Scope`.
- New client-owned table => `organization_id` column, RLS policy, and an isolation test.

## RLS and backups
The three client-owned tables use `FORCE ROW LEVEL SECURITY`, which applies even to the table owner.
Consequence: `pg_dump` as a role WITHOUT `BYPASSRLS` **fails** (good: loud, not a silent partial
backup). Never "fix" that with `pg_dump --enable-row-security`; that produces an incomplete dump.
The owner role is only used by operators/migrations, never by the API.

## Docker inside the Claude Code cloud sandbox (for testing the Compose stack)
The sandbox has Docker installed but the daemon is not running, and outbound TLS goes through an
intercepting proxy. To exercise `docker compose`:
1. Start the daemon: `nohup dockerd > /tmp/dockerd.log 2>&1 &` then `docker run --rm hello-world`.
2. Build base images that trust the proxy CA (`/root/.ccr/ca-bundle.crt`): a tiny Dockerfile that
   `FROM python:3.12-slim` / `node:22-slim`, copies the CA and sets `PIP_CERT` / `SSL_CERT_FILE` /
   `NODE_EXTRA_CA_CERTS` / `npm_config_cafile`.
3. Use an untracked override that passes them through the Dockerfiles' `PYTHON_IMAGE` / `NODE_IMAGE`
   build args, and set `HTTP_PORT=8080` in `.env`:
   `docker compose -f docker-compose.yml -f docker-compose.sandbox.yml up -d --build`
This is only needed in that sandbox; on your own VM plain `docker compose up -d --build` is enough.
