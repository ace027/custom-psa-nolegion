# Plan 12-04 Summary: /api/v1 everywhere and the committed OpenAPI spec

## Result
**Status**: Complete
**Wave**: 3
**Agent**: engineering-senior-developer
**Completed**: 2026-10-31

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-senior-developer | — | 22 | 2.83 | 24.83 | heuristic |
| testing-api-tester | — | 21 | 0 | 21 | heuristic |
| engineering-backend-architect | — | 17 | 2.8 | 19.8 | heuristic |

- **Task type detected**: implementation
- **Confidence**: HIGH
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Move to /api/v1 (done)
- [x] Task 2: OpenAPI export and tests (done)
- [x] Task 3: Docs and owner checks (done)

## Files Modified
- `backend/app/main.py`
- `backend/app/openapi_export.py`
- `backend/app/routers/auth.py`
- `backend/tests/conftest.py`
- `backend/tests/test_api_keys.py`
- `backend/tests/test_api_v1_and_openapi.py`
- `backend/tests/test_asset_sync.py`
- `backend/tests/test_assets_api.py`
- `backend/tests/test_audit.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_automation_api.py`
- `backend/tests/test_automation_time.py`
- `backend/tests/test_billing_config.py`
- `backend/tests/test_billing_db_guards.py`
- `backend/tests/test_billing_permissions_audit.py`
- `backend/tests/test_billing_runs.py`
- `backend/tests/test_block_agreements.py`
- `backend/tests/test_block_billing.py`
- `backend/tests/test_calendar_sync.py`
- `backend/tests/test_calendar_sync_api.py`
- `backend/tests/test_client_notices.py`
- `backend/tests/test_config.py`
- `backend/tests/test_credit_memos.py`
- `backend/tests/test_crm_api.py`
- `backend/tests/test_csat.py`
- `backend/tests/test_dashboards.py`
- `backend/tests/test_expenses.py`
- `backend/tests/test_integrations.py`
- `backend/tests/test_invoice_emails.py`
- `backend/tests/test_invoicing.py`
- `backend/tests/test_isolation.py`
- `backend/tests/test_late_fees.py`
- `backend/tests/test_mail_ingest.py`
- `backend/tests/test_notice_permissions_audit.py`
- `backend/tests/test_notices.py`
- `backend/tests/test_notifications.py`
- `backend/tests/test_oncall_api.py`
- `backend/tests/test_organizations.py`
- `backend/tests/test_payment_db_guards.py`
- `backend/tests/test_payment_permissions_audit.py`
- `backend/tests/test_payments.py`
- `backend/tests/test_permissions.py`
- `backend/tests/test_portal.py`
- `backend/tests/test_portal_appointments.py`
- `backend/tests/test_procurement.py`
- `backend/tests/test_project_billing.py`
- `backend/tests/test_projects.py`
- `backend/tests/test_projects_api.py`
- `backend/tests/test_proration.py`
- `backend/tests/test_quoting.py`
- `backend/tests/test_report_metrics.py`
- `backend/tests/test_report_schedules.py`
- `backend/tests/test_reports.py`
- `backend/tests/test_reports_api.py`
- `backend/tests/test_rmm_alerts.py`
- `backend/tests/test_rmm_alerts_api.py`
- `backend/tests/test_scheduling_api.py`
- `backend/tests/test_sites_contacts.py`
- `backend/tests/test_statements.py`
- `backend/tests/test_ticket_links.py`
- `backend/tests/test_ticket_statuses.py`
- `backend/tests/test_ticket_types_fields.py`
- `backend/tests/test_tickets_phase1a.py`
- `backend/tests/test_tickets_phase1b.py`
- `backend/tests/test_timekeeping.py`
- `backend/tests/test_timesheet_approval.py`
- `backend/tests/test_triage_attachments.py`
- `backend/tests/test_users.py`
- `backend/tests/test_webhooks_api.py`
- `backend/tests/test_zz_api_contract.py`
- `docs/API.md`
- `docs/API_KEYS.md`
- `docs/AUTOMATION.md`
- `docs/DEVELOPMENT.md`
- `docs/ENTRA_SETUP.md`
- `docs/PORTAL.md`
- `docs/SCHEDULING.md`
- `docs/api/openapi.json`
- `docs/verify/automation-api.md`
- `docs/verify/dispatch-board.md`
- `docs/verify/phase-1.md`
- `docs/verify/portal.md`
- `docs/verify/reports.md`
- `docs/verify/tickets-phase1c.md`
- `docs/verify/time-phase2a.md`
- `frontend/e2e/dispatch.spec.ts`
- `frontend/src/ApiKeys.test.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/Automation.test.tsx`
- `frontend/src/Billing.test.tsx`
- `frontend/src/Block.test.tsx`
- `frontend/src/Crm.test.tsx`
- `frontend/src/Dashboards.test.tsx`
- `frontend/src/Dispatch.test.tsx`
- `frontend/src/Integrations.test.tsx`
- `frontend/src/OnCall.test.tsx`
- `frontend/src/OutlookSync.test.tsx`
- `frontend/src/Payments.test.tsx`
- `frontend/src/Phase1A.test.tsx`
- `frontend/src/Phase1C.test.tsx`
- `frontend/src/Phase2A.test.tsx`
- `frontend/src/Phase3A.test.tsx`
- `frontend/src/Phase3B.test.tsx`
- `frontend/src/Phase3C.test.tsx`
- `frontend/src/Portal.test.tsx`
- `frontend/src/PortalAppointments.test.tsx`
- `frontend/src/Procurement.test.tsx`
- `frontend/src/Profile.test.tsx`
- `frontend/src/Projects.test.tsx`
- `frontend/src/Quotes.test.tsx`
- `frontend/src/Reminders.test.tsx`
- `frontend/src/Reports.test.tsx`
- `frontend/src/RmmAlerts.test.tsx`
- `frontend/src/TicketAppointments.test.tsx`
- `frontend/src/Tickets.test.tsx`
- `frontend/src/Webhooks.test.tsx`
- `frontend/src/api.test.ts`
- `frontend/src/api.ts`
- `frontend/src/pages/Expenses.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/TicketDetail.tsx`
- `frontend/src/pages/Timesheet.tsx`
- `frontend/src/pages/WarrantyReport.tsx`
- `frontend/src/pages/billing/Invoices.tsx`
- `frontend/src/pages/billing/Reports.tsx`
- `frontend/src/pages/billing/StatementActions.tsx`
- `frontend/src/pages/quotes/QuotePage.tsx`
- `frontend/src/portal/PortalApp.tsx`

