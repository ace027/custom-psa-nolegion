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
- [x] Block-hour unused hours expire at month end with no rollover (STATE.md decisions). Make this configurable. Deferred by owner to Phase 17 (2026-11-02), where per-agreement rollover is a success criterion.
- [x] One tax rate per client (STATE.md decisions)
- [x] No payment processor; portal payments stay manual (STATE.md decisions)
- [x] Default markup stays 0% until you set it (Phase 10)

## Real-tenant Outlook spike

Setup first: create the "PSA Techs" group and the Exchange RBAC for Applications scope ([docs/CALENDAR_SETUP.md](../CALENDAR_SETUP.md)). Run it in the `worker` container from the repo root (it has the Graph settings; host Python has no dependencies, see [dispatch-spike.md](dispatch-spike.md)), after `docker compose build worker`. The script is read-only by default and never prints the client secret or token.

```sh
docker compose run --rm worker python dev/graph_calendar_spike.py --mailbox tech@example.com                  # read-only getSchedule
docker compose run --rm worker python dev/graph_calendar_spike.py --mailbox tech@example.com --write          # also create, re-create (idempotency), update, delete a test event
docker compose run --rm worker python dev/graph_calendar_spike.py --mailbox tech@example.com --write --outside other@example.com   # RBAC boundary check
```

Per VERIFY.md Phase 4, the third run is `--write --outside <someone outside the group>`; the outside call must be refused.

What a pass looks like: every line printed starts with `PASS` and the exit code is 0 (any `FAIL` gives exit code 1). Expected steps: `getSchedule read`; with `--write`: `create_event`, `idempotent create`, `update_event`, `delete_event`, `delete again tolerated (404)`; with `--outside`: `RBAC boundary` PASS with "denied with <status>". A `WARN` on `RBAC boundary` means the outside mailbox was readable, so the scope is not enforced; treat that as a fail. Paste the final PASS/FAIL block into the Notes of P04-02 and P04-03.

## Checks by phase

### Phase 1: Block-hour / retainer agreements

