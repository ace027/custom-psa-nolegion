# Custom PSA

A small, self-hosted PSA for an MSP/MSSP. Boring on purpose: FastAPI + PostgreSQL + React, run with Docker Compose.

**Status:** Phases 1-3 (Foundation, Ticketing, Contracts & invoicing) complete: the MVP. See [docs/PLAN.md](docs/PLAN.md) for the roadmap and design decisions, and [docs/BACKLOG.md](docs/BACKLOG.md) for ideas that are deliberately not built yet.

## What works today
**Statements and payment reminders**
- Reminders (default 1/15/30/60 days past due) and monthly client statements are *prepared* automatically and *approved by a person* before anything is emailed; invoice or statement PDFs attach; replies become tickets
- Per-client "do not remind", blocked when no billing/primary contact email, stale notices must be refreshed, sent records are immutable

**Payment tracking**
- Record payments (partial, split across invoices, unapplied credit), write-offs with a reason, paid/partial/overdue status, and a receivables aging report by client
- Balances are derived; payments, applications and write-offs are never edited (void with a reason), enforced by the database

**Phase 3: contracts and invoicing**
- Recurring agreements (per user, per device, flat fee), product catalog, hourly rates (per work type, with per-client overrides), one-off product charges
- Draft invoices from billable time, products and agreements; a **monthly billing run with a review step**, then all-or-nothing finalize with gap-free numbering
- Finalized invoices are immutable (enforced by the database); void and reissue for corrections; invoice PDFs
- Money is integer cents with documented per-line rounding: read [docs/BILLING.md](docs/BILLING.md)

**Phase 2: ticketing**
- Tickets with status, priority, queue, category, assignee and business-hours SLA clocks (pause while waiting on customer)
- Internal vs customer-visible notes; time entries that round billable time up to your increment
- Email-to-ticket and email replies through Microsoft Graph (one shared mailbox, scoped by Exchange RBAC), threaded by ticket number and headers, with triage for unknown senders
- Dashboard: my tickets, unassigned, SLA at risk; admin settings for queues, categories, priorities, work types, business hours

**Phase 1: foundation**
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
docs/       PLAN, BACKLOG, BILLING, DEVELOPMENT, ENTRA_SETUP, MAIL_SETUP, BACKUP_RESTORE, verify/
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
4a. Optional, for email-to-ticket: [docs/MAIL_SETUP.md](docs/MAIL_SETUP.md) (the `worker` container idles until configured)
5. Set up backups **before** you put real data in: [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)

## Tests
```sh
cd backend && pytest          # needs local PostgreSQL, see docs/DEVELOPMENT.md
cd frontend && npm test       # unit tests
cd frontend && npx playwright test   # smoke test against a running dev stack
```
