# Codebase Map

**Analyzed:** 2026-10-09
**Generated At:** 2026-10-09T00:59:20Z
**Map Schema Version:** 2.0
**Analyzed Commit:** a4dbbf3
**Source File Count:** 237
**Source Fingerprint:** 071000694970ef22
**Scope:** project-root
**Root:** /home/user/custom-psa-nolegion
**Confidence:** MEDIUM: architecture, commands and conventions come from manifests and docs actually read; coverage gaps and module paths beyond those come from the code-computed facts and were not individually verified.

```yaml
map_schema_version: "2.0"
generated_at: "2026-10-09T00:59:20Z"
analyzed_commit: a4dbbf3
source_file_count: 237
source_fingerprint: "071000694970ef22"
source_fingerprint_kind: content
scope: project-root
```

## Architecture Overview
- Monorepo: FastAPI + PostgreSQL + React/Vite, run via Docker Compose (README.md).
- Backend: `backend/app/main.py` builds the app and mounts routers from `backend/app/routers/` under `/api`. OpenAPI at `/api/docs`.
- Layering: routers -> `backend/app/services.py` (business rules, audit on every write) -> `backend/app/repositories.py` (all queries, `Scope`-filtered).
- Security: staff sessions via Entra OIDC; every non-public route needs a permission dependency; PostgreSQL RLS (`FORCE ROW LEVEL SECURITY`) on client-owned tables. The API runs as `psa_app` (no BYPASSRLS); `psa_owner` is for migrations and backups only (docs/DEVELOPMENT.md).
- Middleware in main.py: unsafe methods require `X-Requested-With: psa` (CSRF defense); responses set `Cache-Control: no-store`.
- Frontend: `frontend/src/App.tsx` splits three shells: public `/csat`, client portal `/portal*`, and the staff app behind `useMe()`. Routes are gated by `can(me, "<perm>")`.
- Worker container (`python -m app.worker`) polls the mailbox via Microsoft Graph and sends queued email.
- Proxy: Caddy serves the static frontend and proxies `/api` (`deploy/Caddyfile`).

## Language Distribution
| Extension | File Count | % of Codebase |
|-----------|------------|---------------|
| .py | 164 | 69% |
| .tsx | 60 | 25% |
| .ts | 13 | 5% |

## Detected Stack
| Layer | Technology | Evidence |
|-------|------------|----------|
| Language | Python | 164 .py files |
| Framework | fastapi | import or requirement |
| Testing | pytest | test_*.py / pytest reference |

## Conventions Detected
- **File naming**: snake_case
- **Module structure**: Monorepo
- **Config location**: .env files, *.config files
- **Test approach**: separate test directories (75 test files)
- **Import style**: relative
- **Linting/formatting**: none detected

## Entry Points
| Type | Path | Evidence |
|------|------|----------|
| Python | `backend/app/main.py` | main.py |

## Functionality Inventory
| Feature | Entry | Key files |
|---|---|---|
| Auth / sessions (Entra OIDC, dev login) | routers/auth.py | backend/app/main.py, docs/ENTRA_SETUP.md |
| Orgs, sites, contacts | routers/organizations.py | backend/app/services.py, backend/app/repositories.py |
| Users and roles | routers/users.py | backend/app/permissions.py |
| Ticketing, SLA, notes, time | routers/tickets.py, ticket_config.py, ticket_links.py | frontend/src/pages/TicketDetail.tsx, docs/TICKETS_PLAN.md |
| Billing runs, invoices, credit memos, late fees, payments | routers/billing.py, invoices.py, credit_memos.py, late_fees.py, payments.py | backend/app/billing.py, backend/app/models.py, docs/BILLING.md, frontend/src/pages/billing/ |
| Notices and reminders (Graph mail) | routers/notices.py | backend/app/notices.py, docs/MAIL_SETUP.md |
| Quoting and surveys | routers/quotes.py | frontend/src/pages/quotes/, docs/QUOTING.md |
| Integrations and assets | routers/integrations.py, assets.py | docs/INTEGRATIONS.md |
| Timesheets and expenses | routers/timekeeping.py, expenses.py | frontend/src/pages/Timesheet.tsx, Expenses.tsx, TimerBar.tsx |
| Client portal | routers/portal.py | frontend/src/portal/, docs/PORTAL.md |
| CSAT | routers/csat.py | frontend/src/portal/CsatPage.tsx |
| Reports, audit, search, holidays | routers/reports.py, search.py, holidays.py | frontend/src/pages/Audit.tsx, Search.tsx |

