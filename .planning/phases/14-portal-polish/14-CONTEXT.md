# Phase 14: Portal polish -- Context

## Phase Goal
Client users sign in with Entra SSO, attach files, manage their contact details and export their data.

## Requirements Covered
- REQ-13

## What Already Exists (from prior phases)
- Portal auth (Phase 0/5): one-time emailed links (auth/portal_sessions.py), a separate psa_portal cookie and portal_sessions table; PortalCtx scopes every request to the contact's org via RLS (portal_deps.py); public_session runs with an all-org scope for the unauthenticated routes
- Staff Entra OIDC: auth/oidc.py get_oauth() registers a single-tenant 'entra' client (authlib, PKCE S256, state in the SessionMiddleware psa_oidc_state cookie); resolve_user_from_claims never auto-creates users and binds oid on first login; tests/test_auth.py fakes get_oauth with FakeOAuth/FakeEntra
- Attachments today come only from inbound mail (mail/ingest.py _store_attachments): files under settings.attachments_dir at key '{ticket_id}/{uuid4hex}', max_attachment_bytes 10 MB, table attachments is immutable (SELECT, INSERT grants) with RLS; staff download (routers/tickets.py download_attachment) always sends application/octet-stream with nosniff and a path-traversal guard
- reports.to_csv/_cell already neutralise formula cells; reports.record_export audits staff exports
- Phase 13 added the portal KB routes; Phase 12 moved everything to /api/v1 and committed docs/api/openapi.json (regenerate with the pinned venv, PIT-002)
- python-multipart is NOT a dependency

## Key Design Decisions
- Portal SSO uses a SECOND, multi-tenant Entra app registration (PORTAL_ENTRA_CLIENT_ID / PORTAL_ENTRA_CLIENT_SECRET, authority 'organizations'), separate from the single-tenant staff app, registered in auth/oidc.py beside the staff client (shared helper, not a copy)
- Because the multi-tenant metadata issuer is a {tenantid} template, the portal client validates iss itself: iss must equal https://login.microsoftonline.com/{tid}/v2.0 for the token's own tid (authlib claims_options validate hook); signature, aud, exp and nonce stay authlib's
- Identity mapping (no auto-provisioning): staff set organizations.entra_tenant_id (the client's tenant GUID, partial-unique). On callback: tid must match exactly one non-archived organization; then a contact of THAT org with portal_access and not archived is matched by contacts.entra_oid, else by case-insensitive email/preferred_username within that org only; an oid already bound to a different value is denied; the oid is bound on first success. Every denial is audited portal.login_failed with a reason and redirects to /portal?sso=denied (no detail leaked)
- One-time links keep working for every contact (fallback), and both login paths produce the same portal session for the same contact record
- Portal SSO routes: GET /portal/sso/login (302 to Microsoft, 404 when not configured or portal disabled), GET /portal/sso/callback, and public GET /portal/login-options -> {sso: bool}; all three are added to the contract test's PUBLIC set
- Uploads are JSON with base64 content (no new dependency): POST /portal/tickets/{id}/attachments {filename, content_base64}; decoded size 1..max_attachment_bytes (413 above), extension allowlist pdf png jpg jpeg gif txt log csv docx xlsx pptx zip eml msg (415 otherwise), invalid base64 422, closed ticket 409, at most 20 uploads per contact per hour (429); filename sanitised like the staff download; stored with the ingest key scheme
- attachments gains source email|portal (CHECK; email requires email_message_id, which becomes nullable) and uploaded_by_contact_id; the portal lists and downloads only portal-sourced attachments on tickets the contact can see; staff see all with a source badge
- Contact self-service: PATCH /portal/me/contact edits name, phone and title only; email is the login identity and stays staff-managed; audited portal.contact_update with before/after
- CSV export: GET /portal/export/tickets.csv (all portal users, tickets they can see), /portal/export/invoices.csv (billing contacts only), /portal/export/devices.csv (device sharing only); built with reports.to_csv, capped at 10000 rows, Content-Disposition attachment, audited portal.export {kind, rows}
- Every new portal endpoint gets a cross-organization negative test (board recommendation)
- Phase 14 is full process: board quick-assess ran (recommendations above taken as constraints); spec and architecture proposals skipped by default

## Plan Structure
- **Plan 14-01 (Wave 1)**: Portal Entra SSO and the phase 14 schema -- Add migration 0035 for the whole phase and Entra SSO sign-in for portal contacts through a multi-tenant app registration, with the identity mapping and denials from the context, tested against a fake IdP.
- **Plan 14-02 (Wave 2)**: Portal attachments, contact self-service and CSV export (backend) -- Let portal contacts upload and download attachments on their tickets, edit their own name, phone and title, and export their tickets, invoices and devices as CSV, all isolated to their organization and audited.
- **Plan 14-03 (Wave 3)**: Portal polish frontend and manual checks -- Add Sign in with Microsoft to the portal login, file attachments on portal tickets, a My details page, CSV export buttons, the staff tenant-id and SSO-linked fields, and the Phase 14 manual checks.