## Verification Results
8/8 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `service postgresql start >/dev/null 2>&1; cd backend && ruff check app tests && ruff format --check app tests` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m app.openapi_export --check` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && timeout 2700 python -m pytest -q -p no:logging` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run && npm run build` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m pytest -q -x tests/test_zz_api_contract.py tests/test_tickets.py tests/test_auth.py` | 0 | PASS |
| `cd frontend && npm run typecheck && npx vitest run` | 0 | PASS |
| `service postgresql start >/dev/null 2>&1; cd backend && python -m app.openapi_export --check && python -m pytest -q tests/test_api_v1_and_openapi.py` | 0 | PASS |
| `grep -q '/api/v1' docs/API.md && grep -q 'Phase 12' .planning/VERIFY.md && grep -q 'api/v1/auth/callback' docs/ENTRA_SETUP.md` | 0 | PASS |

## Key Decisions
- The ticket source test asserts that the six required values are a subset of the enum, because the enum also has `project`.
- The asset source enum is compared as a sorted list, since the spec orders it manual, rmm, import.
- I left `Caddyfile` and `vite.config.ts` unchanged, as the plan allowed (`handle /api/*` and the `/api` proxy already cover `/api/v1`).

## Issues Encountered
- The first rewrite also changed TS import specifiers to `../api/v1`. I fixed them, and the frontend typecheck, vitest and build are green afterwards.
- I did not rerun the backend suite after the frontend import fix, because that fix touched no backend files. The backend `--check` still passes.

## Escalations
(none)

