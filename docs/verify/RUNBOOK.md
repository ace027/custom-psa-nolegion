# Owner verification runbook

One ordered pass through every deferred owner check (source: [.planning/VERIFY.md](../../.planning/VERIFY.md)) and every checklist in this folder. Fill in the Result column of each row with `pass`, `fail` or `deferred`, and put anything worth remembering in Notes.

## Before you start

Prerequisites (from `.env.example`, the README and the setup docs):

- Entra staff sign-in app, see [docs/ENTRA_SETUP.md](../ENTRA_SETUP.md). Its redirect URI must end in `/api/v1/auth/callback`. Env: `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, plus `PUBLIC_URL` and `SITE_ADDRESS`.
- Client-portal sign-in: a SEPARATE multi-tenant app registration per [docs/PORTAL_SSO.md](../PORTAL_SSO.md). Env: `PORTAL_ENTRA_CLIENT_ID`, `PORTAL_ENTRA_CLIENT_SECRET`. Leave empty to offer emailed one-time links only.
- Mail and calendar: a separate Graph app registration per [docs/MAIL_SETUP.md](../MAIL_SETUP.md) and [docs/CALENDAR_SETUP.md](../CALENDAR_SETUP.md). Env: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `MAIL_MAILBOX`.
- RMM and vendor credentials (NinjaOne, Hudu): [docs/INTEGRATIONS.md](../INTEGRATIONS.md). They are encrypted with `CREDENTIALS_KEY` in `.env`.
- Outbound webhooks and API keys: [docs/WEBHOOKS.md](../WEBHOOKS.md), [docs/API_KEYS.md](../API_KEYS.md).
- Payment credentials: the project decision is that there is no payment processor and portal payments stay manual, so none are needed. See [payments.md](payments.md).

Start the stack (production, from the README):

```sh
cp .env.example .env     # fill it in, never commit .env
docker compose up -d --build
```

Start the stack (development, from the README):

```sh
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" -c constraints.txt
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload            # API on :8000
cd ../frontend && npm ci && npm run dev  # UI on :5173, dev login enabled
```

Load seed data: `cd backend && alembic upgrade head && python -m app.seed` (the same line as above; see [docs/DEVELOPMENT.md](../DEVELOPMENT.md)).

## Owner decisions to confirm

- [x] Register the multi-tenant portal app per docs/PORTAL_SSO.md (Phase 14)
- [x] `kb:write` is limited to admin and tech (assumed default, Phase 13)
- [x] Portal uploads are limited to 10 MB and the extension allowlist (assumed default, Phase 14)
- [x] Update the staff Entra redirect URI to `<public_url>/api/v1/auth/callback`; the API has no `/api` alias (Phase 12, STATE.md decisions)
- [ ] Block-hour unused hours expire at month end with no rollover (STATE.md decisions). Make this configurable.
- [x] One tax rate per client (STATE.md decisions)
- [x] No payment processor; portal payments stay manual (STATE.md decisions)
- [x] Default markup stays 0% until you set it (Phase 10)

## Real-tenant Outlook spike

Setup first: create the "PSA Techs" group and the Exchange RBAC for Applications scope ([docs/CALENDAR_SETUP.md](../CALENDAR_SETUP.md)). Run everything from `backend/` with the Graph env vars set. The script is read-only by default and never prints the client secret or token.

```sh
cd backend
python dev/graph_calendar_spike.py --mailbox tech@example.com                 # read-only getSchedule
python dev/graph_calendar_spike.py --mailbox tech@example.com --write         # also create, re-create (idempotency), update, delete a test event
python dev/graph_calendar_spike.py --mailbox tech@example.com --outside other@example.com   # RBAC boundary check
```

Per VERIFY.md Phase 4, the third run is `--write --outside <someone outside the group>`; the outside call must be refused.

What a pass looks like: every line printed starts with `PASS` and the exit code is 0 (any `FAIL` gives exit code 1). Expected steps: `getSchedule read`; with `--write`: `create_event`, `idempotent create`, `update_event`, `delete_event`, `delete again tolerated (404)`; with `--outside`: `RBAC boundary` PASS with "denied with <status>". A `WARN` on `RBAC boundary` means the outside mailbox was readable, so the scope is not enforced; treat that as a fail. Paste the final PASS/FAIL block into the Notes of P04-02 and P04-03.

## Checks by phase

### Phase 1: Block-hour / retainer agreements

Checklists: [billing-block-hours.md](billing-block-hours.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P01-01 | Walk through docs/verify/billing-block-hours.md | | |

### Phase 2: Scheduling: availability & appointments

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P02-01 | (no manual checks; covered by automated tests) | | |

### Phase 3: Dispatch board

Checklists: [dispatch-board.md](dispatch-board.md), [dispatch-spike.md](dispatch-spike.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P03-01 | Walk through docs/verify/dispatch-board.md | | |
| P03-02 | Walk through docs/verify/dispatch-spike.md | | |
| P03-03 | e2e smoke.spec.ts "ticket lifecycle" fails before phase 4; confirm it is fixed or fix it | | |

### Phase 4: Outlook push + free/busy

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P04-01 | Create the "PSA Techs" group and Exchange RBAC for Applications scope (docs/CALENDAR_SETUP.md) | | |
| P04-02 | Run `cd backend && python dev/graph_calendar_spike.py --mailbox <tech>` (read-only) on the real tenant | | |
| P04-03 | Run it again with `--write`, then with `--write --outside <someone outside the group>`; the outside call must be refused | | |
| P04-04 | Turn on Outlook sync in Settings; book, move, reassign and cancel an appointment and check each tech's Outlook calendar | | |
| P04-05 | Put a meeting in a tech's Outlook; within 5 minutes the board shows hatched busy time with the cache-age caption | | |
| P04-06 | Force a failure (e.g. a tech outside the group); the board shows the failed badge and Retry works after fixing it | | |

### Phase 5: Client confirmations + on-call

Checklists: [client-notices-oncall.md](client-notices-oncall.md), [notifications.md](notifications.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P05-01 | Walk through docs/verify/client-notices-oncall.md | | |

### Phase 6: RMM alerts to tickets

Checklists: [rmm-alerts.md](rmm-alerts.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P06-01 | Walk through docs/verify/rmm-alerts.md | | |
| P06-02 | Check the NinjaOne alert field names (uid, deviceId, severity, sourceConfigUid) against a live tenant first | | |
| P06-03 | Enable alerts with defaults on the Integrations card | | |
| P06-04 | A MODERATE+ alert on a mapped device makes one RMM ticket with device link and severity priority | | |
| P06-05 | A repeating alert raises occurrences and makes no second ticket | | |
| P06-06 | A MINOR alert makes no ticket | | |
| P06-07 | An unsynced device makes no ticket until asset sync | | |
| P06-08 | Clearing an untouched alert resolves the ticket with a note | | |
| P06-09 | Clearing after a tech note adds a note only and the ticket stays open | | |
| P06-10 | Rules note_only and always_resolve behave as labelled | | |
| P06-11 | Re-firing after resolve makes a new ticket linked as related | | |
| P06-12 | Broken credentials show an error on the card and change no tickets | | |
| P06-13 | Check now queues a poll and is disabled while alerts are off | | |
| P06-14 | Tech and read-only users cannot see the card | | |

### Phase 7: Automation & API

Checklists: [automation-api.md](automation-api.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P07-01 | Walk through docs/verify/automation-api.md (API keys, webhooks, automation rules) | | |
| P07-02 | Unverified: a real Microsoft Teams Workflows webhook URL renders the adaptive card | | |
| P07-03 | Unverified: a real n8n instance accepts the payload and the HMAC-SHA256 signature verifies | | |
| P07-04 | Unverified: a LAN n8n works with WEBHOOK_ALLOW_PRIVATE_HOSTS=true (https only) | | |
| P07-05 | A rule's assign, escalate, notify, webhook and create-ticket actions each work on a real ticket | | |
| P07-06 | Rules never trigger other rules; a rule firing more than 200 times in an hour switches itself off | | |

### Phase 8: Projects & project billing

Checklists: [projects.md](projects.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P08-01 | Walk through docs/verify/projects.md (projects, phases, tasks, dependencies, board, budget, fixed-fee and T&M billing) | | |
| P08-02 | Confirm: milestones (phase completion) are not billed | | |
| P08-03 | Confirm: project time does not use block hours | | |

### Phase 9: CRM & renewals

Checklists: [crm.md](crm.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P09-01 | Walk through docs/verify/crm.md (leads and conversion, pipeline, quote link and win, forecast, renewal reminders) | | |
| P09-02 | Confirm: the forecast is an estimate only and never creates invoices | | |
| P09-03 | Confirm: the renewal worker sends one email per new reminder and never repeats it | | |

### Phase 10: Procurement & inventory

Checklists: [procurement.md](procurement.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P10-01 | Walk through docs/verify/procurement.md (vendors, purchase orders, receiving with serials, delivery, undo, consume, markup rules, client card) | | |
| P10-02 | Confirm: a client is billed when the item is delivered, not when it is received | | |
| P10-03 | Confirm: markup order is line, then product rule, then category rule, then the default | | |
| P10-04 | Confirm: the default markup is 0% until you set it | | |
| P10-05 | Confirm: taxability comes from the purchase order line, which defaults from the product | | |
| P10-06 | Confirm: undo delivery is refused once the charge is invoiced, and a credit memo is the fix | | |

### Phase 11: Reporting & dashboards

Checklists: [reports.md](reports.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P11-01 | Walk through docs/verify/reports.md (SLA, utilisation, aging, profitability, dashboards, scheduled emails) | | |
| P11-02 | Confirm: SLA population is tickets created in the range, and pending tickets are left out of the met percentage | | |
| P11-03 | Confirm: utilisation capacity is work hours minus holidays and time off, and logged includes internal time | | |
| P11-04 | Confirm: profitability cost is labour + goods (at delivery) + expenses, with revenue excluding tax by invoice date | | |
| P11-05 | Confirm: labour comes from each user's cost rate, and time with no rate counts as $0 and is flagged | | |
| P11-06 | Confirm: weekly reports cover the previous Monday to Sunday, monthly the previous calendar month (day 1-28) | | |
| P11-07 | Confirm: scheduled emails go once per period, only to staff holding report:read, and failures are not retried | | |

### Phase 12: Integration readiness

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P12-01 | Update the Entra app registration redirect URI to `<public_url>/api/v1/auth/callback`, then sign in | | |
| P12-02 | Build with VITE_BRAND_NAME, VITE_BRAND_LOGO and VITE_BRAND_COLORS set and check the header and login page | | |
| P12-03 | An API-key request creates a ticket with source `api` | | |
| P12-04 | An existing n8n/webhook consumer still works (outbound webhook URLs are unchanged) | | |

### Phase 13: Knowledge base

Checklists: [kb.md](kb.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P13-01 | Walk through docs/verify/kb.md | | |
| P13-02 | Confirm: kb:write for admin and tech only (assumed default) | | |

### Phase 14: Portal polish

Checklists: [portal-polish.md](portal-polish.md), [portal.md](portal.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P14-01 | Walk through docs/verify/portal-polish.md | | |
| P14-02 | Real-tenant check: register the multi-tenant portal app per docs/PORTAL_SSO.md and sign in from a client tenant | | |
| P14-03 | Confirm: uploads limited to 10 MB and the extension allowlist (assumed default) | | |
## Other checklists

These files are not tied to a single phase above. Walk through any that still apply to what you use.

- [billing-phase3a.md](billing-phase3a.md)
- [billing-phase3b.md](billing-phase3b.md)
- [billing-phase3c.md](billing-phase3c.md)
- [design.md](design.md)
- [payments.md](payments.md)
- [phase-1.md](phase-1.md)
- [phase-2.md](phase-2.md)
- [phase-3.md](phase-3.md)
- [quoting.md](quoting.md)
- [statements-reminders.md](statements-reminders.md)
- [tickets-phase1a.md](tickets-phase1a.md)
- [tickets-phase1b.md](tickets-phase1b.md)
- [tickets-phase1c.md](tickets-phase1c.md)
- [tickets-phase1d.md](tickets-phase1d.md)
- [time-phase2a.md](time-phase2a.md)
- [time-phase2b.md](time-phase2b.md)
- [time-phase2c.md](time-phase2c.md)
- [vciso-phase1.md](vciso-phase1.md)

## Recording failures

For each `fail`:

1. Open a fix with `/triad:quick "<ID>: <what failed>"`, for example `/triad:quick "P06-04: repeating alert made a second ticket"`.
2. Re-run the check.
3. Change the Result to `pass`.

If you accept the failure instead, write `deferred (owner-accepted): reason` in the Result or Notes cell.
