# Phase 6: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| # | Category | Result | Evidence |
|---|---|---|---|
| A1 | Injection | PASS | ORM bound params; state Literal, limit ge/le (routers/integrations.py:121-122) |
| A2 | Broken Auth | PASS | require(integration:manage) on both routes; token in memory; Fernet creds |
| A3 | Sensitive Data | PASS | _safe() limits vendor errors to status/path/class name |
| A4 | XXE | N/A | JSON only |
| A5 | Access Control | PASS (WARN) | org from asset; composite FKs; forced RLS; worker scope all relies on app code |
| A6 | Misconfiguration | WARN | base_url any https host; unknown alert_* keys accepted |
| A7 | XSS | PASS | no dangerouslySetInnerHTML; React text nodes |
| A8 | Deserialization | PASS | r.json() + str() coercion |
| A9 | Known Vulns | PASS | scan clean |
| A10 | Logging | WARN | system actions audited; no anomaly record on mass clear; failed-poll audit per attempt |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Vendor -> engine | Empty/truncated list mass-resolves tickets | T/D | 200 [] or cut list; poll treats missing as cleared | resolve_if_untouched default, notes, audit | PARTIAL |
| Vendor -> engine | Alert flood | D | many distinct condition keys | severity filter, mapped devices only | UNMITIGATED |
| Vendor -> engine | Spoofed deviceId | S | other client's device | org from this integration's asset mapping | MITIGATED |
| Vendor -> engine | Dedupe poisoning | T | changing uid | uq_rmm_alerts_open | MITIGATED |
| Admin API | Elevation | E | non-admin call | require(M) | MITIGATED |
| Admin API | Param abuse | T/D | huge limit, bad state | Literal + ge/le | MITIGATED |
| Admin API | SSRF via base_url | I/S | admin sets hostile https host | https only, admin only | PARTIAL |
| Admin API | Config tampering | T | bool-as-int, bad enums | strict validation | MITIGATED |
| Worker scope all | Cross-client write | E/I | wrong org bug | org from asset, composite FKs | MITIGATED |
| Worker scope all | Repudiation | R | system resolves | audit actor_type system + note | MITIGATED |
| Worker scope all | Corrupt config aborts job | D | non-int poll minutes in DB | API validation | PARTIAL |
| Vendor text -> UI/ticket | Stored XSS | T/I | HTML in message | React escaping | MITIGATED |
| Vendor text -> UI/ticket | Length abuse | D | long fields | message 1000, subject 200; keys unbounded | PARTIAL |
| Vendor text -> UI/ticket | Bidi/zero-width spoofing | S | U+202E in message | source=rmm badge | PARTIAL |

## Attack Surface
- Inbound untrusted: NinjaOne GET /v2/alerts body and OAuth token response
- Outbound: worker HTTPS to admin-set base_url with decrypted client secret
- Admin HTTP: GET /integrations/{id}/alerts, POST /integrations/{id}/alerts/poll, PATCH /integrations/{id} config
- DB: rmm_alerts (forced RLS), tickets.asset_id, integrations.alerts_*, audit_log, ticket_notes
- Vendor text sinks: ticket subject/description, system notes, rmm_alerts.message, alerts_last_error, audit detail
- Readers: admin RmmAlertsCard; tech/read_only via ticket APIs; portal contacts with org-wide view (portal.py:208-210,290)
- Trust escalation: worker runs scope all, actor None

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A4:Insecure Design | MEDIUM | A missing alert counts as cleared with no sanity guard. An empty or truncated 200 response from /v2/alerts clears every open alert and resolves untouched tickets; with always_resolve, it resolves all of them. list_alerts is unpaginated and UNVERIFIED. | backend/app/rmm_alerts.py:340-353, backend/app/integrations/ninjaone.py:187-192 | Skip clears when the fetch returns 0 alerts while some are open, or when the count drops sharply; record the anomaly in alerts_last_error and audit. Optionally require two consecutive misses, cap auto-resolves per poll, and verify pagination against a live tenant. | FIXED |
| SEC-002 | A4:Insecure Design | MEDIUM | Nothing caps the alerts or tickets created per poll, and condition_key and device_external_id have no length bound, so a flapping or hostile vendor can create unbounded tickets. | backend/app/rmm_alerts.py, backend/app/integrations/ninjaone.py:92-101 | Cap tickets created per poll and report the overflow in alerts_last_error. Truncate condition_key and device_external_id to about 200 characters, and re-apply the message bound in the engine. | FIXED |
| SEC-003 | A5:Security Misconfiguration | LOW | base_url accepts any https host, so an admin could send the client secret to a host of their choosing (SSRF / exfiltration). | backend/app/asset_schemas.py:22,30 | Owner decision: optionally allowlist NinjaOne regional domains. | FIXED |
| SEC-004 | A1:Broken Access Control | LOW | Portal contacts with an org-wide view can read RMM ticket descriptions, which include the device id, condition key and raw vendor message. The data stays within the same client. | backend/app/portal.py:208-210,290, backend/app/rmm_alerts.py:108-118 | Owner decision: hide source=rmm tickets from the portal or sanitize their description. | FIXED |
| SEC-005 | A10:Logging | LOW | Every failed poll attempt writes an integration.alerts_failed audit row, roughly 288 a day during a vendor outage. | backend/app/rmm_alerts.py:307-313 | Audit only when the error text changes or the state flips. | FIXED |
| SEC-006 | A5:Security Misconfiguration | LOW | Unknown alert_* config keys are accepted on NinjaOne. due() reads alert_poll_minutes without a type check, so one corrupt row aborts the job for every integration. | backend/app/integration_services.py:46-60, backend/app/rmm_alerts.py:80-84 | Allowlist the alert keys, and fall back to the default or catch the error per integration in due(). | FIXED |
| SEC-007 | A3:Sensitive Data | LOW | Bidi and zero-width control characters in vendor text survive the whitespace normalisation into the subject, description and UI. | backend/app/integrations/ninjaone.py:97 | Strip Unicode categories Cc, Cf, Zl and Zp in _to_alert. | FIXED |
| SEC-008 | A1:Broken Access Control | INFO | The worker runs with scope all, but org derivation and the composite FKs hold. Ignored client maps and inactive orgs are not checked on intake. | backend/app/worker.py:119-120, backend/app/rmm_alerts.py:192-210 | Add a two-client colliding-device-id test; optionally join IntegrationClientMap.ignored. | FIXED |
| SEC-009 | A4:Insecure Design | INFO | list_alerts loads all organizations and lazy-loads the asset and ticket per row (N+1, capped at 500). | backend/app/integration_services.py:177-186 | Use selectinload and join the organization name. | FIXED |

## Resolution (2026-10-20)
- SEC-001 to SEC-002, SEC-004 to SEC-007, SEC-009 were fixed in 69523ca (owner choices recorded in 06-REVIEW.md).
- SEC-003 is fixed by a quick task. A NinjaOne base_url must be a plain https origin on ninjarmm.com or ninjaone.com (no userinfo, port, query or fragment). Changing any integration's host needs the credentials entered again, so a stored secret is never sent to a new host.
- SEC-008 is fixed. Intake requires a non-ignored client map and an active, unarchived organization. A two-integration colliding-device-id test is added.
