---
phase: 09-crm-renewals
compacted: 2026-10-21
original_summaries: [09-01-SUMMARY.md, 09-02-SUMMARY.md, 09-03-SUMMARY.md]
requirements_satisfied: [REQ-09]
---

# Phase 9: CRM & renewals — Compacted Summary

## Deliverables
- 09-01 CRM schema, stages and permissions (Complete): backend/alembic/versions/0030_crm.py, backend/app/models.py, backend/app/permissions.py, backend/tests/conftest.py, backend/tests/test_crm_schema.py, backend/tests/test_permissions.py
- 09-02 CRM service, quote link, forecast and renewal job (Complete)
- 09-03 Sales pipeline, forecast and renewals UI, docs and verify checklist (Complete): docs/CRM.md, docs/verify/crm.md, frontend/src/App.tsx, frontend/src/Crm.test.tsx, frontend/src/api.ts, frontend/src/pages/Dashboard.tsx, frontend/src/pages/OrgOpportunitiesCard.tsx, frontend/src/pages/OrganizationDetail.tsx, frontend/src/pages/Settings.tsx, frontend/src/pages/crm/Forecast.tsx, frontend/src/pages/crm/Leads.tsx, frontend/src/pages/crm/OpportunityPage.tsx, frontend/src/pages/crm/Pipeline.tsx, frontend/src/pages/crm/Renewals.tsx, frontend/src/pages/crm/Sales.tsx, frontend/src/pages/quotes/QuotePage.tsx

## Decisions
- 09-01: Added uq_quotes_id_org and uq_agreements_id_org in the migration, since neither table had a unique (id, organization_id) for the composite FKs. The downgrade dr
- 09-01: Added a partial unique index uq_opportunity_stages_active_terminal, so at most one active won and one active lost stage can exist. The "at least one" half is le
- 09-01: leads and opportunity_stages have no RLS and get SELECT, INSERT and UPDATE for psa_app only. They have no DELETE.
- 09-03: Convert button shows only for Qualified leads, because the backend rejects any other status with a 409.
- 09-03: Renewals "end date" is the reminder's due_on, which the backend sets to the agreement end date.
- 09-03: The quote page has no direct opportunity field, so it finds the linked deal from the client's opportunities by quote_id.

## Conventions and Open Questions
- 09-01 convention: Constraint names to match in 09-02: ck_leads_status, ck_opportunity_stages_kind and _probability, ck_opportunities_kind, _monthly and _term, ck_renewal_reminder
- 09-01 convention: The reseeded stages get fresh ids after each TRUNCATE ... RESTART IDENTITY, so tests should look stages up by name or kind.
- 09-01 convention: Opportunity.quote_id and agreement_id, and RenewalReminder.agreement_id and opportunity_id, are plain BigInteger columns in the models. The composite FKs exist 
- 09-02 convention: Routes are under /api/crm/*: reads need crm:read, writes crm:write, and stage config needs config:manage.
- 09-02 convention: `renewals.scan` runs inside `worker.billing_jobs` with a Ctx whose user is None.
- 09-02 convention: `settings.renewal_reminder_days` and `settings.renewal_email` are available through the existing settings PATCH.
- 09-03 convention: The renewal email links to /crm/renewals, and that route now exists.
- 09-03 convention: Pages use query keys under ["crm", ...]
- 09-03 convention: invalidating ["crm"] refreshes all of them.

## Files Modified
| File | Change |
|------|--------|
| `backend/alembic/versions/0030_crm.py` | 09-01: CRM schema, stages and permissions |
| `backend/app/models.py` | 09-01: CRM schema, stages and permissions |
| `backend/app/permissions.py` | 09-01: CRM schema, stages and permissions |
| `backend/tests/conftest.py` | 09-01: CRM schema, stages and permissions |
| `backend/tests/test_crm_schema.py` | 09-01: CRM schema, stages and permissions |
| `backend/tests/test_permissions.py` | 09-01: CRM schema, stages and permissions |
| `docs/CRM.md` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `docs/verify/crm.md` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/App.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/Crm.test.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/api.ts` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/Dashboard.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/OrgOpportunitiesCard.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/OrganizationDetail.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/Settings.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/Forecast.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/Leads.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/OpportunityPage.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/Pipeline.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/Renewals.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/crm/Sales.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |
| `frontend/src/pages/quotes/QuotePage.tsx` | 09-03: Sales pipeline, forecast and renewals UI, docs and verify checklist |

## Verification
- 09-01 (REQ-09): 5/5 verification commands passed
- 09-02 (REQ-09): 5/5 verification commands passed
- 09-03 (REQ-09): 5/5 verification commands passed

## Agents
- 09-01: engineering-backend-architect
- 09-02: engineering-backend-architect
- 09-03: engineering-frontend-developer

## Also Covered
- backend/app/crm.py
- backend/app/crm_schemas.py
- backend/app/renewals.py
- backend/app/routers/crm.py
- backend/app/main.py
- backend/app/quoting.py
- backend/app/worker.py
- backend/app/config_services.py
- backend/app/schemas.py
- backend/tests/test_crm.py
- backend/tests/test_crm_api.py
- backend/tests/test_renewals.py
- .planning/VERIFY.md
