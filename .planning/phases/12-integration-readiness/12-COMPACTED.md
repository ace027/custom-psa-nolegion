---
phase: 12-integration-readiness
compacted: 2026-10-31
original_summaries: [12-01-SUMMARY.md, 12-02-SUMMARY.md, 12-03-SUMMARY.md, 12-04-SUMMARY.md]
requirements_satisfied: [REQ-14]
---

# Phase 12: Integration readiness — Compacted Summary

## Deliverables
- 12-01 Integration-readiness schema, models, schemas and writers (Complete)
- 12-02 Automation time kept out of billing; reported separately (Complete): backend/app/billing_repo.py, backend/app/projects.py, backend/app/report_metrics.py, backend/app/report_schemas.py, backend/app/reports.py, backend/tests/test_automation_time.py, docs/BILLING.md, docs/REPORTS.md
- 12-03 Frontend: branding config, client scope module, note authors and new fields (Complete): docs/DEVELOPMENT.md, frontend/src/App.tsx, frontend/src/IntegrationReadiness.test.tsx, frontend/src/api.ts, frontend/src/branding.ts, frontend/src/clientScope.ts, frontend/src/main.tsx, frontend/src/pages/Automation.tsx, frontend/src/pages/Dashboard.tsx, frontend/src/pages/Login.tsx, frontend/src/pages/OrgAssetsCard.tsx, frontend/src/pages/OrgBillingCard.tsx, frontend/src/pages/OrganizationDetail.tsx, frontend/src/pages/Organizations.tsx, frontend/src/pages/ProjectDetail.tsx, frontend/src/pages/Search.tsx, frontend/src/pages/TicketDetail.tsx, frontend/src/pages/WarrantyReport.tsx, frontend/src/pages/billing/StatementActions.tsx, frontend/src/pages/crm/Leads.tsx, frontend/src/pages/crm/OpportunityPage.tsx, frontend/src/pages/crm/Renewals.tsx, frontend/src/pages/procurement/Inventory.tsx, frontend/src/pages/procurement/PurchaseOrderPage.tsx, frontend/src/pages/quotes/QuotesList.tsx, frontend/src/pages/quotes/SurveyPage.tsx, frontend/src/pages/reports/UtilisationReport.tsx, frontend/src/vite-env.d.ts
- 12-04 /api/v1 everywhere and the committed OpenAPI spec (Complete): backend/app/main.py, backend/app/openapi_export.py, backend/app/routers/auth.py, backend/tests/conftest.py, backend/tests/test_api_keys.py, backend/tests/test_api_v1_and_openapi.py, backend/tests/test_asset_sync.py, backend/tests/test_assets_api.py, backend/tests/test_audit.py, backend/tests/test_auth.py, backend/tests/test_automation_api.py, backend/tests/test_automation_time.py, backend/tests/test_billing_config.py, backend/tests/test_billing_db_guards.py, backend/tests/test_billing_permissions_audit.py, backend/tests/test_billing_runs.py, backend/tests/test_block_agreements.py, backend/tests/test_block_billing.py, backend/tests/test_calendar_sync.py, backend/tests/test_calendar_sync_api.py, backend/tests/test_client_notices.py, backend/tests/test_config.py, backend/tests/test_credit_memos.py, backend/tests/test_crm_api.py, backend/tests/test_csat.py, backend/tests/test_dashboards.py, backend/tests/test_expenses.py, backend/tests/test_integrations.py, backend/tests/test_invoice_emails.py, backend/tests/test_invoicing.py, backend/tests/test_isolation.py, backend/tests/test_late_fees.py, backend/tests/test_mail_ingest.py, backend/tests/test_notice_permissions_audit.py, backend/tests/test_notices.py, backend/tests/test_notifications.py, backend/tests/test_oncall_api.py, backend/tests/test_organizations.py, backend/tests/test_payment_db_guards.py, backend/tests/test_payment_permissions_audit.py, backend/tests/test_payments.py, backend/tests/test_permissions.py, backend/tests/test_portal.py, backend/tests/test_portal_appointments.py, backend/tests/test_procurement.py, backend/tests/test_project_billing.py, backend/tests/test_projects.py, backend/tests/test_projects_api.py, backend/tests/test_proration.py, backend/tests/test_quoting.py, backend/tests/test_report_metrics.py, backend/tests/test_report_schedules.py, backend/tests/test_reports.py, backend/tests/test_reports_api.py, backend/tests/test_rmm_alerts.py, backend/tests/test_rmm_alerts_api.py, backend/tests/test_scheduling_api.py, backend/tests/test_sites_contacts.py, backend/tests/test_statements.py, backend/tests/test_ticket_links.py, backend/tests/test_ticket_statuses.py, backend/tests/test_ticket_types_fields.py, backend/tests/test_tickets_phase1a.py, backend/tests/test_tickets_phase1b.py, backend/tests/test_timekeeping.py, backend/tests/test_timesheet_approval.py, backend/tests/test_triage_attachments.py, backend/tests/test_users.py, backend/tests/test_webhooks_api.py, backend/tests/test_zz_api_contract.py, docs/API.md, docs/API_KEYS.md, docs/AUTOMATION.md, docs/DEVELOPMENT.md, docs/ENTRA_SETUP.md, docs/PORTAL.md, docs/SCHEDULING.md, docs/api/openapi.json, docs/verify/automation-api.md, docs/verify/dispatch-board.md, docs/verify/phase-1.md, docs/verify/portal.md, docs/verify/reports.md, docs/verify/tickets-phase1c.md, docs/verify/time-phase2a.md, frontend/e2e/dispatch.spec.ts, frontend/src/ApiKeys.test.tsx, frontend/src/App.test.tsx, frontend/src/Automation.test.tsx, frontend/src/Billing.test.tsx, frontend/src/Block.test.tsx, frontend/src/Crm.test.tsx, frontend/src/Dashboards.test.tsx, frontend/src/Dispatch.test.tsx, frontend/src/Integrations.test.tsx, frontend/src/OnCall.test.tsx, frontend/src/OutlookSync.test.tsx, frontend/src/Payments.test.tsx, frontend/src/Phase1A.test.tsx, frontend/src/Phase1C.test.tsx, frontend/src/Phase2A.test.tsx, frontend/src/Phase3A.test.tsx, frontend/src/Phase3B.test.tsx, frontend/src/Phase3C.test.tsx, frontend/src/Portal.test.tsx, frontend/src/PortalAppointments.test.tsx, frontend/src/Procurement.test.tsx, frontend/src/Profile.test.tsx, frontend/src/Projects.test.tsx, frontend/src/Quotes.test.tsx, frontend/src/Reminders.test.tsx, frontend/src/Reports.test.tsx, frontend/src/RmmAlerts.test.tsx, frontend/src/TicketAppointments.test.tsx, frontend/src/Tickets.test.tsx, frontend/src/Webhooks.test.tsx, frontend/src/api.test.ts, frontend/src/api.ts, frontend/src/pages/Expenses.tsx, frontend/src/pages/Login.tsx, frontend/src/pages/TicketDetail.tsx, frontend/src/pages/Timesheet.tsx, frontend/src/pages/WarrantyReport.tsx, frontend/src/pages/billing/Invoices.tsx, frontend/src/pages/billing/Reports.tsx, frontend/src/pages/billing/StatementActions.tsx, frontend/src/pages/quotes/QuotePage.tsx, frontend/src/portal/PortalApp.tsx

