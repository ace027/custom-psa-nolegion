# Custom PSA — Plan

**Status (updated after payment tracking):** plan approved with all §13 defaults accepted. Phases 0-3 (the MVP) and payment tracking are built and tested. Waiting for your review of Phase 3 and your decision on what comes next (see `docs/BACKLOG.md`).

## Progress

| Phase | Status |
|---|---|
| 0. Scaffold | Done. Repo layout, Compose stack, CI workflow, Alembic, roles/RLS scaffolding, health checks |
| 1. Foundation | Done. Orgs/sites/contacts, staff users + roles, Entra OIDC, audit log, seed, UI, 68 backend tests, 6 frontend tests, 1 browser smoke test |
| 2. Ticketing | Done. Tickets, queues/categories/priorities, SLA clocks, notes, time, triage, Graph email in/out via a worker, dashboard, settings UI. 191 backend tests, 10 frontend tests, 2 browser smoke tests |
| 3b. Payment tracking (added after the MVP, at your request) | Done. Payments, applications, write-offs, receivables aging. 361 backend tests, 57 frontend tests, 3 browser tests |
| 3. Contracts & invoicing | Done. Agreements, products, rates, one-off charges, invoices, monthly run with review, PDF. 312 backend tests, 49 frontend tests, 3 browser tests |

### Payment tracking (3b): decisions and things to check
Choices you made: payments can be **partial and split across invoices**; overpayments become **unapplied credit**; **write-offs** exist (reason required); aging is by **days past the due date** in the standard buckets.
- **Balances are derived, never stored** on the (frozen) invoice: `total - active applications - active write-offs`. Payments, applications and write-offs are **immutable except for voiding with a required reason** (no edits, no deletes). Wrong entry? Void and re-record.
- **Database-enforced money rules** (triggers, so they hold even if the API is bypassed and under concurrent requests): apply only to a finalized invoice, same client, never more than the invoice balance or the payment's unapplied amount. A test fires ten simultaneous $30 payments at a $100 invoice: exactly three succeed.
- **An invoice with payments/write-offs cannot be voided** until those are undone.
- **No processor/bank integration:** nothing is charged or reconciled; payments are entered by hand. No refund record (void the payment), no payment reminders or statements (backlog).
- **Payment dates can't be in the future** (business time zone). Browser testing caught a real bug here: the form defaulted to the UTC date, which is "tomorrow" in a US evening. The form now leaves the date blank and the server supplies your business-timezone today.
- **New permission** `payment:write` (admin, billing). Voiding payments/applications, write-offs and their reversal use `billing:finalize`. Techs and read-only can *see* balances and receivables.
- **Invoice PDFs don't change** when payments arrive (no PAID stamp/balance): they are the document you issued.

