# Integration readiness (Phase 12): design and decisions

Owner request (2026-10-30): before first release, add small forward-compatible hooks for the future
custom RMM (Rust backend) and vCISO module, which will share this app's React 19 / TypeScript shell.
No integration is built now. Out of scope: webhook intake, the RMM connector, a NinjaOne inbound
adapter, a monorepo restructure, a Client 360 page, unified search, an AI assistant.

## Mapping onto what exists (survey of 2026-10-30, head migration 0032)

| # | Item | Exists | Plan |
|---|------|--------|------|
| 1 | UUIDs | organizations, sites, contacts have BigInteger identity PKs; no uuid columns | `uuid` column, default `gen_random_uuid()` (core in PG 13+, no pgcrypto), backfilled, then NOT NULL + unique. Every response carries `uuid`; integer `id` and routes stay |
| 2a | organizations.rmm_client_id | none (NinjaOne maps via integration_client_maps.external_id) | nullable UUID, unique |
| 2b | asset source/external_id | `assets` (0010) exists; vendor ids in asset_sources (uq integration_id, external_id) | `assets.source` manual/rmm/import (default manual; existing synced assets = rmm), `external_id`, unique (source, external_id) where external_id is not null. No configuration_items table |
| 3 | tickets.source / external_ref | source String(10) CHECK ui/email/portal/rmm/rule; set in ticket_services.py, portal.py, rmm_alerts.py, automation.py | values manual/email/portal/rmm/api/rule; data migration ui -> manual; API-key-created tickets -> api; `external_ref` unique (source, external_ref) where not null |
| 4 | ticket_notes.author_type | author_user_id; system notes via ticket_services.system_note (author NULL); NotesCard in TicketDetail.tsx has no filter | author_type human/system/ai, backfill NULL author -> system, else human; system_note writes system; distinct styling and an All/Human/System/AI filter |
| 5 | automation time | time_entries.billable, work_type_id; billing picks billable, unvoided, uninvoiced (billing_repo.py); reports sum minutes_actual | `entry_type` labour/automation; CHECK automation => billable = false (billing then never selects it); utilisation/time reports show automation minutes as their own column, excluded from utilisation % and profitability labour cost |
| 6a | /v1 | all routers under /api (main.py); frontend base in api.ts; Caddyfile and vite proxy forward /api | every route under /api/v1, no alias; update api.ts, tests, e2e, Caddyfile/vite if needed, docs, OIDC redirect URI default and docs |
| 6b | OpenAPI | FastAPI serves /api/openapi.json; nothing committed | export script, committed openapi.json (repo root or docs/api/), test that fails when stale |
| 7 | Entra ids | users.entra_oid (unique) bound at first login; tid checked against settings, not stored | users.entra_tenant_id set at login with entra_oid. Phase 14 (portal Entra SSO for contacts) reuses the same oid + tenant pair |
| 8a | white-label | "PSA" hard-coded in index.html, App.tsx, Login.tsx; logo is a text tile | one `branding.ts` (name, logo, colours), optional VITE_ env override at build time |
| 8b | design tokens | done: index.css @theme; no hex colours in .tsx | nothing |
| 8c | client scope | one api() helper, but 18 files build organizations/${id} paths | a `useClientScope` hook/module that those files use |

## Owner decisions (2026-10-30)
- Run as its own phase inserted before the knowledge base (renumbered 13-15).
- Ticket sources: manual, email, portal, rmm, api, rule.
- /api/v1 only, no /api alias (pre-release); owner updates the Entra app registration redirect URI.
- Automation minutes: separate column in reports, outside utilisation % and labour cost.

## Constraints for planning
- New columns on RLS tables need no policy change, but check test_isolation, test_backup_restore and test_zz_api_contract.
- Migrations reversible; run on a seeded copy (scripts/seed) before and after; downgrade restores ui as a ticket source.
- Money and RLS parts stay on the main model (CLAUDE.md).