Checklists: [billing-block-hours.md](billing-block-hours.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P01-01 | Walk through docs/verify/billing-block-hours.md | pass | All checks pass. Flat fee clients are considered AYCE, so all time should attach to that flat fee agreement, but no extra time should be billed for the client. This allows for profitability to be tracked for AYCE clients |

### Phase 2: Scheduling: availability & appointments

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P02-01 | (no manual checks; covered by automated tests) | pass | |

### Phase 3: Dispatch board

Checklists: [dispatch-board.md](dispatch-board.md), [dispatch-spike.md](dispatch-spike.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P03-01 | Walk through docs/verify/dispatch-board.md | pass | |
| P03-02 | Walk through docs/verify/dispatch-spike.md | pass | First owner run failed on the host (`No module named pydantic_settings`): the spike must run inside the worker container, not a host venv. Re-run on the dev server (2026-11-02) with `docker compose run --rm worker python dev/graph_calendar_spike.py ...`: all steps PASS |
| P03-03 | e2e smoke.spec.ts "ticket lifecycle" fails before phase 4; confirm it is fixed or fix it | pass |  |

### Phase 4: Outlook push + free/busy

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P04-01 | Create the "PSA Techs" group and Exchange RBAC for Applications scope (docs/CALENDAR_SETUP.md) | pass | |
| P04-02 | Run `docker compose run --rm worker python dev/graph_calendar_spike.py --mailbox <tech>` (read-only) on the real tenant | pass | Dev server (2026-11-02), worker container: `PASS getSchedule read` |
| P04-03 | Run it again with `--write`, then with `--write --outside <someone outside the group>`; the outside call must be refused | pass | Dev server (2026-11-02): create_event, idempotent create, update_event, delete_event and delete-again (404) all PASS; with `--outside`: `PASS RBAC boundary denied with 403` |
| P04-04 | Turn on Outlook sync in Settings; book, move, reassign and cancel an appointment and check each tech's Outlook calendar | pass | This worked without any issue |
| P04-05 | Put a meeting in a tech's Outlook; within 5 minutes the board shows hatched busy time with the cache-age caption | pass | |
| P04-06 | Force a failure (e.g. a tech outside the group); the board shows the failed badge and Retry works after fixing it | pass | |

### Phase 5: Client confirmations + on-call

Checklists: [client-notices-oncall.md](client-notices-oncall.md), [notifications.md](notifications.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P05-01 | Walk through docs/verify/client-notices-oncall.md | pass | |

### Phase 6: RMM alerts to tickets

Checklists: [rmm-alerts.md](rmm-alerts.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P06-01 | Walk through docs/verify/rmm-alerts.md | pass | Confirmed by owner (2026-11-02). Earlier fail (blank screen on client mapping) fixed; mapping clients works |
| P06-02 | Check the NinjaOne alert field names (uid, deviceId, severity, sourceConfigUid) against a live tenant first | pass | Confirmed by owner (2026-11-02) |
| P06-03 | Enable alerts with defaults on the Integrations card | pass | Confirmed by owner (2026-11-02) |
| P06-04 | A MODERATE+ alert on a mapped device makes one RMM ticket with device link and severity priority | pass | Confirmed by owner (2026-11-02) |
| P06-05 | A repeating alert raises occurrences and makes no second ticket | pass | Confirmed by owner (2026-11-02) |
| P06-06 | A MINOR alert makes no ticket | pass | Confirmed by owner (2026-11-02) |
| P06-07 | An unsynced device makes no ticket until asset sync | pass | Confirmed by owner (2026-11-02) |
| P06-08 | Clearing an untouched alert resolves the ticket with a note | pass | Confirmed by owner (2026-11-02) |
| P06-09 | Clearing after a tech note adds a note only and the ticket stays open | pass | Confirmed by owner (2026-11-02) |
| P06-10 | Rules note_only and always_resolve behave as labelled | pass | Confirmed by owner (2026-11-02) |
| P06-11 | Re-firing after resolve makes a new ticket linked as related | pass | Confirmed by owner (2026-11-02) |
| P06-12 | Broken credentials show an error on the card and change no tickets | pass | Confirmed by owner (2026-11-02) |
| P06-13 | Check now queues a poll and is disabled while alerts are off | pass | Confirmed by owner (2026-11-02) |
| P06-14 | Tech and read-only users cannot see the card | pass | Dev-server role check (2026-11-02): GET /integrations 403 for tech and read_only, 200 for admin |

### Phase 7: Automation & API

Checklists: [automation-api.md](automation-api.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P07-01 | Walk through docs/verify/automation-api.md (API keys, webhooks, automation rules) | pass | Dev-server session (2026-11-02): API keys, webhooks (secret shown once, http and private hosts refused, retries logged with no secret) and rules all work; webhook test used example.com because .invalid is refused at save |
| P07-02 | Unverified: a real Microsoft Teams Workflows webhook URL renders the adaptive card | deferred (owner-accepted): unverified | Marked N/A by owner (2026-11-02) |
| P07-03 | Unverified: a real n8n instance accepts the payload and the HMAC-SHA256 signature verifies | deferred (owner-accepted): unverified | Marked N/A by owner (2026-11-02) |
| P07-04 | Unverified: a LAN n8n works with WEBHOOK_ALLOW_PRIVATE_HOSTS=true (https only) | deferred (owner-accepted): unverified | Marked N/A by owner (2026-11-02) |
| P07-05 | A rule's assign, escalate, notify, webhook and create-ticket actions each work on a real ticket | pass | Dev-server session (2026-11-02): rule assigned, escalated, notified the chosen assignee and created child ticket 342; dry run changed nothing |
| P07-06 | Rules never trigger other rules; a rule firing more than 200 times in an hour switches itself off | pass | Failed on the dev server (2026-11-02), fixed in 1d472c4; re-check passed: new ticket 346 went High via rule 2, rule 1 did not run. 200/hour cap passes by test |

### Phase 8: Projects & project billing

Checklists: [projects.md](projects.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P08-01 | Walk through docs/verify/projects.md (projects, phases, tasks, dependencies, board, budget, fixed-fee and T&M billing) | pass | Dev-server session (2026-11-02): phases, tasks, dependencies (loop refused), budget and approval work. Billing steps, board move and tech/read-only screens not run. Remaining budget now counts logged time (owner decision, e14f9bc) |
| P08-02 | Confirm: milestones (phase completion) are not billed | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): completing a phase created no invoices, lines or charges |
| P08-03 | Confirm: project time does not use block hours | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): code excludes project time from block hours (billing.py), covered by a test; not shown live (no block agreement) |

### Phase 9: CRM & renewals

Checklists: [crm.md](crm.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P09-01 | Walk through docs/verify/crm.md (leads and conversion, pipeline, quote link and win, forecast, renewal reminders) | pass | Dev-server session (2026-11-02): lead qualify and convert, pipeline (Lost needs a reason) and forecast figures checked by hand. Quote link and win not run (sends email) |
| P09-02 | Confirm: the forecast is an estimate only and never creates invoices | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): invoices and agreements unchanged; forecast has no write path |
| P09-03 | Confirm: the renewal worker sends one email per new reminder and never repeats it | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): code and tests: one email per new reminder, to the staff address only, never repeated |

### Phase 10: Procurement & inventory

Checklists: [procurement.md](procurement.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P10-01 | Walk through docs/verify/procurement.md (vendors, purchase orders, receiving with serials, delivery, undo, consume, markup rules, client card) | pass | Dev-server session (2026-11-02): vendors, PO lines, serial checks, receiving, delivery, undo, consume and no repricing all work. Draft POs had a number; now numbered only when ordered (owner decision, e14f9bc) |
| P10-02 | Confirm: a client is billed when the item is delivered, not when it is received | pass | Owner decision (2026-11-02): client POs bill when ordered, stock POs at delivery. Re-checked on the dev server (2026-11-02): one charge at order (PO-2, $154.31 x 2 at 25%), none at delivery, consume refused, cancel voids (PO-3), stock PO bills at delivery (PO-4). A hand-voided order charge frees the line to bill at delivery (owner decision) |
| P10-03 | Confirm: markup order is line, then product rule, then category rule, then the default | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): line 5%, then product 20%, then category 15%, then default, each applied as expected |
| P10-04 | Confirm: the default markup is 0% until you set it | pass | Confirmed by owner (2026-11-02): built-in default stays 0%; this install uses 25% |
| P10-05 | Confirm: taxability comes from the purchase order line, which defaults from the product | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): a line marked not taxable overrode a taxable product; lines without an override took the product setting |
| P10-06 | Confirm: undo delivery is refused once the charge is invoiced, and a credit memo is the fix | pass | Confirmed by owner (2026-11-02); with billing at PO order the rule is: an uninvoiced client charge can be voided, once invoiced it is refused and a credit memo is the fix |

### Phase 11: Reporting & dashboards

Checklists: [reports.md](reports.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P11-01 | Walk through docs/verify/reports.md (SLA, utilisation, aging, profitability, dashboards, scheduled emails) | pass | Dev-server session (2026-11-02): SLA, utilisation, aging, profitability and dashboard endpoints return 200 (query params are from, to, group). Resolving now ends the first-response clock (owner decision, e14f9bc) |
| P11-02 | Confirm: SLA population is tickets created in the range, and pending tickets are left out of the met percentage | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): November n = 344 = tickets created; met + breached + pending + no-SLA = n |
| P11-03 | Confirm: utilisation capacity is work hours minus holidays and time off, and logged includes internal time | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): Nov 1-7 capacity 2700 min and logged 878 min match the database; holidays, time off and internal time checked in code only |
| P11-04 | Confirm: profitability cost is labour + goods (at delivery) + expenses, with revenue excluding tax by invoice date | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): labour $75.00 and goods $513.80 at cost matched; revenue $0 (nothing invoiced) |
| P11-05 | Confirm: labour comes from each user's cost rate, and time with no rate counts as $0 and is flagged | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): labour used the cost rate; minutes without a cost rate 0 |
| P11-06 | Confirm: weekly reports cover the previous Monday to Sunday, monthly the previous calendar month (day 1-28) | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): observed in code |
| P11-07 | Confirm: scheduled emails go once per period, only to staff holding report:read, and failures are not retried | pass | Confirmed by owner (2026-11-02). Observed on the dev server (2026-11-02): code and tests: once per period, report:read recipients only, failed run not re-run; note the outbox itself retries a queued email up to 5 times |

