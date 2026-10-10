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

Vendor integrations need `CREDENTIALS_KEY` in `backend/.env` before you can save NinjaOne/Hudu credentials (generate one with the command in [INTEGRATIONS.md](INTEGRATIONS.md)). The tests set their own key and use fake vendors.

### Tests
`pytest` runs against a real PostgreSQL database `psa_test` (never SQLite: RLS must be exercised).
Override with `PSA_TEST_DB_HOST/PORT/NAME`. The suite drops and recreates the `public` schema of that
database, so never point it at anything you care about.

The suite also enforces API hygiene: every route must have a summary, tag and permission
(`tests/test_zz_api_contract.py`), and every route must be called by at least one test.

## Trying the mail worker locally (no Microsoft tenant)
`backend/dev/fake_graph.py` is a tiny in-memory stand-in for the Graph mail endpoints:
```sh
python dev/fake_graph.py &                      # http://localhost:9911
export GRAPH_BASE_URL=http://localhost:9911/v1.0 GRAPH_LOGIN_URL=http://localhost:9911 \
       GRAPH_TENANT_ID=t GRAPH_CLIENT_ID=c GRAPH_CLIENT_SECRET=s MAIL_MAILBOX=support@msp.example.com
curl -X POST localhost:9911/_inject -d '{"from":"dana@contoso-dental.example.com","subject":"Scanner broken","body":"Help"}'
python -m app.worker --once                      # ingest it; run again after emailing a note to send it
curl localhost:9911/_sent                        # what the PSA "sent"
```
The automated tests use an in-memory fake client instead (`tests/mailfakes.py`) plus `httpx.MockTransport`
tests of the real Graph client, so `pytest` needs none of this.

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
With the API and `npm run dev` running and a **freshly seeded** database (the billing spec starts and finalizes the current month's run, which can only happen once per month; reset with `alembic downgrade base && alembic upgrade head && python -m app.seed`):
`cd frontend && npx playwright test` (set `CHROMIUM_PATH` if the bundled browser is not installed).

### Isolated e2e run
`scripts/e2e.sh [playwright args...]` runs Playwright against a throwaway stack, so it needs no running servers and no fresh seed:
- a new database `psa_e2e_<pid>` (roles `psa_owner` / `psa_app` are created if missing), migrated and seeded, and dropped on exit;
- the API (`DEV_LOGIN_ENABLED=true`) and the Vite dev server on free ports, with Vite proxying `/api` to that API (`E2E_API_PORT`);
- both processes are stopped on exit, even on failure or Ctrl-C. Logs are kept in a temp dir whose path is printed on failure.

```sh
service postgresql start                                  # if Postgres is not running
scripts/e2e.sh e2e/dispatch.spec.ts                        # one spec
scripts/e2e.sh e2e/dispatch.spec.ts --repeat-each=3        # any Playwright flag works
```
It runs as a Postgres superuser through `runuser -u postgres -- psql` (as root) or `sudo -u postgres psql`; set `E2E_PSQL` to override that command. Set `CHROMIUM_PATH` if the bundled browser is not installed.

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
