# Phase 6: RMM alerts to tickets -- Context

## Phase Goal
NinjaOne alerts become deduplicated tickets linked to the device and auto-resolve when the alert clears.

## Requirements Covered
- REQ-06: RMM alerts to tickets: NinjaOne alert intake with deduplication, auto-resolve and device link.
- SC1: Alert intake creates one ticket per open condition (dedupe tested)
- SC2: Ticket links to the synced asset
- SC3: Cleared alerts auto-resolve per a configurable rule

## What Already Exists (from prior phases)
- Phase 1C integrations: integrations (MSP-level, no organization_id, no RLS, config JSONB, encrypted credentials via app/crypto.py), integration_client_maps, sync_runs; assets / asset_sources / asset_overrides are client-scoped with forced RLS (migration 0010). asset_sources maps (integration_id, external_id = NinjaOne device id) to an asset.
- app/integrations/ninjaone.py NinjaOneClient (read-only, OAuth client credentials, _get raises VendorError, never leaks secrets); app/integrations/base.py Adapter protocol, RemoteAsset, VendorError; app/integrations/registry.py build_adapter(integration).
- app/asset_sync.py sync_integration + due(); worker.py integration_jobs() pattern: new_session, set_org_scope(db,'all'), Ctx(db, user=None, scope=Scope.all()), commit per integration, catch-all log.exception; called from both branches of the main loop.
- app/ticket_services.py create_ticket(ctx, data, *, source, requester_email) and _apply_status(ctx, ticket, behavior); mail/ingest.py creates tickets as the system (actor None). Ticket.status behaviors: new, open, waiting_on_customer, resolved, closed. Priorities: lower rank = more urgent (notifications.py escalation). ck_tickets_source currently ('ui','email','portal').
- app/ticket_links.py: related/duplicate_of/parent_of links within one client.
- Tests: tests/conftest.py TABLES reset list, fixtures owner/make_user/login/admin/make_org/make_org_with_ticket; tests/vendorfakes.py FakeVendor + vendors fixture monkeypatching registry.build_adapter; tests/test_vendor_adapters.py httpx.MockTransport pattern; tests/test_zz_api_contract.py requires every route documented (summary+tags), permissioned and exercised.
- Phase 5 pattern: staff-internal tables have no organization_id and no RLS; client-owned tables get organization_id + ENABLE/FORCE RLS + org_scope policy + explicit grants + has_table_privilege tests.

## Key Design Decisions
- Owner: intake by POLLING the NinjaOne API from the worker (no inbound webhook, nothing exposed).
- Owner: clear rule default 'resolve_if_untouched' (resolve only if no assignee, no staff-authored note and no non-void time entry; otherwise add an internal note). Per-integration config alert_clear_rule in ('resolve_if_untouched','always_resolve','note_only').
- Owner: minimum severity per integration, default MODERATE. Severities ordered NONE < MINOR < MODERATE < MAJOR < CRITICAL. Priority mapping: CRITICAL -> active priority with the lowest rank, MAJOR -> second-lowest rank (or the lowest if only one exists), every other severity -> the default priority.
- Owner: while an alert's ticket is open, repeats only bump occurrences. When a new alert uid arrives for a condition whose ticket is resolved/closed, the old rmm_alert row is closed with resolution 'superseded' and a fresh ticket is created and linked 'related' to the previous ticket.
- Board quick-assess and architecture proposals: skipped by owner.
- Dedupe key: condition_key = '<deviceId>:<sourceConfigUid or sourceType or uid>'; partial unique index on (integration_id, condition_key) WHERE state='open' makes one open row (and one ticket) per condition.
- Device link: an alert whose deviceId has no asset_sources row for that integration is skipped (counted as skipped_unmapped) because the client cannot be determined; asset sync (6h) creates the source later. Every RMM ticket therefore carries asset_id.
- Clears are only judged after a fully successful list_alerts call; a VendorError changes nothing except alerts_polled_at / alerts_last_error.
- rmm_alerts is client-scoped (organization_id + forced RLS, like assets/asset_sources); composite FKs (ticket_id, organization_id) -> tickets(id, organization_id) and (asset_id, organization_id) -> assets(id, organization_id) keep rows inside one client. Grants SELECT, INSERT, UPDATE (no DELETE).
- tickets.asset_id nullable with composite FK (asset_id, organization_id) -> assets(id, organization_id) (new uq_assets_id_org); ck_tickets_source gains 'rmm'.
- Integration config keys (ninjaone only, validated): alerts_enabled bool (default false), alert_min_severity (default 'MODERATE'), alert_clear_rule (default 'resolve_if_untouched'), alert_poll_minutes int 1..60 (default 5). New integrations columns alerts_polled_at, alerts_requested_at, alerts_last_error.
- All engine writes act as the system: Ctx(user=None); audit actions rmm_alert.ticket_created, rmm_alert.repeated (only on new uid), rmm_alert.cleared, integration.alerts_failed.
- API stays under /integrations with integration:manage (admin only): GET /integrations/{id}/alerts and POST /integrations/{id}/alerts/poll (sets alerts_requested_at; worker polls on its next loop; no vendor I/O in the request).
- Retro constraints: single-wave chain (06-01 -> 06-02 -> 06-03); schema plan mirrors tenancy of comparable tables, registers new tables in tests/conftest.py TABLES, and tests every grant with has_table_privilege; all code committed with the plan (no SUMMARY-only commits).
- PRF-001: no owner manual testing until Phase 14; 06-03 appends a Phase 6 section to .planning/VERIFY.md and writes docs/verify/rmm-alerts.md.

## Plan Structure
- **Plan 06-01 (Wave 1)**: RMM alert schema, models and NinjaOne alert adapter -- Add migration 0027 (rmm_alerts, tickets.asset_id, ticket source 'rmm', integrations alert columns), the matching models, and a read-only NinjaOneClient.list_alerts() returning RemoteAlert records, with schema/privilege and adapter tests.
- **Plan 06-02 (Wave 2)**: Alert polling engine, worker job and admin API -- Poll enabled NinjaOne integrations for active alerts, create one ticket per open condition linked to the asset, bump repeats, auto-resolve or note on clear per the configured rule, and expose alert config, list and poll-now to admins.
- **Plan 06-03 (Wave 3)**: Integrations alerts panel, ticket device chip and verify docs -- Let admins configure and watch NinjaOne alert intake on the Integrations page, show the linked device on RMM tickets, and write the Phase 6 verify checklist.