### Phase 3 decisions and things to check (read these)
- **Your "go" is treated as approval of the §6 billing rules** as written (integer cents, per-line half-up rounding, per-line tax on the rounded amount, tax-rate snapshot, immutable finalized invoices, void + reissue). They are implemented exactly and covered by tests, including an independent exact-arithmetic reference check. Full explanation and a worked example: `docs/BILLING.md`.
- **No payment tracking.** There is no "paid" status, payment recording or A/R aging: you asked for no payment/accounting integrations and I didn't invent manual payment tracking. Invoices are issued and frozen; who has paid is tracked outside the PSA for now. **This is the biggest gap to decide on** (backlog).
- **One tax rate per client**, plus a "taxable" flag on each agreement, product and work type. No per-jurisdiction tax. Labor taxability varies by state and defaults to **not taxable**: confirm for your state.
- **No proration** (as decided): an agreement active at any time in the month bills the full month at the quantity on the day the run starts. Manual adjustment happens in the review step.
- **Time is grouped** into one invoice line per ticket and work type (billed hours = sum of the entries' rounded minutes). Quantity is stored to 4 decimal places, which is exact for 15/30/60-minute increments.
- **A work type with no rate is never billed at $0**: the time stays unbilled and the run warns.
- **Rates**: default hourly rate per work type plus an optional per-client override (the §13.7 default).
- **Corrections**: void + reissue, or a negative manual "credit" line. A negative-total invoice can't be finalized (no credit-memo document yet).
- **Invoice number format is fixed** `INV-YYYY-NNNN` (year of the invoice date, in your business time zone). Payment terms are per client (default Net 30); no automatic late fees.
- **One run per month, enforced in the database.** Cancelling an unfinalized run frees the month. After finalizing, fixes go on a one-off invoice, never a second run.
- **Immutability is enforced by PostgreSQL triggers**, not just app code: a finalized invoice and its lines cannot be changed (only voided), invoices can't be deleted, and the runtime role has no DELETE on the billing ledger. The restore drill confirms this survives a backup/restore.
- **Product cost (your margin) is hidden** from everyone except admin/billing (found in review: the catalog endpoint would otherwise have shown it to techs).
- **Company details (name, address, footer) are admin-only** (Settings); finalizing is blocked until a company name is set.
- **PDF invoices** are generated server-side (reportlab, pure Python; new dependency). Emailing invoices is manual.
- **Caught by tests while building (fixed before commit):** the "archived client skipped" warning was not being saved on the run.
- **Not verified**: nothing here depends on Microsoft 365. Everything was run for real: in the browser, and in Docker Compose (run, review, finalize, PDF, DB tamper attempts, backup/restore).

### Phase 2 deviations and decisions (read these)
- **Not verified against real Microsoft 365.** The Graph client is tested with `httpx.MockTransport`, and the whole mail loop (ingest, triage, reply threading, outbound send) was run end to end against a local fake Graph, both as processes and in Docker Compose. Real tenant behavior (Exchange RBAC scoping, throttling, message quirks) is on the manual checklist. **Please do the `docs/MAIL_SETUP.md` steps against a test mailbox before pointing real mail at it.**
- **Mailbox scoping uses Exchange RBAC for Applications**, not the Application Access Policy named in the original plan: Microsoft documents the latter as legacy and says new setups shouldn't use it. The connector app gets **no Entra-consented mail permissions** (those would be tenant-wide).
- **Polling design changed from "delta query" to "unread messages in the Inbox, mark read after commit".** Simpler to reason about; idempotent on the Graph message id, so a crash never double-creates tickets. (Graph also rejects `$filter` + a different `$orderby`, so we sort client-side.) Delta sync is in the backlog.
- **Plain-text email only**: we ask Graph for the text body, so HTML from email is never stored or rendered. Quoted reply history is trimmed for display; the full original is stored.
- **Security rule added beyond the plan:** a ticket number in a subject is not enough to append to a ticket. The sender must already be associated with it; otherwise a new "needs triage" ticket is created. Automated mail (out-of-office, bounces, bulk, own address) is ignored.
- **SLA targets live on priorities** (business minutes, first response + resolution) and the single business-hours calendar lives in `settings`: no separate `sla_policies` table. Due dates are always derived as `created + target + business minutes spent paused`, so pausing never mutates dates. Stopped clocks: waiting on customer, resolved, closed. **Changing business hours does not recompute existing due dates** (only priority/pause changes do).
- **Statuses are a fixed set** (new, open, waiting on customer, resolved, closed) with fixed labels; queues/categories/priorities/work types are editable rows.
- **Time-entry rule (billing-critical):** billable minutes = actual rounded **up** to the configured increment (default 15), stored per entry at entry time; non-billable = 0. Entries are voided, never deleted; only the owner or an admin can change them. Phase 3 will lock entries once invoiced.
- **Notes are immutable** (the app database role cannot UPDATE them, except moving them to an organization during triage). Outbound email uses an outbox table + worker retries (5 attempts).
- **Time zone default is `America/Chicago`** (business hours 08:00-17:00 Mon-Fri). **Please set yours in Settings.** It drives SLA math and the default date of time entries.
- **Work type has no default on the time form** (the UI makes you pick), because Phase 3 will bill by work type and a silent default would mis-bill.
- **Worker reports its own state** to the database (mailbox configured, last seen, last error) because the API container deliberately doesn't hold the Graph secret.
- **Bug caught by tests:** an unscoped duplicate-message check under RLS saw no rows. A new guard test now fails if any table with `organization_id` lacks forced RLS (`audit_log` is the one documented exception: written by unscoped auth events, append-only, admin-only reads).
- **Backups now include attachments** (separate encrypted tarball); restore handles both.
- Added `backend/dev/fake_graph.py` (dev-only stand-in for Graph) and configurable `GRAPH_BASE_URL`/`GRAPH_LOGIN_URL` (GCC High).

### Phase 1 deviations and discoveries (read these)
- **Backup gotcha found while testing:** `FORCE ROW LEVEL SECURITY` makes `pg_dump` fail for a non-`BYPASSRLS` owner. Good (loud), but the owner role must have `BYPASSRLS`. Documented in `docs/DEVELOPMENT.md` and `docs/BACKUP_RESTORE.md`; an automated dump→restore drill in the test suite now guards it.
- **Compose stack verified for real** (after the first pass, once Docker was running in the sandbox): fresh `docker compose up --build` gives healthy db/api/proxy, migrations exit 0, the API runs as non-root `psa_app` (no superuser, no BYPASSRLS), the proxy serves the UI plus security headers, `/api/*` reaches the API, dev login is a 404 in production mode, and a request through the production images creates an org with its audit row. `deploy/backup.sh`, the documented scratch-DB restore drill, and the destructive `deploy/restore.sh` all worked against the containers (restore removed data created after the backup and kept RLS and the append-only audit grants). Still untested: real Entra sign-in, and automatic HTTPS with a real hostname.
- **Python 3.11 locally / 3.12 in Docker:** code is written to run on both; CI uses 3.12.
- **CSRF:** besides `SameSite=Lax` cookies, every state-changing request must carry `X-Requested-With: psa` (added beyond the plan; cheap defense in depth).
- **Dev login:** a development-only sign-in path exists so the app is usable without an Entra tenant. It is disabled unless `DEV_LOGIN_ENABLED=true`, and hard-refused when `ENVIRONMENT=production`.
- **First admin** on a fresh production DB is bootstrapped with one SQL insert (see `docs/ENTRA_SETUP.md`). It is the only unaudited write.
- Organization `default tax settings` were left out of Phase 1 (nothing uses them yet); they arrive with Phase 3.
- The plan's `tests per endpoint` promise is enforced by a test that fails if any route is undocumented, missing a permission declaration, or never called by the suite.

## 1. Decisions locked in (from your answers)

| Topic | Decision |
|---|---|
| Backend | Python 3.12 + FastAPI |
| ORM / migrations | SQLAlchemy 2.x + Alembic (migrations in repo) |
| DB | PostgreSQL 16 |
| Frontend | React + TypeScript + Vite + Tailwind |
| Isolation | App-layer scoping **plus** Postgres Row-Level Security as a backstop |
| Money | USD only, integer cents, per-line tax rate, time rounds up to a configurable increment (default 15 min) |
| Scale | 1-10 staff, <500 tickets/mo, single VM, Docker Compose, no HA |
| Roles | Fixed global roles: admin, tech, billing, read-only |
| Mail | Microsoft Graph app registration, one shared mailbox, polling |
| Recurring billing | Bill in advance, quantity counted at run time, no proration, manual adjust in review |
| Counts (users/devices) | Manual quantity field on the agreement in Phase 3 |

## 2. Architecture

```
Browser ──HTTPS──> Reverse proxy (Caddy) ──> web (static React build)
                                         └─> api (FastAPI, uvicorn)
                                                 │
                                    worker (same image, different command)
                                    - Graph mailbox poller
                                    - SLA clock checks
                                                 │
                                            PostgreSQL 16
```

- **Single Python codebase, two processes** from one image: `api` and `worker`. The worker is a plain loop (APScheduler or a simple scheduled loop) — no Celery or Redis. Postgres is the only stateful dependency. Revisit only if load demands it.
- **Reverse proxy:** Caddy by default (automatic TLS, tiny config). If you already run nginx/Traefik/NPM, we skip the proxy container and just document the upstream. *(Open question 1.)*
- **Layering:** `routers` (HTTP, auth, validation) → `services` (business rules, audit) → `repositories` (the only place that touches queries, always tenant-scoped). Routers never write raw queries.
- **API:** REST + JSON, OpenAPI generated by FastAPI. Every endpoint has a summary, request/response models and error codes. A test asserts that no route is missing docs or a permission declaration.
- **Config/secrets:** env vars via `pydantic-settings`; `.env.example` in repo, real `.env` and Docker secrets never committed. Secret scanning in CI.
- **Dependencies** (kept short): fastapi, uvicorn, sqlalchemy, alembic, psycopg, pydantic-settings, authlib (OIDC), msal or httpx for Graph, pytest, ruff. Frontend: react, react-router, TanStack Query, tailwind. No component-library framework to start.

## 3. Multi-tenancy and isolation (design detail)

"Tenant" here means **client organization**, not another MSP. There is one MSP (you).

- Every client-owned table has `organization_id NOT NULL` with an index. (Tickets, contacts, sites, agreements, invoices, time entries, and so on.)
- The repository layer takes a **scope object** (`Scope(org_ids=... | ALL)`) built from the authenticated principal:
  - staff: `ALL` (per your fixed global roles decision)
  - portal contact (later): exactly their own `organization_id`
- **RLS backstop:** on each request the API sets `SET LOCAL app.org_scope = '...'` inside the transaction; RLS policies compare `organization_id` against it. The app connects as a **non-owner, non-superuser role** (owners bypass RLS unless `FORCE ROW LEVEL SECURITY` is set; we set it). Migrations run as a separate owner role.
- Tests: a dedicated isolation suite creates two orgs and asserts that a portal-scoped principal can never read or write the other org's rows, at both the repo layer and via raw SQL under RLS.
- **Regret flag:** RLS interacts with connection pooling (must use `SET LOCAL` inside a transaction, never session-level `SET`). This is the one place I'd deliberately keep simple and heavily tested.

## 4. Auth

- **Staff:** Entra ID OIDC (authorization code + PKCE) using `authlib`. Single-tenant app registration. On first login, the user is matched by `oid`/`tid` claims and must be pre-provisioned or auto-created as **read-only** (your choice, *open question 2*). Roles are assigned in the PSA, not from Entra groups (simpler; can add group mapping later).
- **Sessions:** server-side session cookie (HttpOnly, Secure, SameSite=Lax), stored in Postgres. Preferable to JWTs in the browser for a small app: revocable, no token-refresh logic.
- **Client portal (later phase, designed for now):** separate `portal_users` table and a separate auth path (email + password with mandatory MFA or magic-link), issuing a session whose principal is scoped to one organization. Separate cookie name and route prefix (`/portal-api`). Staff and portal principals are different types in code so one can't be mistaken for the other.
- **Auth events logged:** login success/failure, logout, role change, session revoked, denied authorization (403).
- **Least privilege:** every route declares a required permission; default is deny. Permission matrix lives in one file, `permissions.py`, and is tested.

Role matrix (Phase 1 draft):

| Capability | admin | tech | billing | read-only |
|---|---|---|---|---|
| Manage users/roles | ✔ | | | |
| Orgs/contacts/sites write | ✔ | ✔ | | |
| Tickets/time/notes write | ✔ | ✔ | | |
| Contracts/invoices write | ✔ | | ✔ | |
| Finalize billing run | ✔ | | ✔ | |
| Read everything | ✔ | ✔ | ✔ | ✔ |
| View audit log | ✔ | | | |

## 5. Audit log

- Append-only `audit_log` table: `id, occurred_at, actor_type, actor_id, action, entity_type, entity_id, organization_id, before (jsonb), after (jsonb), request_id, ip`.
- Written **in the same DB transaction** as the change, by the service layer through one `audit.record()` helper, so a write cannot succeed without an audit row.
- DB role used by the app has `INSERT` and `SELECT` only on `audit_log` (no `UPDATE`/`DELETE`).
- Sensitive fields (password hashes, tokens) are redacted from before/after.
- A test iterates all mutating routes and asserts an audit row exists after each.

## 6. Data model (core; Phases 1-3)

Conventions: UUIDv7 or bigint identity PKs (*I recommend bigint identity for readability plus a `public_id` for URLs where needed*), `created_at`/`updated_at`, soft-delete (`archived_at`) instead of hard delete for business entities, money as integer cents, timestamps `timestamptz` (UTC).

**Phase 1**
- `organizations` (name, status, billing address, default tax settings, notes)
- `sites` (organization_id, name, address)
- `contacts` (organization_id, name, email, phone, title, is_primary, is_billing_contact; email is unique per org)
- `users` (staff; entra_oid, email, display_name, role, is_active)
- `sessions`, `audit_log`

**Phase 2**
- `queues`, `categories`, `priorities`, `statuses` (statuses as a small fixed enum + configurable labels, **not** free-form)
- `sla_policies` (per priority: first-response minutes, resolution minutes; business-hours calendar)
- `tickets` (number, organization_id, contact_id, site_id, queue_id, category_id, priority, status, assignee_id, sla_policy_id, first_response_due, resolution_due, first_responded_at, resolved_at, source)
- `ticket_notes` (ticket_id, author, body, visibility `internal|customer`, source `ui|email`)
- `time_entries` (ticket_id, user_id, started_at, minutes_actual, minutes_billable, billable, work_type, note, `invoice_line_id` nullable)
- `email_messages` (graph_message_id unique, internet_message_id, in_reply_to, conversation_id, ticket_id, direction, raw headers, body) for threading and idempotent ingest
- `attachments` (stored on local volume, metadata in DB)

**Phase 3**
- `products` (sku, name, unit price cents, taxable, cost)
- `agreements` (organization_id, type `per_user|per_device|flat`, unit price cents, quantity, taxable, start, end, billing_day, status)
- `agreement_quantity_log` (history of manual quantity changes, cheap to add now, useful evidence later)
- `invoices` (number, organization_id, status `draft|final|void`, period_start/end, subtotals, tax_total, total, issued_at)
- `invoice_lines` (invoice_id, kind `time|product|agreement`, description, quantity (numeric), unit_price_cents, tax_rate_bp, tax_cents, line_total_cents, source refs)
- `billing_runs` (period, status `draft|reviewed|finalized`) and `billing_run_invoices`
- `invoice_number_seq` (gap-free per year; assigned at finalize, not at draft)

**Designed for, not built:** `portal_users`, `assets`, `projects/tasks`, `quotes`, `integration_links(external_system, external_id, entity_type, entity_id)` (a generic mapping table so NinjaOne/Hudu/M365 IDs never pollute core tables), `webhook_outbox` for n8n.

### Billing math rules (proposed — please confirm)
1. All money is integer cents. No floats anywhere in billing.
2. Time: `minutes_billable = ceil(actual / increment) * increment`, with a configurable minimum per entry (default: none).
3. Line total = `round_half_up(quantity × unit_price)`; **tax is computed per line**, rounded to the cent per line, and the invoice tax total is the sum of line taxes (avoids penny drift between the lines and the total).
4. Tax rate stored as **basis points on the invoice line** (a snapshot), so changing an org's rate later never rewrites history.
5. **Finalized invoices are immutable.** Corrections = void + reissue or a credit line on the next invoice. Enforced in the service and by a DB trigger.
6. Recurring run: quantity is snapshotted onto the invoice line at run time. Review step lets you edit draft invoices before finalizing. Re-running the same period is idempotent (unique `(agreement_id, period)`), so you can't double-bill.
7. Time and products are marked with `invoice_line_id` when they're put on an invoice; voiding the invoice releases them.

## 7. Email-to-ticket (Phase 2)

- Azure app registration with `Mail.ReadWrite` + `Mail.Send` **application** permissions, **restricted to the one support mailbox with an Exchange Application Access Policy** (or RBAC for Applications). Without that restriction the app could read every mailbox in the tenant, so this is a hard requirement in the setup doc.
- Worker polls Graph delta query every ~60s for the Inbox folder. Idempotent on `graph_message_id`.
- Threading order: (1) ticket number token in subject `[#1234]`, (2) `In-Reply-To`/`References` matched against stored `internet_message_id`, (3) otherwise a new ticket.
- Sender → contact matched by email (and domain → org as a fallback); unknown senders create a ticket in an "Unmatched" state for triage rather than being dropped or auto-creating orgs.
- Loop protection: ignore auto-replies/bounces (`Auto-Submitted`, `X-Auto-Response-Suppress`, mailer-daemon), and never reply to ourselves.
- Outbound: customer-visible notes can be emailed via Graph `sendMail` from the shared mailbox, with the ticket token in the subject.
- Regret flag: HTML email is messy. Plan: store the original, render a **sanitized** version (allow-list sanitizer), strip quoted history heuristically, and never render remote images by default.

## 8. SLA

- SLA policy per priority gives first-response and resolution targets; due times computed against a business-hours calendar (one calendar in Phase 2, timezone configurable).
- Clock **pauses** in statuses flagged `pauses_sla` (e.g. Waiting on Customer).
- Dashboard "SLA at risk" = due within a configurable threshold (default 25% of the target remaining) or already breached.

## 9. Deployment, backups, ops

- `docker-compose.yml`: `proxy`, `web`, `api`, `worker`, `db`. Named volumes for Postgres data and attachments.
- Migrations run as a one-shot `migrate` step before `api` starts.
- **Backups:** nightly `pg_dump` (custom format) plus a tarball of attachments, encrypted (age or gpg) and copied off the VM. Retention 14 daily / 8 weekly. `docs/BACKUP_RESTORE.md` covers restore procedure and a **restore test** you run quarterly. The restore script gets tested in CI against a scratch DB.
- Health endpoints `/healthz` and `/readyz`. Structured JSON logs; auth events go to a distinct logger so they can be shipped to your SIEM later.
- CI (GitHub Actions): ruff, pytest against a real Postgres service container, frontend typecheck/build, dependency audit (pip-audit, npm audit), secret scan.

## 10. Testing strategy

- pytest against **real Postgres** (no SQLite), with RLS active in tests.
- Per endpoint: happy path, authz denied per role, validation error, audit row present.
- Billing math: table-driven unit tests plus property-style tests (sum of lines == invoice total, no float drift).
- Isolation suite (section 3).
- OpenAPI completeness test (every route documented and permission-tagged).
- Frontend: a few Vitest component tests plus one Playwright smoke test per phase, not exhaustive.

## 11. Phased roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Scaffold** (after approval) | Repo layout, Compose, CI, Alembic baseline, app roles/RLS scaffolding, health check, README | `docker compose up` works; CI green |
| **1. Foundation** | Orgs, sites, contacts; Entra SSO login; users/roles; audit log; auth event logging; seed script; org/contact CRUD UI | Role matrix enforced by tests; audit on every write; isolation suite passing |
| **2. Ticketing** | Tickets, queues/categories/priorities, notes (internal/customer), time entries, SLA engine, Graph email ingest + reply, dashboard | Email round-trip works against a test mailbox; SLA pause/resume tested |
| **3. Contracts & invoicing** | Agreements, products, billable rollup, invoice draft/finalize/void, monthly run + review, PDF/print view of invoice | Billing math tests; run is idempotent; finalized invoices immutable |
| **Statements & reminders** (post-MVP) | Reminder stages (1/15/30/60), monthly statements, review-then-send queue, PDF attachments, immutable sent records | Nothing sends without approval; stage issued once per invoice; stale notices refreshed; DB triggers freeze sent records |
| Later | Portal, assets, projects, reporting, quotes, integrations, compliance evidence | Listed in BACKLOG.md; data model already leaves room |

Each phase ends with: tests passing, README/PLAN updated, seed data, manual verification checklist (`docs/verify/phase-N.md`), and a short change summary.

## 12. Risks and "you'll regret this later" flags

1. **Billing math** (section 6): rounding, tax snapshotting and invoice immutability are the parts hardest to fix after real invoices exist. Confirm rules before Phase 3 starts.
2. **RLS + pooling** (section 3): easy to misconfigure into either *no* protection or *broken* queries. Mitigated by tests, but it's the most technical piece.
3. **Graph mailbox scope** (section 7): an unrestricted app registration can read all mail in your tenant. Setup doc must enforce the access policy. Also this is a CMMC-relevant control.
4. **Email HTML/XSS and attachments:** sanitize on render, size limits, and consider malware scanning later (backlog).
5. **Ticket data is sensitive** (may hold client credentials, CUI-adjacent info). Encrypt backups, encrypt the disk/volume, and keep the audit log. If any client data is truly CUI, hosting requirements change (FedRAMP-moderate-equivalent hosting for CUI systems). Worth deciding early whether the PSA will ever hold CUI. *(Open question 5.)*
6. **Single VM, no HA:** accepted for your scale; the mitigation is tested restores, not redundancy.
7. **Scope creep:** every extra idea goes to `docs/BACKLOG.md`.
8. **Bus factor of 1:** favor boring code, comment "why" not "what", keep `docs/` current.
9. **Statuses/priorities as data vs. enums:** fully configurable workflows are a time sink. Plan uses a fixed status enum with editable labels, and priorities/queues/categories as editable rows.
10. **Time zones:** store UTC, display in org/staff zone, define "billing day" and business hours in a single configured zone.

## 13. Open questions (RESOLVED: all defaults accepted)

1. **Reverse proxy:** do you already run one (nginx / Traefik / NPM)? *Default: ship Caddy in Compose.*
2. **New Entra user handling:** auto-create as read-only on first login, or require an admin to pre-provision? *Default: pre-provision only (safer).*
3. **Ticket numbering:** simple incrementing number (e.g. 10001+) or year-prefixed (2026-0001)? *Default: plain incrementing.*
4. **Invoice output:** is an HTML/print-to-PDF view enough for Phase 3, or do you need generated PDFs emailed to clients? *Default: server-generated PDF download; emailing is manual.*
5. **CUI:** could client CUI ever be stored in tickets/attachments? *Default: assume no, with a warning banner; revisit hosting if yes.*
6. **Business hours:** one calendar (e.g. Mon-Fri 8-5 Central) for all SLAs? *Default: yes.*
7. **Work types / rates:** one hourly rate per org, or rates by work type (e.g. remote vs. onsite vs. after-hours)? *Default: a rate per work type with an optional per-org override.*
8. **Invoice numbering and terms:** format, net terms per org (Net 15/30), late-fee text? *Default: `INV-YYYY-0001`, terms per org, no automatic late fees.*
9. **Hypervisor/VM baseline:** OS on the VM (I'd assume Ubuntu LTS or Debian) and where offsite backups go (S3-compatible, SMB share, other)?
10. **Frontend scope:** staff UI only for MVP (portal deferred). Confirmed?

## 14. Proposed repo layout

```
/backend        FastAPI app, alembic/, tests/
/frontend       React + Vite + Tailwind
/deploy         compose files, Caddyfile, backup scripts
/docs           PLAN.md, BACKLOG.md, BACKUP_RESTORE.md, verify/
docker-compose.yml, .env.example, README.md
```

---
**Next step:** reply with approvals/changes to sections 1, 6 (billing rules) and 13. On approval I'll do Phase 0 (scaffold) and Phase 1, stopping after each for your review.
