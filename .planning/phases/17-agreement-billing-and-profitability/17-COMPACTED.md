---
phase: 17-agreement-billing-and-profitability
compacted: 2026-11-03
original_summaries: [17-01-SUMMARY.md, 17-02-SUMMARY.md, 17-03-SUMMARY.md, 17-04-SUMMARY.md]
requirements_satisfied: [Owner test note 8, P01-01 note, Block-hour rollover configurable, Profitability and utilisation by agreement, Profitability by agreement]
---

# Phase 17: Agreement billing and profitability — Compacted Summary

## Deliverables
- 17-01 Agreement on tickets and time entries (Complete with Warnings): backend/alembic/versions/0041_agreement_attachment_and_rollover.py, backend/app/billing.py, backend/app/models.py, backend/app/routers/billing.py, backend/app/routers/tickets.py, backend/app/schemas.py, backend/app/ticket_services.py, backend/tests/test_agreement_attachment.py, backend/tests/test_seed_and_migrations.py, docs/api/openapi.json
- 17-02 Billing by agreement: all-inclusive and block rollover (Complete with Warnings): backend/app/billing.py, backend/app/billing_repo.py, backend/tests/test_agreement_billing.py, docs/BILLING.md
- 17-03 Profitability and utilisation by agreement (Complete with Warnings): backend/app/schemas.py
- 17-04 Agreement controls and reports in the UI (Complete): frontend/src/AgreementAttachment.test.tsx, frontend/src/api.ts, frontend/src/pages/TicketDetail.tsx, frontend/src/pages/billing/Agreements.tsx, frontend/src/pages/reports/ProfitabilityReport.tsx

## Decisions
- 17-01: Leaving `agreement_id` out of a create request uses the default (the ticket's agreement, for time); sending null explicitly means no agreement.
- 17-02: Carried-in minutes are shown in hours, like the existing line: "N h included (incl. C h carried over)". The note appears only when the carry-in is above 0, so e
- 17-03: The extended response models live in `schemas.py`, the file the plan allows, and subclass the `report_schemas` models; the default response shape only gains `gr
- 17-04: The agreement lists come from GET /agreements, which needs billing:read. Without it the ticket and time rows show text only ("Agreement #id" or "No agreement"),
- 17-04: A time entry's select offers agreements still in force on its work_date, plus its current one.
- 17-04: The Fields card shows a plain Agreement block, not a select, when the client has no agreements.

## Conventions and Open Questions
- 17-01 convention: tickets.agreement_id and time_entries.agreement_id are nullable FKs (indexes ix_tickets_agreement_id, ix_time_entries_agreement_id)
- 17-01 convention: null means today's billing behaviour.
- 17-02 convention: `block_candidates` now takes `(db, scope, agreement, start, end)` instead of org_id
- 17-02 convention: `_pull_block` is its only caller.
- 17-03 convention: Plan 17-04 UI: pass `group=agreement` and read `agreement_id` (null means 'No agreement'), `agreement_name` and `agreement_type` on profitability rows, and the 
- 17-04 convention: The profitability toggle sends group only when set to agreement
- 17-04 convention: the default request is unchanged.
- 17-04 convention: The 409 text comes straight from the API's error detail

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0041_agreement_attachment_and_rollover.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/billing.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/models.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/routers/billing.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/routers/tickets.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/schemas.py` | 17-01: Agreement on tickets and time entries |
| `backend/app/ticket_services.py` | 17-01: Agreement on tickets and time entries |
| `backend/tests/test_agreement_attachment.py` | 17-01: Agreement on tickets and time entries |
| `backend/tests/test_seed_and_migrations.py` | 17-01: Agreement on tickets and time entries |
| `docs/api/openapi.json` | 17-01: Agreement on tickets and time entries |
| `backend/app/billing.py` | 17-02: Billing by agreement: all-inclusive and block rollover |
| `backend/app/billing_repo.py` | 17-02: Billing by agreement: all-inclusive and block rollover |
| `backend/tests/test_agreement_billing.py` | 17-02: Billing by agreement: all-inclusive and block rollover |
| `docs/BILLING.md` | 17-02: Billing by agreement: all-inclusive and block rollover |
| `backend/app/schemas.py` | 17-03: Profitability and utilisation by agreement |
| `frontend/src/AgreementAttachment.test.tsx` | 17-04: Agreement controls and reports in the UI |
| `frontend/src/api.ts` | 17-04: Agreement controls and reports in the UI |
| `frontend/src/pages/TicketDetail.tsx` | 17-04: Agreement controls and reports in the UI |
| `frontend/src/pages/billing/Agreements.tsx` | 17-04: Agreement controls and reports in the UI |
| `frontend/src/pages/reports/ProfitabilityReport.tsx` | 17-04: Agreement controls and reports in the UI |

## Verification
- 17-01 (Owner test note 8): 7/7 verification commands passed
- 17-02 (P01-01 note, Block-hour rollover configurable): 6/6 verification commands passed
- 17-03 (Profitability and utilisation by agreement): 6/6 verification commands passed
- 17-04 (Owner test note 8, Profitability by agreement): 5/5 verification commands passed

## Agents
- 17-01: engineering-backend-architect
- 17-02: engineering-backend-architect
- 17-03: engineering-backend-architect
- 17-04: engineering-frontend-developer

## Also Covered
- backend/app/report_metrics.py
- backend/app/routers/reports.py
- backend/tests/test_agreement_profitability.py
- docs/REPORTS.md