## Decisions
- 12-01: Ticket source CHECK also keeps 'project' (set by app/projects.py since migration 0029) beside the six owner-approved values. The plan's list would have broken p
- 12-01: Asset backfill: any asset with a source row becomes 'import', then any with a NinjaOne (kind 'ninjaone') source becomes 'rmm', so NinjaOne wins.
- 12-01: Rule conditions are rewritten in Python, handling both a single value and a list value, in both directions.
- 12-02: Besides the three query filters you named, I added the labour filter to the project budget query (`projects.py`) and the unbilled report (`reports.unbilled`). B
- 12-02: Users with only automation minutes appear in the utilisation rows.
- 12-02: Internal time still counts in logged minutes, as before.
- 12-03: AI notes use the existing violet-100 and violet-800 tokens, which have dark-mode overrides. System notes use slate-100 and slate-200.
- 12-03: NotesCard is exported from `TicketDetail.tsx` so the tests can render it.
- 12-03: The Automation column in the utilisation totals row is the sum of the row values, because the totals type has no `automation_minutes`.
- 12-04: The ticket source test asserts that the six required values are a subset of the enum, because the enum also has `project`.
- 12-04: The asset source enum is compared as a sorted list, since the spec orders it manual, rmm, import.
- 12-04: I left `Caddyfile` and `vite.config.ts` unchanged, as the plan allowed (`handle /api/*` and the `/api` proxy already cover `/api/v1`).

