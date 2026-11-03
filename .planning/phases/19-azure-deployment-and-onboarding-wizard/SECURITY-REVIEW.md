# Phase 19: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| # | Category | Result | Evidence |
|---|---|---|---|
| A1 | Injection | PASS | Graph OData filter values escaped (_odata), path ids quote()d; Key Vault secret names validated ^[a-z0-9-]{1,127}$; deploy.sh passes values via --file, never argv |
| A2 | Broken Auth | PASS | consent: state token_urlsafe(32) + PKCE S256, bound to admin user id, 10 min, compare_digest, consumed once (onboarding_auth.py:63-109) |
| A3 | Sensitive Data | PASS | admin token stored only as Fernet ciphertext, ≤60 min, deleted on finish; secretText only in a local var to Key Vault; logs carry status/exception type only (onboarding.py:67-70, keyvault.py:89-105) |
| A4 | XXE | N/A | no XML |
| A5 | Access Control | PASS | every onboarding route: config:manage + role admin + no API key, 404 when disabled (routers/onboarding.py:46-52); nav entry gated by admin-only user:manage |
| A6 | Misconfiguration | WARN | managed identity holds Key Vault Secrets Officer (needed by the wizard) — accepted risk SEC note |
| A7 | XSS | PASS | React escaping; no raw HTML sinks in Setup.tsx |
| A8 | Deserialization | PASS | JSON only |
| A9 | Known Vulns | PASS | no new dependencies |
| A10 | Logging | PASS | onboarding.* audit events incl. rejected state in its own transaction; no secrets in audit detail |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Browser → consent callback | Forged callback / login CSRF | Spoofing | attacker-supplied code/state | one-time state bound to signed-in admin + PKCE | MITIGATED |
| App DB | Token theft from DB dump | Information disclosure | read onboarding_tokens | Fernet ciphertext, ≤60 min, deleted on finish | MITIGATED |
| App → Graph | Lingering directory power | Elevation of privilege | reuse of delegated grant after setup | finish removes the three admin scopes from the grant | PARTIAL (only if admin clicks Finish) |
| App → Key Vault | Compromised app overwrites secrets | Tampering | managed identity Secrets Officer | vault-scoped role, purge protection, audit | PARTIAL (accepted) |
| Operator → deploy.sh | Secrets on screen/disk | Information disclosure | echo / leftover files | umask 077 temp dir, --file, trap cleanup, no set -x | MITIGATED |

## Attack Surface
- /api/v1/onboarding/* (admin-only, 404 unless ONBOARDING_ENABLED): consent/start, consent/callback, status, portal-app, mail-app, connect, finish
- Outbound: login.microsoftonline.com token endpoint, graph.microsoft.com (delegated admin token), Key Vault REST via managed identity
- deploy/azure/deploy.sh run by the operator with az CLI; main.bicep (Key Vault RBAC, private PostgreSQL, ingress only on proxy)

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A6:Misconfiguration | MEDIUM | The app's managed identity holds Key Vault Secrets Officer so the wizard can write secrets; a compromised app could overwrite vault secrets (e.g. point SSO at another app). Accepted by design. | deploy/azure/main.bicep:164 | After setup, optionally remove the Secrets Officer assignment (documented in AZURE_DEPLOY.md as a hardening step) and re-add it only when re-running Setup. | OPEN |
| SEC-002 | A5:Access Control | MEDIUM | If the admin never clicks Finish, the delegated grant for Application.ReadWrite.All etc. stays on the staff SSO app for that admin (token row expires in 60 min, but the grant persists). | backend/app/onboarding.py:477 | Show a persistent banner on Setup while the grant exists; document manual revocation in Entra (Enterprise apps → Permissions). | OPEN |
| SEC-003 | A3:Sensitive Data | LOW | The consent token is encrypted with the same credentials_key as integration secrets; key compromise exposes it for ≤60 min. | backend/app/onboarding_auth.py:154 | Acceptable given the 60-minute cap and deletion on finish. | OPEN |
