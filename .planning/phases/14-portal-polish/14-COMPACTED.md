---
phase: 14-portal-polish
compacted: 2026-10-31
original_summaries: [14-01-SUMMARY.md, 14-02-SUMMARY.md, 14-03-SUMMARY.md]
requirements_satisfied: [REQ-13]
---

# Phase 14: Portal polish — Compacted Summary

## Deliverables
- 14-01 Portal Entra SSO and the phase 14 schema (Complete with Warnings): .env.example, backend/alembic/versions/0035_portal_polish.py, backend/app/auth/oidc.py, backend/app/config.py, backend/app/models.py, backend/app/portal_schemas.py, backend/app/routers/organizations.py, backend/app/routers/portal.py, backend/app/schemas.py, backend/app/services.py, backend/tests/test_organizations.py, backend/tests/test_portal_sso.py, backend/tests/test_seed_and_migrations.py, backend/tests/test_zz_api_contract.py, docs/PORTAL.md, docs/PORTAL_SSO.md, docs/api/openapi.json
- 14-02 Portal attachments, contact self-service and CSV export (backend) (Complete): backend/app/portal.py, backend/app/portal_files.py, backend/app/portal_schemas.py, backend/app/repositories.py, backend/app/routers/portal.py, backend/app/schemas.py, backend/tests/test_portal_polish.py, backend/tests/test_tickets.py, docs/PORTAL.md, docs/api/openapi.json
- 14-03 Portal polish frontend and manual checks (Complete): backend/app/portal.py, backend/app/schemas.py, backend/tests/test_portal_polish.py, docs/api/openapi.json

## Decisions
- 14-01: no new grants: 0001 already gives psa_app table-wide UPDATE on contacts and organizations, and attachments keep SELECT, INSERT plus UPDATE (organization_id)
- 14-02: Only a ticket with status `closed` refuses uploads; `resolved` and `waiting_on_customer` accept them.
- 14-02: The extension allow-list is txt, log, csv, pdf, png, jpg, jpeg, gif, webp, doc, docx, xls, xlsx, ppt, pptx, zip, eml, msg. Anything else is 415.
- 14-02: The oversized-body check runs on the encoded length before decoding, as the plan asked.
- 14-03: OrgForm sends `entra_tenant_id` only when the user has `portal:manage`. The backend returns 403 for any non-empty tenant id from a user without it, so a plain o
- 14-03: The Unlink Microsoft button stays on `org:write` (`canWrite`). The backend's `update_contact` only applies `unlink_entra` under the normal contact permission, a

## Conventions and Open Questions
- 14-01 convention: Attachment.source defaults to 'email' in the database
- 14-01 convention: portal uploads must set source='portal', uploaded_by_contact_id and email_message_id=None (the CHECK requires a message id for email rows)
- 14-02 convention: Portal uploads set `source='portal'`, `email_message_id=None` and `uploaded_by_contact_id`. Portal reads filter on `source='portal'`.
- 14-02 convention: Tests that upload must redirect `attachments_dir` to a temp dir, as the autouse fixture in `test_portal_polish.py` does.
- 14-03 convention: `PortalMeOut` now includes `phone` and `title`
- 14-03 convention: the OpenAPI spec is regenerated and its check passes.
- 14-03 convention: Phase 15 manual checks are in `docs/verify/portal-polish.md` and `.planning/VERIFY.md`.

## Files Modified
| File | Change |
|------|--------|
| `.env.example` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/alembic/versions/0035_portal_polish.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/auth/oidc.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/config.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/models.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/portal_schemas.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/routers/organizations.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/routers/portal.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/schemas.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/services.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/tests/test_organizations.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/tests/test_portal_sso.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/tests/test_seed_and_migrations.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/tests/test_zz_api_contract.py` | 14-01: Portal Entra SSO and the phase 14 schema |
| `docs/PORTAL.md` | 14-01: Portal Entra SSO and the phase 14 schema |
| `docs/PORTAL_SSO.md` | 14-01: Portal Entra SSO and the phase 14 schema |
| `docs/api/openapi.json` | 14-01: Portal Entra SSO and the phase 14 schema |
| `backend/app/portal.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/portal_files.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/portal_schemas.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/repositories.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/routers/portal.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/schemas.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/tests/test_portal_polish.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/tests/test_tickets.py` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `docs/PORTAL.md` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `docs/api/openapi.json` | 14-02: Portal attachments, contact self-service and CSV export (backend) |
| `backend/app/portal.py` | 14-03: Portal polish frontend and manual checks |
| `backend/app/schemas.py` | 14-03: Portal polish frontend and manual checks |
| `backend/tests/test_portal_polish.py` | 14-03: Portal polish frontend and manual checks |
| `docs/api/openapi.json` | 14-03: Portal polish frontend and manual checks |

## Verification
- 14-01 (REQ-13): 6/6 verification commands passed
- 14-02 (REQ-13): 6/6 verification commands passed
- 14-03 (REQ-13): 6/6 verification commands passed

## Agents
- 14-01: engineering-security-engineer
- 14-02: engineering-backend-architect
- 14-03: engineering-frontend-developer

## Also Covered
- backend/app/auth/portal_sessions.py
- backend/tests/test_backup_restore.py
- backend/app/routers/tickets.py
- frontend/src/api.ts
- frontend/src/portal/PortalApp.tsx
- frontend/src/portal/PortalLogin.tsx
- frontend/src/portal/PortalAttachments.tsx
- frontend/src/portal/MyDetailsPage.tsx
- frontend/src/portal/ExportButton.tsx
- frontend/src/pages/OrganizationDetail.tsx
- frontend/src/pages/TicketDetail.tsx
- frontend/src/PortalPolish.test.tsx
- README.md