## Conventions and Open Questions
- 12-01 convention: Next wave can rely on /api responses carrying uuid on organizations, sites and contacts, and rmm_client_id on organizations.
- 12-01 convention: Next wave can rely on source and external_id on assets, and source and external_ref on tickets.
- 12-01 convention: Next wave can rely on author_type on notes, entry_type on time entries, and entra_tenant_id on users.
- 12-02 convention: Utilisation API rows and totals now carry `automation_minutes` (int), and the CSV's last column is `automation_minutes`. The frontend can show it.
- 12-03 convention: Call clientApiPath or clientRoute for any new client-scoped path or link. A literal `organizations/${` outside `clientScope.ts` and tests fails the grep gate.
- 12-03 convention: `automation_minutes` is required on utilisation rows, so the backend must send it.
- 12-04 convention: Regenerate the spec with `python -m app.openapi_export` after any API change. The freshness test fails otherwise.
- 12-04 convention: New frontend paths go through `api()`, which adds `/api/v1`. Hand-built links such as CSV downloads must use `/api/v1` explicitly.

## Files Modified
| File | Change |
|------|--------|
| `backend/app/billing_repo.py` | 12-02: Automation time kept out of billing; reported separately |
| `backend/app/projects.py` | 12-02: Automation time kept out of billing; reported separately |
| `backend/app/report_metrics.py` | 12-02: Automation time kept out of billing; reported separately |
| `backend/app/report_schemas.py` | 12-02: Automation time kept out of billing; reported separately |
| `backend/app/reports.py` | 12-02: Automation time kept out of billing; reported separately |
| `backend/tests/test_automation_time.py` | 12-02: Automation time kept out of billing; reported separately |
| `docs/BILLING.md` | 12-02: Automation time kept out of billing; reported separately |
| `docs/REPORTS.md` | 12-02: Automation time kept out of billing; reported separately |
| `docs/DEVELOPMENT.md` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/App.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/IntegrationReadiness.test.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/api.ts` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/branding.ts` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/clientScope.ts` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/main.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/Automation.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/Dashboard.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/Login.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/OrgAssetsCard.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/OrgBillingCard.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/OrganizationDetail.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/Organizations.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/ProjectDetail.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/Search.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/TicketDetail.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/WarrantyReport.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/billing/StatementActions.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/crm/Leads.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/crm/OpportunityPage.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/crm/Renewals.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/procurement/Inventory.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/procurement/PurchaseOrderPage.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/quotes/QuotesList.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/quotes/SurveyPage.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/pages/reports/UtilisationReport.tsx` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `frontend/src/vite-env.d.ts` | 12-03: Frontend: branding config, client scope module, note authors and new fields |
| `backend/app/main.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/app/openapi_export.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/app/routers/auth.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/conftest.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_api_keys.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_api_v1_and_openapi.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_asset_sync.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_assets_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_audit.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_auth.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_automation_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_automation_time.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_billing_config.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_billing_db_guards.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_billing_permissions_audit.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_billing_runs.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_block_agreements.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_block_billing.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_calendar_sync.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_calendar_sync_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_client_notices.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_config.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_credit_memos.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_crm_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_csat.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_dashboards.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_expenses.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_integrations.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_invoice_emails.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_invoicing.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_isolation.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_late_fees.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_mail_ingest.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_notice_permissions_audit.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_notices.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_notifications.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_oncall_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_organizations.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_payment_db_guards.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_payment_permissions_audit.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_payments.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_permissions.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_portal.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_portal_appointments.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_procurement.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_project_billing.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_projects.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_projects_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_proration.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_quoting.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_report_metrics.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_report_schedules.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_reports.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_reports_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_rmm_alerts.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_rmm_alerts_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_scheduling_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_sites_contacts.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_statements.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_ticket_links.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_ticket_statuses.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_ticket_types_fields.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_tickets_phase1a.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_tickets_phase1b.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_timekeeping.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_timesheet_approval.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_triage_attachments.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_users.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_webhooks_api.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `backend/tests/test_zz_api_contract.py` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/API.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/API_KEYS.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/AUTOMATION.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/DEVELOPMENT.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/ENTRA_SETUP.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/PORTAL.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/SCHEDULING.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/api/openapi.json` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/automation-api.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/dispatch-board.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/phase-1.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/portal.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/reports.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/tickets-phase1c.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `docs/verify/time-phase2a.md` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/e2e/dispatch.spec.ts` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/ApiKeys.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/App.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Automation.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Billing.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Block.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Crm.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Dashboards.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Dispatch.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Integrations.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/OnCall.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/OutlookSync.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Payments.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase1A.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase1C.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase2A.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase3A.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase3B.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Phase3C.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Portal.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/PortalAppointments.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Procurement.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Profile.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Projects.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Quotes.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Reminders.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Reports.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/RmmAlerts.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/TicketAppointments.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Tickets.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/Webhooks.test.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/api.test.ts` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/api.ts` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/Expenses.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/Login.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/TicketDetail.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/Timesheet.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/WarrantyReport.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/billing/Invoices.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/billing/Reports.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/billing/StatementActions.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/pages/quotes/QuotePage.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |
| `frontend/src/portal/PortalApp.tsx` | 12-04: /api/v1 everywhere and the committed OpenAPI spec |

## Verification
- 12-01 (REQ-14): 7/7 verification commands passed
- 12-02 (REQ-14): 8/8 verification commands passed
- 12-03 (REQ-14): 5/5 verification commands passed
- 12-04 (REQ-14): 8/8 verification commands passed

## Agents
- 12-01: engineering-backend-architect
- 12-02: engineering-senior-developer
- 12-03: engineering-frontend-developer
- 12-04: engineering-senior-developer

## Also Covered
- backend/alembic/versions/0033_integration_readiness.py
- backend/app/models.py
- backend/app/schemas.py
- backend/app/asset_schemas.py
- backend/app/ticket_services.py
- backend/app/ticket_views.py
- backend/app/ticket_links.py
- backend/app/automation.py
- backend/app/asset_sync.py
- backend/app/assets.py
- backend/app/auth/oidc.py
- backend/app/timekeeping.py
- backend/app/repositories.py
- backend/app/services.py
- backend/app/routers/tickets.py
- backend/app/routers/organizations.py
- backend/app/routers/timekeeping.py
- backend/app/routers/assets.py
- backend/app/routers/users.py
- docs/INTEGRATIONS.md
- backend/app/billing.py
- backend/app/dashboards.py
- frontend/index.html
- .planning/VERIFY.md
- deploy/Caddyfile
- frontend/vite.config.ts
