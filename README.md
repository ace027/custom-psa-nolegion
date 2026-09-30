# Custom PSA

A small, self-hosted PSA for an MSP/MSSP. Boring on purpose: FastAPI + PostgreSQL + React, run with Docker Compose.

**Status:** Phase 1 (Foundation) complete. See [docs/PLAN.md](docs/PLAN.md) for the roadmap and design decisions, and [docs/BACKLOG.md](docs/BACKLOG.md) for ideas that are deliberately not built yet.

## What works today (Phase 1)
- Organizations, sites and contacts (soft-delete/archive, no hard deletes)
- Staff users with fixed roles: `admin`, `tech`, `billing`, `read_only`
- Sign-in with Microsoft Entra ID (OIDC), server-side sessions, admin pre-provisions users
- Audit log on every write and every auth event (append-only at the database level)
- Client-data isolation: app-layer scoping **plus** PostgreSQL row-level security
- OpenAPI docs at `/api/docs`

## Layout
```
backend/    FastAPI app, Alembic migrations, tests
frontend/   React + Vite + Tailwind
deploy/     Caddyfile, DB init, backup/restore scripts
docs/       PLAN, BACKLOG, DEVELOPMENT, ENTRA_SETUP, BACKUP_RESTORE, verify/
docker-compose.yml, .env.example
```

## Quick start (development)
See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Short version:
```sh
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload            # API on :8000
cd ../frontend && npm ci && npm run dev  # UI on :5173, dev login enabled
```

## Deploy (production)
1. Register the Entra app: [docs/ENTRA_SETUP.md](docs/ENTRA_SETUP.md)
2. `cp .env.example .env` and fill it in (never commit `.env`)
3. `docker compose up -d --build`
4. Create the first admin (one-time): see "First admin" in [docs/ENTRA_SETUP.md](docs/ENTRA_SETUP.md)
5. Set up backups **before** you put real data in: [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)

## Tests
```sh
cd backend && pytest          # needs local PostgreSQL, see docs/DEVELOPMENT.md
cd frontend && npm test       # unit tests
cd frontend && npx playwright test   # smoke test against a running dev stack
```
