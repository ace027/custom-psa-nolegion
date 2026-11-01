# Phase 14: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| Item | Result | Evidence |
|---|---|---|
| A01 Broken Access Control | PASS | portal_files.py:111,162,173-185 (visibility, scope.apply, source='portal', traversal guard); routers/portal.py:234,244 (billing_only/devices_only); organizations.py:32-38 (tenant id needs portal:manage); portal_schemas.py:30 (extra=forbid) |
| A02 Cryptographic Failures | PASS | portal_sessions.py:98,119 (token_urlsafe(32), hashed); routers/portal.py:62 (httponly, secure in prod, SameSite=Lax) |
| A03 Injection | PASS | reports.py:389 formula neutralising; ORM-only queries in oidc.py:118-139; no dangerouslySetInnerHTML |
| A04 Insecure Design | WARN | oidc.py:131-142 email fallback trusts an unverified email claim inside the client tenant (M-1) |
| A05 Security Misconfiguration | PASS | main.py:73-86 (X-Requested-With, nosniff, no-store); octet-stream + nosniff downloads |
| A06 Vulnerable Components | PASS | scan: 0 dependency findings; authlib 1.9.1 |
| A07 Identification and Authentication | WARN | oidc.py:46-58 iss pinned to tid; nonce/state/PKCE/signature checked by authlib; aud not pinned explicitly (L-1) |
| A08 Software and Data Integrity | PASS | 0035: attachments stay SELECT/INSERT; CHECKs; downgrade refuses with portal files |
| A09 Logging and Monitoring | PASS | every SSO denial and login audited; uploads, exports, contact updates audited; small gap for unexpected exceptions (INFO) |
| A10 SSRF | N/A | only fixed Microsoft metadata/JWKS/token URLs |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Browser -> /portal/sso/callback | Foreign tenant or forged issuer | Spoofing | Any Entra tenant user signs in | iss == LOGIN_BASE/{tid}/v2.0; tid matches exactly one org (unique lower(tid)) | MITIGATED |
| Browser -> /portal/sso/callback | Staff/portal code or token confusion | Spoofing | Victim sent to the other callback | codes bound to client_id; state keyed per client; nonce; staff resolver requires MSP tid | MITIGATED (prefix overlap L-2) |
| Browser -> /portal/sso/callback | Login CSRF / fixation | Spoofing | Attacker's code+state URL | state+nonce in signed cookie; fresh session token | MITIGATED |
| Client tenant user -> contact mapping | Sign in as another contact | Spoofing/EoP | Tenant member or guest with an unbound contact's email | org-limited lookup, portal_access, oid binding; email not verified | PARTIAL (M-1) |
| Cross-org via email | Bind a contact in another org | EoP | Same email in two orgs | email lookup filtered by org; bound oid elsewhere denied | MITIGATED |
| Portal session lifetime | Session survives revocation | EoP | Contact archived/disabled, unlinked | _active() on every request; unlink revokes sessions | MITIGATED (tenant change L-4) |
| Callback redirect | Open redirect | Tampering | Crafted return URL | fixed destinations, no next param | MITIGATED |
| Portal state-changing routes | CSRF | Tampering | Cross-site POST/PATCH | SameSite=Lax + required X-Requested-With | MITIGATED |
| Attachments | IDOR | Information disclosure | Guess ids | RLS + scope.apply + source + visibility re-check | MITIGATED |
| Attachments | Stored XSS / sniffing | Tampering | HTML/SVG upload | allowlist; octet-stream + nosniff + attachment | MITIGATED |
| Attachments | Memory/disk DoS | DoS | Large bodies, many uploads | size-limited route; exact cap; 20/hour | PARTIAL (L-3) |
| Exports | CSV injection | Tampering | =HYPERLINK subject | _cell prefixes ' | MITIGATED |
| Exports | Data to non-designated contact | Information disclosure | Plain contact GETs invoices.csv | billing_only/devices_only; org scope | MITIGATED |
| public_session (all-org RLS) | Over-broad reads/writes | EoP | Callback logic | only lookups, oid bind, session insert, audit | MITIGATED |
| Staff -> organizations.entra_tenant_id | Low-privilege staff points client at attacker tenant | EoP | PATCH organization | portal:manage required; GUID validated | MITIGATED |
| Migration downgrade | Silent loss of client files | Tampering | alembic downgrade | refuses while portal rows exist | MITIGATED |