## Module Ownership
| Module | Responsibility | Suggested agent |
|---|---|---|
| backend/app/billing.py, schemas.py money paths | Billing math, invoices, payments | engineering-senior-developer |
| backend/app/services.py, repositories.py, permissions.py | Business rules, scoping, RBAC | engineering-backend-architect |
| backend/alembic/versions/ | Migrations 0001-0022 | engineering-backend-architect |
| backend/app/notices.py, worker | Mail, Graph, reminders | engineering-backend-architect |
| backend/app/auth/, main.py middleware | Sessions, CSRF, OIDC | engineering-security-engineer |
| backend/tests/ | Pytest suite | testing-api-tester |
| frontend/src/api.ts, ui.tsx, auth.tsx, money.ts | Shared client code (high fan-in) | engineering-frontend-developer |
| frontend/src/pages/quotes/, TicketDetail.tsx, TicketTable.tsx, TimerBar.tsx | UI with weak or no tests | engineering-frontend-developer |
| deploy/, docker-compose.yml | Compose, Caddy, backup/restore | engineering-infrastructure-devops |
| docs/*.md | Plans and setup guides | product-technical-writer |

## Risk Areas
- Migrations 0001-0022 are applied in production. Editing one breaks deployed databases; schema changes need a new revision.
- `FORCE RLS` means `pg_dump` as a non-BYPASSRLS role fails. Do not use `--enable-row-security` (partial dump) (docs/DEVELOPMENT.md).
- Test suite drops and recreates `public` on `psa_test`. Never point it at real data.
- `CREDENTIALS_KEY` defaults to empty in docker-compose.yml, so vendor credentials cannot be saved until set.
- Untested: frontend/src/pages/quotes/QuotesList.tsx (CRITICAL); TicketDetail.tsx, TicketTable.tsx, TimerBar.tsx, lookups.ts (HIGH). No frontend linter.
- High fan-in: frontend/src/api.ts (43), ui.tsx (40), auth.tsx (26), money.ts (21). Largest: backend/app/schemas.py, models.py, billing.py, notices.py.
- Billing Playwright spec finalizes the current month's run; needs a freshly seeded DB on rerun.
- Dev login gated by `DEV_LOGIN_ENABLED`, refused when `ENVIRONMENT=production`.

## Technical Debt Signals
**TODO/FIXME/HACK/XXX density**: 0 per source file — LOW

_None detected_

### Complexity (largest files)
| File | Lines | Level |
|------|-------|-------|
| `backend/app/schemas.py` | 1634 | HIGH |
| `backend/app/models.py` | 1242 | HIGH |
| `backend/app/billing.py` | 999 | HIGH |
| `frontend/src/api.ts` | 905 | HIGH |
| `backend/app/notices.py` | 899 | HIGH |

### Git Hotspots (90 days)
_Skipped: fewer than 10 commits in 90 days, or not a git repository._

### Hygiene
_None detected_

## Dependency Risk
No package manifest detected (package.json, requirements.txt, Gemfile, Cargo.toml, go.mod). Dependency risk analysis requires a recognized package ecosystem.

## Agent Guidance
- Every route uses `ctx: Ctx = require(P.SOME_PERMISSION)`; add permissions in `backend/app/permissions.py`; every write goes through `services.py` with `audit.record(...)`; client-owned queries go through `repositories.py` with a `Scope`; a new client-owned table needs `organization_id`, an RLS policy and an isolation test.
- Backend tests go in `backend/tests/` (pytest, real PostgreSQL, never SQLite). `test_zz_api_contract.py` requires every route to have a summary, tag, permission and at least one test call.
- Frontend unit tests: vitest (`npm test`); e2e: Playwright in `frontend/e2e`.
- Do not touch: applied Alembic revisions; RLS policies without an owner decision. Per CLAUDE.md, money/billing math, auth, quoting rules and security review stay with the main model.

## Dependency Graph
**Files analyzed**: 237 | **Internal edges**: 203 | **External deps**: 54

### Fan-out (most imports)
| File | Imports |
|------|---------|
| `frontend/src/App.tsx` | 37 |
| `frontend/src/pages/OrgBillingCard.tsx` | 6 |
| `frontend/src/pages/OrganizationDetail.tsx` | 5 |
| `frontend/src/pages/TicketDetail.tsx` | 5 |
| `frontend/src/pages/Tickets.tsx` | 5 |

### Fan-in (most imported)
| File | Imported by |
|------|-------------|
| `frontend/src/api.ts` | 43 |
| `frontend/src/ui.tsx` | 40 |
| `frontend/src/auth.tsx` | 26 |
| `frontend/src/money.ts` | 21 |
| `frontend/src/App.tsx` | 17 |

### Key Dependency Chains
- frontend/src/App.tsx → frontend/src/api.ts → frontend/src/auth.tsx
- frontend/src/pages/OrgBillingCard.tsx → frontend/src/api.ts → frontend/src/auth.tsx
- frontend/src/pages/OrganizationDetail.tsx → frontend/src/api.ts → frontend/src/auth.tsx

## Test Coverage Map
**Test convention**: tests/ or test/ directory
**Coverage**: 10% of sampled source files have a matching test — LOW
**Source**: file-name matching (no coverage report read)

### Critical Untested Files
| File | Lines | Fan-in | Risk Score | Risk Level |
|------|-------|--------|------------|------------|
| `frontend/src/pages/quotes/QuotesList.tsx` | 124 | 3 | 31.2 | CRITICAL |
| `frontend/src/pages/TicketDetail.tsx` | 453 | 2 | 24.5 | HIGH |
| `frontend/src/pages/TicketTable.tsx` | 87 | 2 | 20.9 | HIGH |
| `frontend/src/pages/TimerBar.tsx` | 48 | 2 | 20.5 | HIGH |
| `frontend/src/lookups.ts` | 27 | 2 | 20.3 | HIGH |

## API Surface
**Framework**: fastapi | **Routes detected**: 436 | **Resources**: 62

| Method | Path | File |
|--------|------|------|
| GET | `/organizations/{org_id}/assets` | `backend/app/routers/assets.py` |
| GET | `/assets/{asset_id}` | `backend/app/routers/assets.py` |
| PUT | `/assets/{asset_id}/overrides/{field}` | `backend/app/routers/assets.py` |
| DELETE | `/assets/{asset_id}/overrides/{field}` | `backend/app/routers/assets.py` |
| PUT | `/organizations/{org_id}/assets-sharing` | `backend/app/routers/assets.py` |
| GET | `/reports/warranty` | `backend/app/routers/assets.py` |
| GET | `/reports/warranty.csv` | `backend/app/routers/assets.py` |
| GET | `/organizations/{org_id}/assets` | `backend/app/routers/assets.py` |
| GET | `/assets/{asset_id}` | `backend/app/routers/assets.py` |
| PUT | `/assets/{asset_id}/overrides/{field}` | `backend/app/routers/assets.py` |
| DELETE | `/assets/{asset_id}/overrides/{field}` | `backend/app/routers/assets.py` |
| PUT | `/organizations/{org_id}/assets-sharing` | `backend/app/routers/assets.py` |
| GET | `/reports/warranty` | `backend/app/routers/assets.py` |
| GET | `/reports/warranty.csv` | `backend/app/routers/assets.py` |
| GET | `/login` | `backend/app/routers/auth.py` |
| GET | `/callback` | `backend/app/routers/auth.py` |
| POST | `/dev-login` | `backend/app/routers/auth.py` |
| POST | `/logout` | `backend/app/routers/auth.py` |
| GET | `/me` | `backend/app/routers/auth.py` |
| PATCH | `/me/notifications` | `backend/app/routers/auth.py` |
| GET | `/login` | `backend/app/routers/auth.py` |
| GET | `/callback` | `backend/app/routers/auth.py` |
| POST | `/dev-login` | `backend/app/routers/auth.py` |
| POST | `/logout` | `backend/app/routers/auth.py` |
| GET | `/me` | `backend/app/routers/auth.py` |
| PATCH | `/me/notifications` | `backend/app/routers/auth.py` |
| GET | `/billing/work-types` | `backend/app/routers/billing.py` |
| PATCH | `/billing/work-types/{work_type_id}` | `backend/app/routers/billing.py` |
| GET | `/organizations/{org_id}/billing` | `backend/app/routers/billing.py` |
| PATCH | `/organizations/{org_id}/billing` | `backend/app/routers/billing.py` |
| PUT | `/organizations/{org_id}/billing/rates/{work_type_id}` | `backend/app/routers/billing.py` |
| DELETE | `/organizations/{org_id}/billing/rates/{work_type_id}` | `backend/app/routers/billing.py` |
| GET | `/products` | `backend/app/routers/billing.py` |
| POST | `/products` | `backend/app/routers/billing.py` |
| PATCH | `/products/{product_id}` | `backend/app/routers/billing.py` |
| POST | `/products/{product_id}/archive` | `backend/app/routers/billing.py` |
| POST | `/products/{product_id}/unarchive` | `backend/app/routers/billing.py` |
| GET | `/agreements` | `backend/app/routers/billing.py` |
| POST | `/agreements` | `backend/app/routers/billing.py` |
| GET | `/agreements/{agreement_id}` | `backend/app/routers/billing.py` |

## Config & Environment
**Config files**: 9 detected | **Env variables**: 23 referenced | **Sensitive vars**: 6

### Config Files
| File |
|------|
| `.env.example` |
| `.github/workflows/ci.yml` |
| `backend/.env.example` |
| `backend/Dockerfile` |
| `docker-compose.yml` |
| `frontend/Dockerfile` |
| `frontend/playwright.config.ts` |
| `frontend/tsconfig.json` |
| `frontend/vite.config.ts` |

### Environment Variables
| Variable | Source | Sensitive |
|----------|--------|-----------|
| APP_DB_PASSWORD | `.env.example` | yes |
| CHROMIUM_PATH | `frontend/playwright.config.ts` | no |
| CREDENTIALS_KEY | `backend/tests/conftest.py` | yes |
| DATABASE_URL | `backend/tests/conftest.py` | no |
| DEV_LOGIN_ENABLED | `backend/tests/conftest.py` | no |
| E2E_BASE_URL | `frontend/playwright.config.ts` | no |
| ENTRA_CLIENT_ID | `backend/tests/conftest.py` | no |
| ENTRA_CLIENT_SECRET | `backend/tests/conftest.py` | yes |
| ENTRA_TENANT_ID | `backend/tests/conftest.py` | no |
| ENVIRONMENT | `backend/tests/conftest.py` | no |
| FAKE_GRAPH_HOST | `backend/dev/fake_graph.py` | no |
| GRAPH_CLIENT_ID | `.env.example` | no |
| GRAPH_CLIENT_SECRET | `.env.example` | yes |
| GRAPH_TENANT_ID | `.env.example` | no |
| MAIL_MAILBOX | `.env.example` | no |
| MIGRATION_DATABASE_URL | `backend/tests/conftest.py` | no |
| OWNER_DB_PASSWORD | `.env.example` | yes |
| PSA_TEST_DB_HOST | `backend/tests/conftest.py` | no |
| PSA_TEST_DB_NAME | `backend/tests/conftest.py` | no |
| PSA_TEST_DB_PORT | `backend/tests/conftest.py` | no |
| PUBLIC_URL | `.env.example` | no |
| SESSION_SECRET | `backend/tests/conftest.py` | yes |
| SITE_ADDRESS | `.env.example` | no |

### Secret Exposure Warnings
_None detected_

## Setup / Runbook
- Backend: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`.
- DB: `alembic upgrade head && python -m app.seed`; API: `uvicorn app.main:app --reload` (:8000).
- Lint: `ruff check app tests && ruff format app tests`.
- Tests: `cd backend && pytest` (needs local PostgreSQL `psa_test`).
- Frontend: `cd frontend && npm ci && npm run dev` (:5173); `npm test`, `npm run build`, `npx playwright test`.
- Compose: `cp .env.example .env` then `docker compose up -d --build`. Required vars: OWNER_DB_PASSWORD, APP_DB_PASSWORD, PUBLIC_URL, SESSION_SECRET, ENTRA_*. Keep values in `.env`.

## Pattern Library
1. Permission-guarded route: routers mounted in `backend/app/main.py` with `prefix="/api"`, guarded by `require(P.*)`.
2. Audited write: `backend/app/services.py` `create_organization` adds, flushes, then `audit.record(...)` in one transaction.
3. Scoped query: `backend/app/repositories.py` `list_organizations` uses `scope.apply(stmt, Organization.id)`.
4. Integrity to 409: `backend/app/services.py` `_flush` maps `IntegrityError` to `Conflict` (HTTP 409 in main.py).
5. Role-gated frontend routes: `frontend/src/App.tsx` `can(me, "billing:read") && <Route ...>`.
6. Contract test: `backend/tests/test_zz_api_contract.py` iterates `app.routes`.

## Monorepo Structure
| Package | Path |
|---------|------|
| backend | `backend` |
| frontend | `frontend` |

## Directory Mappings
| Category | Primary Location | Priority | Pattern |
|----------|------------------|----------|---------|
| tests | `backend/tests` | explicit | `backend/tests/**` |
| pages | `backend/app` | explicit | `backend/app/**` |
| docs | `docs` | inferred | `docs/**` |

### Path Enforcement Rules
Strictness: warn (writes outside a category's location are reported, not blocked).

## Retrieval Artifacts
- Chunk index: `.planning/codebase/index.jsonl`
- Symbols: `.planning/codebase/symbols.json`
- Search guide: `.planning/codebase/search.md`