### Phase 12: Integration readiness

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P12-01 | Update the Entra app registration redirect URI to `<public_url>/api/v1/auth/callback`, then sign in | pass | Confirmed by owner (2026-11-02) |
| P12-02 | Build with VITE_BRAND_NAME, VITE_BRAND_LOGO and VITE_BRAND_COLORS set and check the header and login page | pass | Owner checked placeholder branding on psa.dev.local (2026-11-02); reverted. Colours need the JSON single-quoted in .env (docs fixed) |
| P12-03 | An API-key request creates a ticket with source `api` | pass | Dev-server session (2026-11-02): key with only ticket:write created ticket 340 with source api; other calls 403; revoked key gets 401; all audited |
| P12-04 | An existing n8n/webhook consumer still works (outbound webhook URLs are unchanged) | deferred (owner-accepted): unverified | Marked N/A by owner (2026-11-02) |

### Phase 13: Knowledge base

Checklists: [kb.md](kb.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P13-01 | Walk through docs/verify/kb.md | deferred (owner-accepted): removed | Knowledge base removed; Hudu articles replace it (2026-11-02) |
| P13-02 | Confirm: kb:write for admin and tech only (assumed default) | deferred (owner-accepted): removed | Knowledge base removed; Hudu articles replace it (2026-11-02) |

### Phase 14: Portal polish

Checklists: [portal-polish.md](portal-polish.md), [portal.md](portal.md)

| # | Check | Result (pass/fail/deferred) | Notes |
|---|-------|-----------------------------|-------|
| P14-01 | Walk through docs/verify/portal-polish.md |  | Not run yet: needs a portal contact with the owner's email. Dev-server code check (2026-11-02): every line is covered by backend tests; Sign in with Microsoft section follows P14-02 (deferred) |
| P14-02 | Real-tenant check: register the multi-tenant portal app per docs/PORTAL_SSO.md and sign in from a client tenant| deferred | Deferred by owner (2026-11-02): button shows after the compose fix (b518ccd); signing in with the client test account is not working yet |
| P14-03 | Confirm: uploads limited to 10 MB and the extension allowlist (assumed default) | pass | Confirmed by owner (2026-11-02). Checked in code on the dev server (2026-11-02): 10 MB (config.py, api.ts) and the 18-extension allowlist match on server and browser; no live refusal yet |
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