## Attack Surface
- Unauthenticated: GET /api/v1/portal/login-options; GET /portal/sso/login (starts OIDC, sets psa_oidc_state); GET /portal/sso/callback (trust boundary: Microsoft token endpoint and JWKS, then claims-to-contact mapping under the all-org RLS scope); existing POST /portal/login-link and /portal/verify.
- Authenticated portal contact (portal cookie, RLS = one org): PATCH /portal/me/contact; GET/POST /portal/tickets/{id}/attachments (base64 JSON, size-limited route); GET /portal/attachments/{id}/download; GET /portal/export/{tickets,invoices,devices}.csv.
- Staff: organizations entra_tenant_id (portal:manage); contact unlink_entra; staff download now includes client-uploaded files.
- Storage: attachments_dir/{ticket_id}/{uuid4}; no user-controlled path parts.
- Identity trust: the MSP trusts each client tenant's directory email/UPN for contacts not yet bound.

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A07:Identification and Authentication Failures | MEDIUM | First-login fallback matches an unbound contact by email/preferred_username without any verified-email check. A user (or invited guest) inside the client's own tenant whose email claim equals an unbound contact's email (e.g. the billing contact) gets that contact's portal session and binds their oid, locking the real contact out (oid_mismatch). | backend/app/auth/oidc.py:131-142 | Require the xms_edov optional claim (or a per-org verified-domain list) before the email fallback, or require the first binding to be confirmed through a one-time email link; document the residual trust in docs/PORTAL_SSO.md. | OPEN |
| SEC-002 | A07:Identification and Authentication Failures | LOW | PORTAL_CLAIMS_OPTIONS replaces authlib defaults, so aud is not pinned (validate_aud returns early). Not exploitable today (back-channel code redemption, azp check) but the comment claiming aud is checked is wrong. | backend/app/auth/oidc.py:56-58 | Add aud: {essential: True, values: [portal_entra_client_id]} and a wrong-aud test. | OPEN |
| SEC-003 | A07:Identification and Authentication Failures | LOW | Client name 'entra' is a prefix of 'entra_portal', so authlib state keys and prefix cleanup overlap in the shared psa_oidc_state cookie. Not exploitable (codes are client-bound) but a namespace confusion. | backend/app/auth/oidc.py:20-42 | Rename the clients so neither is a prefix of the other (entra_staff / entra_portal). | OPEN |
| SEC-004 | A04:Insecure Design | LOW | Base64 decode runs before the 20/hour rate check; the count-then-insert is not atomic; no per-org disk quota. | backend/app/portal_files.py:118-126 | Check the rate limit before decoding, serialize per contact (advisory lock), add a per-org storage quota. | OPEN |
| SEC-005 | A01:Broken Access Control | LOW | Changing or clearing organizations.entra_tenant_id does not revoke SSO sessions or clear bound oids, so sessions from a wrong tenant survive up to portal_session_hours. | backend/app/routers/organizations.py:32-38 | On tenant-id change, revoke portal sessions of that org's SSO-bound contacts and clear their entra_oid. | OPEN |
| SEC-006 | A09:Logging and Monitoring | INFO | Only PortalLoginDenied is audited; other resolver exceptions (e.g. an entra_oid unique race) give an unaudited 500. | backend/app/auth/oidc.py:118-151 | Map IntegrityError on the flush to deny('oid_conflict'). | OPEN |
| SEC-007 | A04:Insecure Design | INFO | Allowlist includes macro-capable legacy Office formats, .zip, .msg/.eml that staff then open; same exposure as inbound email. | backend/app/portal_files.py:26-47 | Consider malware scanning or dropping legacy macro formats. | OPEN |
| SEC-008 | A01:Broken Access Control | INFO | An admin can set the MSP's own tenant on a client org (by design, admin-only). | backend/app/routers/organizations.py:32-38 | Warn in the UI when the tenant id equals the staff tenant. | OPEN |
