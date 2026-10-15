# Phase 4: Outlook push + free/busy -- Context

## Phase Goal
Appointments appear in each tech's Outlook calendar via a worker outbox, and Outlook busy time shows on the dispatch board.

## Requirements Covered
- REQ-04: Outlook one-way push: worker-only idempotent outbox pushing appointments to each tech's Outlook calendar, getSchedule free/busy cache shown on the board, failed-sync visibility; the API never calls Graph.

## What Already Exists (from prior phases)
- backend/app/mail/graph.py: GraphClient (httpx, app-only client credentials, bound to one mailbox via _request -> /users/{mailbox}{path}; raises GraphError with no status or retry info)
- backend/dev/fake_graph.py: stdlib HTTPServer fake of the Graph mail endpoints for local runs (in-memory state, /_inject and /_sent control endpoints)
- backend/tests/test_graph_client.py: tests GraphClient with httpx.MockTransport
- backend/app/worker.py: main loop runs run_cycle (mail, only when mail is configured), billing_jobs, notify_jobs, integration_jobs; each job opens dbmod.new_session and calls set_org_scope(db, 'all')
- Mail outbox pattern: email_messages with send_status/send_attempts, mail/ingest.py send_pending claims with FOR UPDATE SKIP LOCKED, batch 20, MAX_SEND_ATTEMPTS=5, no backoff; visibility only as counts at GET /api/mail/status
- Phase 2 scheduling: appointments table (organization_id, ticket_id, tech_id, starts_at, ends_at, status scheduled|cancelled, notes, client_visible), RLS org_scope, services in backend/app/scheduling.py (create_appointment, update_appointment, cancel_appointment with row locks), audit.record on writes, migration 0024_scheduling (head)
- Phase 3: dispatch board frontend/src/pages/Dispatch.tsx (react-big-calendar), frontend/src/scheduling/api.ts (AvailabilityRow {working,time_off,time_off_pending,appointments,free}), frontend/src/scheduling/board.ts backgroundBlocks(), scripts/e2e.sh runs Playwright specs on an isolated DB
- Single-row settings table (models.py Settings) exposed at GET/PATCH /api/settings; Settings.public_url builds ticket links (notifications.py:38)
- User.email is the only mailbox field on users

## Key Design Decisions
- Owner approved Application Calendars.ReadWrite scoped with Exchange RBAC for Applications to a 'PSA Techs' mail-enabled security group; no Entra Graph API permission is added. The mail app registration is reused.
- Only the worker calls Graph. The API reads only the outbox state and the busy cache tables.
- Outlook sync is behind settings.outlook_sync_enabled (default false). Appointment writes always enqueue; the worker does nothing for calendars while the setting is off.
- Event payload (owner decision): subject 'PSA #<ticket id> appointment', body a plain link '<public_url>/tickets/<ticket id>', sensitivity 'private', showAs 'busy', start/end in UTC, no client name, ticket subject, notes or address.
- The Graph user id for a tech is User.email.
- Idempotency: creates send transactionId 'psa-appt-<appointment id>-<tech id>-<sync generation>', so a retried create cannot duplicate the event; updates PATCH the stored graph_event_id; a 404 on PATCH recreates; a 404 on DELETE counts as success.
- Reassign: when an appointment's tech changes, the worker deletes the event from the old tech's calendar, then creates it in the new tech's.
- Retry: transient errors (network, 429, 5xx) back off min(2^attempts, 60) minutes and fail after 6 attempts; permanent errors (400, 401, 403, and 404 on create) fail at once. Failed rows keep last_error (truncated to 500 chars) and can be retried by schedule:write users.
- Free/busy: the worker polls getSchedule every 5 minutes for active users holding schedule:write, window now-1 day to now+14 days, interval 15 minutes, batches of 20 schedules called from the batch's first mailbox; results replace that user's busy_blocks rows. No subject text is stored.
- The board hides an Outlook busy block that exactly matches a synced PSA appointment for the same tech (same start and end), so pushed bookings are not shown twice.
- Staleness: the board shows the busy cache age; a fetch older than 15 minutes shows a stale warning.
- The real-tenant spike is run by the owner with backend/dev/graph_calendar_spike.py after 04-01; the roadmap criterion 'spike verified on a real tenant' stays open until the owner reports the result. Everything else is tested against fakes.
- Retro constraints (phase 3): plans using react-big-calendar verify against the real Vite dev server through scripts/e2e.sh; plans touching e2e list scripts/e2e.sh and the files a fix may need; the build commit must contain the plan's files.
- Board quick-assess recommendations adopted: spike first, per-appointment sync badge with retry, cache age and a distinct Outlook busy style on the board, docs stating the one-way limits and the 5-minute refresh.

## Plan Structure
- **Plan 04-01 (Wave 1)**: Graph calendar client, fake Graph calendar endpoints and the tenant spike script -- Give the Graph client calendar event and getSchedule calls with error classification, extend the dev fake Graph with the same endpoints, and add a spike script the owner runs against the real tenant.
- **Plan 04-02 (Wave 2)**: Sync schema, outbox enqueue and the worker push job -- Add the appointment_sync outbox, the busy cache tables and the outlook_sync_enabled setting, enqueue a sync on every appointment write, and push pending rows to Outlook from a worker job with idempotent retries.
- **Plan 04-03 (Wave 3)**: Free/busy cache job and the sync status, retry and availability API -- Poll getSchedule into the busy cache from the worker, and expose busy blocks, cache age, per-appointment sync state, a sync status summary and a retry action through the API.
- **Plan 04-04 (Wave 4)**: Board Outlook busy shading, sync badges, settings card and setup docs -- Show Outlook busy time in its own style with the cache age on the dispatch board, a sync badge with retry on each appointment, an Outlook sync card in Settings, and the calendar setup docs.
