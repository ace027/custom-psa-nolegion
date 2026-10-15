# Phase 4: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| # | Category | Result | Evidence |
|---|---|---|---|
| A1 | Injection | WARN | SQL is ORM or parameterised (calendar_sync.py). The Graph path is built from an unencoded User.email (graph.py:166); see the LOW finding. |
| A2 | Broken Auth | PASS | New routes use require(P.SCHEDULE_*) (routers/scheduling.py:216,226; deps.py:35-47). Graph uses client credentials with the token in memory (graph.py:144-160). |
| A3 | Sensitive Data | WARN | Event payload is the ticket id plus a link, private (graph.py:46-58). The busy cache stores times and status only. Graph error text is shown to all schedule:read roles (LOW finding). |
| A4 | XXE | N/A | No XML. |
| A5 | Access Control | PASS | Status needs schedule:read and retry needs schedule:write. appointment_sync has forced RLS (0025:46-50). The settings toggle needs config:manage, which is admin only (routers/config.py:148). |
| A6 | Misconfiguration | PASS | Sync is off by default (0025:22-24). backend/dev is not in the Docker image. fake_graph binds loopback. Graph URLs come from env only. |
| A7 | XSS | PASS | last_error is rendered as React text (Dispatch.tsx:405, EditDialog.tsx:55, Settings.tsx:62). |
| A8 | Deserialization | N/A | Plain JSON only. |
| A9 | Known Vulns | PASS | Dependency scan clean. |
| A10 | Logging | PASS | No tokens or secrets are logged. Retry is audited (calendar_sync.py:278-286). httpx INFO logs include tech emails (INFO). |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Browser to API (status, retry) | Unauthenticated or portal caller | Spoofing / EoP | No session or a portal session | require(P.SCHEDULE_*) on a staff session | MITIGATED |
| Browser to API (retry) | Low-privilege requeue | EoP | read_only or billing POSTs retry | Needs schedule:write | MITIGATED |
| API to DB | Cross-org sync rows | Info disclosure | Guess an appointment id | Forced RLS org_scope plus Scope.apply; 404 when not visible | MITIGATED |
| API to DB (busy cache) | Busy times visible to staff | Info disclosure | GET /availability | Times and status only, no subject or location | MITIGATED |
| Settings toggle | Non-admin enables sync | Tampering | PATCH /api/settings | config:manage, admin only, audited | MITIGATED |
| Worker to Graph (URL) | Path injection via User.email | Tampering | Admin sets an email containing / ? # % | EmailStr partial, RBAC calendar scope, no encoding | PARTIAL |
| Worker to Graph (SSRF) | Redirect token traffic | Tampering | GRAPH_BASE_URL or GRAPH_LOGIN_URL | Env only, operator trust | MITIGATED |
| Worker to Graph (content) | Ticket data in Outlook | Info disclosure | Event body | Fixed payload: id, link, private | MITIGATED |
| Graph to PSA (errors) | Graph error body shown | Info disclosure | last_error | Truncated, but shown to all schedule:read roles | PARTIAL |
| Graph to PSA (busy) | Hostile busy data | Tampering | Long status string | Range check; batch rollback | PARTIAL |
| Worker concurrency | Duplicate or lost events | DoS | Two workers or a crash | skip_locked lease, desired_version, transactionId | MITIGATED |
| Retry abuse | Graph call flood | DoS | Loop retry | Failed-state only, max 6 attempts, backoff | MITIGATED |
| Dev tools | fake_graph or spike in production | EoP | Run against production | Not in image, loopback bind | MITIGATED |
| Migration grants | Excess DB privilege | EoP | App role | S/I/U, plus DELETE on busy_blocks (owner-approved) | MITIGATED |

## Attack Surface
- **Routes (staff session only)**
  - GET /api/calendar-sync/status (schedule:read)
  - POST /api/appointments/{id}/sync/retry (schedule:write, audited)
  - GET /api/availability: outlook_busy and outlook_fetched_at (schedule:read)
  - Appointment payloads: sync state
  - PATCH /api/settings: outlook_sync_enabled (config:manage, admin only)
- **Worker only**
  - push_pending: POST/PATCH/DELETE /users/{email}/events
  - refresh_busy: POST /users/{email}/calendar/getSchedule (batches of 20)
  - OAuth token: {GRAPH_LOGIN_URL}/{tenant}/oauth2/v2.0/token
- **Data**
  - appointment_sync (forced RLS)
  - busy_blocks and calendar_busy_status (staff data, no RLS)
  - settings.outlook_sync_enabled (default false)
- **Operator config:** GRAPH_*, PUBLIC_URL, MAIL_MAILBOX
- **User-influenced Graph inputs:** User.email (set by admin), ticket_id (int), appointment times
- **Dev tools:** backend/dev/fake_graph.py and graph_calendar_spike.py, outside the image

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A1:Injection | LOW | The Graph URL is built from the raw User.email with no encoding. EmailStr accepts / ? # % in the local part (verified: 'a/b@x.com' validates), so an admin-set email can redirect the worker's event requests to a different Graph path. RBAC calendar scope and the event-shaped body limit the impact. | backend/app/mail/graph.py:166 | URL-encode the user segment (urllib.parse.quote(user, safe='@')) or reject emails containing / ? # % or whitespace in graph.py and eligible_users(). Add a test with a/b@x.com. | OPEN |
| SEC-002 | A3:Sensitive Data | LOW | Raw Graph/AAD error text (up to 300 chars) and unexpected exception text are stored in last_error and returned to every schedule:read role. They can include tenant or app ids, request ids, or SQL/driver text. | backend/app/mail/graph.py:171-175; backend/app/calendar_sync.py:147,399-401 | Store a short code with the HTTP status (e.g. 'Graph 403') in last_error. Log the full detail server-side only, and store just the class name for unexpected exceptions. | OPEN |
| SEC-003 | A6:Misconfiguration | INFO | GRAPH_BASE_URL and GRAPH_LOGIN_URL are not checked for https; the client secret is POSTed to the login URL. They are set by the operator only. | backend/app/mail/graph.py:132-139 | Warn at startup if either URL is not https and not loopback. | OPEN |
| SEC-004 | A6:Misconfiguration | INFO | public_url defaults to http://localhost:8000, so Outlook events get a useless link if it is not set. | backend/app/config.py:17 | Warn, or refuse to enable sync, while public_url is the default. | OPEN |
| SEC-005 | A10:Logging | INFO | Worker basicConfig at INFO lets the httpx logger record Graph request URLs, which contain tech email addresses. | backend/app/worker.py:143 | Set logging.getLogger('httpx') to WARNING. | OPEN |
| SEC-006 | A8:Deserialization | INFO | Graph busy status is stored unvalidated in String(32). An unexpected long value fails and rolls back the batch. | backend/app/mail/graph.py:228 | Whitelist busy, tentative, oof and workingElsewhere, and map anything else to busy. | OPEN |