## Handoff Context
- **Key outputs**: backend/app/main.py; backend/app/openapi_export.py; backend/app/routers/auth.py; backend/tests/conftest.py; backend/tests/test_api_keys.py; backend/tests/test_api_v1_and_openapi.py; backend/tests/test_asset_sync.py; backend/tests/test_assets_api.py; backend/tests/test_audit.py; backend/tests/test_auth.py; backend/tests/test_automation_api.py; backend/tests/test_automation_time.py; backend/tests/test_billing_config.py; backend/tests/test_billing_db_guards.py; backend/tests/test_billing_permissions_audit.py; backend/tests/test_billing_runs.py; backend/tests/test_block_agreements.py; backend/tests/test_block_billing.py; backend/tests/test_calendar_sync.py; backend/tests/test_calendar_sync_api.py; backend/tests/test_client_notices.py; backend/tests/test_config.py; backend/tests/test_credit_memos.py; backend/tests/test_crm_api.py; backend/tests/test_csat.py; backend/tests/test_dashboards.py; backend/tests/test_expenses.py; backend/tests/test_integrations.py; backend/tests/test_invoice_emails.py; backend/tests/test_invoicing.py; backend/tests/test_isolation.py; backend/tests/test_late_fees.py; backend/tests/test_mail_ingest.py; backend/tests/test_notice_permissions_audit.py; backend/tests/test_notices.py; backend/tests/test_notifications.py; backend/tests/test_oncall_api.py; backend/tests/test_organizations.py; backend/tests/test_payment_db_guards.py; backend/tests/test_payment_permissions_audit.py; backend/tests/test_payments.py; backend/tests/test_permissions.py; backend/tests/test_portal.py; backend/tests/test_portal_appointments.py; backend/tests/test_procurement.py; backend/tests/test_project_billing.py; backend/tests/test_projects.py; backend/tests/test_projects_api.py; backend/tests/test_proration.py; backend/tests/test_quoting.py; backend/tests/test_report_metrics.py; backend/tests/test_report_schedules.py; backend/tests/test_reports.py; backend/tests/test_reports_api.py; backend/tests/test_rmm_alerts.py; backend/tests/test_rmm_alerts_api.py; backend/tests/test_scheduling_api.py; backend/tests/test_sites_contacts.py; backend/tests/test_statements.py; backend/tests/test_ticket_links.py; backend/tests/test_ticket_statuses.py; backend/tests/test_ticket_types_fields.py; backend/tests/test_tickets_phase1a.py; backend/tests/test_tickets_phase1b.py; backend/tests/test_timekeeping.py; backend/tests/test_timesheet_approval.py; backend/tests/test_triage_attachments.py; backend/tests/test_users.py; backend/tests/test_webhooks_api.py; backend/tests/test_zz_api_contract.py; docs/API.md; docs/API_KEYS.md; docs/AUTOMATION.md; docs/DEVELOPMENT.md; docs/ENTRA_SETUP.md; docs/PORTAL.md; docs/SCHEDULING.md; docs/api/openapi.json; docs/verify/automation-api.md; docs/verify/dispatch-board.md; docs/verify/phase-1.md; docs/verify/portal.md; docs/verify/reports.md; docs/verify/tickets-phase1c.md; docs/verify/time-phase2a.md; frontend/e2e/dispatch.spec.ts; frontend/src/ApiKeys.test.tsx; frontend/src/App.test.tsx; frontend/src/Automation.test.tsx; frontend/src/Billing.test.tsx; frontend/src/Block.test.tsx; frontend/src/Crm.test.tsx; frontend/src/Dashboards.test.tsx; frontend/src/Dispatch.test.tsx; frontend/src/Integrations.test.tsx; frontend/src/OnCall.test.tsx; frontend/src/OutlookSync.test.tsx; frontend/src/Payments.test.tsx; frontend/src/Phase1A.test.tsx; frontend/src/Phase1C.test.tsx; frontend/src/Phase2A.test.tsx; frontend/src/Phase3A.test.tsx; frontend/src/Phase3B.test.tsx; frontend/src/Phase3C.test.tsx; frontend/src/Portal.test.tsx; frontend/src/PortalAppointments.test.tsx; frontend/src/Procurement.test.tsx; frontend/src/Profile.test.tsx; frontend/src/Projects.test.tsx; frontend/src/Quotes.test.tsx; frontend/src/Reminders.test.tsx; frontend/src/Reports.test.tsx; frontend/src/RmmAlerts.test.tsx; frontend/src/TicketAppointments.test.tsx; frontend/src/Tickets.test.tsx; frontend/src/Webhooks.test.tsx; frontend/src/api.test.ts; frontend/src/api.ts; frontend/src/pages/Expenses.tsx; frontend/src/pages/Login.tsx; frontend/src/pages/TicketDetail.tsx; frontend/src/pages/Timesheet.tsx; frontend/src/pages/WarrantyReport.tsx; frontend/src/pages/billing/Invoices.tsx; frontend/src/pages/billing/Reports.tsx; frontend/src/pages/billing/StatementActions.tsx; frontend/src/pages/quotes/QuotePage.tsx; frontend/src/portal/PortalApp.tsx
- **Decisions made**: The ticket source test asserts that the six required values are a subset of the enum, because the enum also has `project`.; The asset source enum is compared as a sorted list, since the spec orders it manual, rmm, import.; I left `Caddyfile` and `vite.config.ts` unchanged, as the plan allowed (`handle /api/*` and the `/api` proxy already cover `/api/v1`).
- **Open questions**: (none)
- **Conventions established**: Regenerate the spec with `python -m app.openapi_export` after any API change. The freshness test fails otherwise.; New frontend paths go through `api()`, which adds `/api/v1`. Hand-built links such as CSV downloads must use `/api/v1` explicitly.

## Requirements Covered
- REQ-14

## Token Usage
20 requests, 634666 input tokens (523499 cached), 9399 output tokens, $0.4766
