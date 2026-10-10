# Phase 3: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| # | Category | Result | Evidence |
|---|---|---|---|
| A1 | Injection | PASS | SQLAlchemy-parameterised queries (scheduling.py:336-346, 503-516); user_ids int-parsed and capped (routers/scheduling.py:220-226); e2e.sh DB name from numeric $$ |
| A2 | Broken Auth | PASS | Every route uses require(P.…); dev-login 404 unless enabled and not production (routers/auth.py:94) |
| A3 | Sensitive Data | WARN | reason/decision_note redacted (scheduling.py:234-246); pending time-off windows visible to all staff roles (SEC F2) |
| A4 | XXE | N/A | No XML parsing |
| A5 | Access Control | PASS | _scoped + forced RLS (scheduling.py:351, 0024_scheduling.py:100-102); SCHEDULE_WRITE / TIMEOFF_APPROVE enforced in route and service |
| A6 | Misconfiguration | WARN | e2e.sh creates roles with fixed dev passwords if missing (e2e.sh:45-55); input models ignore unknown fields |
| A7 | XSS | PASS | No dangerouslySetInnerHTML/innerHTML/eval; user text rendered as React text and string tooltips (Dispatch.tsx:79-84, 257-260) |
| A8 | Deserialization | PASS | Pydantic JSON models only, AwareDatetime on writes |
| A9 | Known Vulns | PASS | Scan: 0 high/critical dependency findings |
| A10 | Logging | PASS | Writes audited in the same transaction (scheduling.py:283, 300, 323, 414, 449, 472) |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Browser → API (GET /appointments?with_conflicts) | Cross-org data via conflicts | Information disclosure | Crafted tech_id/ticket_id | _scoped on list and busy queries; conflicts return only kind and ids; RLS | MITIGATED |
| Browser → API | Range cap bypass | Denial of service | Omit from/to with with_conflicts | scheduling.py:497 rejects missing bounds or >8 days first | MITIGATED |
| Browser → API | Per-row query amplification | Denial of service | 8-day window, up to 2000 rows, ~6+ queries each | 8-day cap and 2000-row limit; no batching or rate limit | PARTIAL |
| API read paths | Unapproved leave exposed | Information disclosure | GET /availability time_off_pending; conflict kind time_off_pending | Reasons and notes redacted; windows visible to all staff | PARTIAL |
| API write paths | Mass assignment | Tampering / EoP | Client sends status, organization_id, created_by | Fields not declared, so ignored; org taken from ticket; PATCH rejects nulls | MITIGATED |
| API write paths | Write without role | Elevation of privilege | read_only/billing POST or PATCH | Permission checked in route and service (scheduling.py:288, 313) | MITIGATED |
| Browser rendering | Stored XSS | Tampering | Markup in subject, notes, reason | React escaping, no raw HTML sinks | MITIGATED |
| scripts/e2e.sh → Postgres | Wrong DB dropped / shell injection | Tampering / DoS | $$-based name, E2E_PSQL | Numeric, prefixed name; DROP only that name | MITIGATED |
| scripts/e2e.sh → shared cluster | Weak persistent credentials | Elevation of privilege | Fixed owner_dev/app_dev on roles created if missing | Created only when absent; localhost binds | PARTIAL |
| Vite dev proxy | Proxy target manipulation | Spoofing | E2E_API_PORT | Dev server only; production uses Caddy, API not published | MITIGATED |

## Attack Surface
All routes need an authenticated session and schedule:read unless noted.

- GET/PUT /api/users/{user_id}/schedule: self or approver; PUT needs schedule:write.
- GET /api/time-off (user_id, status, from, to): 1000-row cap; reason and note redacted.
- POST /api/time-off: schedule:write. POST /api/time-off/{id}/approve and /reject: timeoff:approve. POST /api/time-off/{id}/cancel: owner or admin.
- GET /api/appointments (tech_id, ticket_id, from, to, include_cancelled, with_conflicts): 62-day cap, 8 days with conflicts, 2000 rows.
- POST /api/appointments, PATCH /api/appointments/{id} (row-locked), POST /api/appointments/{id}/cancel: schedule:write.
- GET /api/appointments/{id}: always computes conflicts.
- GET /api/availability (from, to required, at most 31 days; user_ids at most 50): returns time_off_pending windows.

Client entry points:
- Dispatch board (Dispatch.tsx): drag and resize send PATCH; undo sends PATCH.
- BookingDialog.tsx, EditDialog.tsx, TicketAppointmentsCard.tsx.
- Vite /api proxy (dev only).
- Tooling: scripts/e2e.sh, playwright.config.ts (E2E_BASE_URL, CHROMIUM_PATH).

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A6:Misconfiguration (resource consumption) | MEDIUM | GET /appointments with with_conflicts runs conflicts_for and appointment_view lookups per row. An 8-day window can return up to 2000 rows, so one request can issue on the order of 10k queries. | backend/app/scheduling.py:365-387, 484-516, 551-572; backend/app/routers/scheduling.py:153 | Prefetch techs, work hours, holidays, time-off and appointments once per request for the whole range. Lower the row limit when with_conflicts is set, and add a rate limit. Same item as review F-001. | OPEN |
| SEC-002 | A3:Sensitive Data | LOW | time_off_pending windows and pending time-off ids are visible to every staff role, including billing and read_only. Reasons and notes stay redacted. | backend/app/scheduling.py:561-562, 601-603; backend/app/scheduling_schemas.py:147 | Return pending windows only to the owner and approvers, or accept this and record the decision in docs/SCHEDULING.md. | OPEN |
| SEC-003 | A6:Misconfiguration | LOW | If psa_owner (BYPASSRLS) and psa_app are missing, e2e.sh creates them with the fixed dev passwords owner_dev and app_dev, and they persist after the run. | scripts/e2e.sh:45-55 | Generate a random password per run, or use per-run roles dropped in cleanup, or refuse to run against a non-localhost Postgres. Document that the script is dev-only. | OPEN |
| SEC-004 | A5:Access Control | LOW | The scheduling input models silently ignore unknown fields. This is not exploitable today, but a field added to a model later could be set by clients without review. | backend/app/scheduling_schemas.py:58-100 | Set model_config = ConfigDict(extra='forbid') on TimeOffIn, AppointmentIn, AppointmentPatch, AppointmentCancel and TimeOffDecision. | OPEN |
| SEC-005 | A7:XSS | INFO | Appointment notes default to client_visible=true and may reach the portal. The portal's rendering was not checked in this review. | backend/app/scheduling_schemas.py (client_visible default) | Confirm the portal escapes appointment notes when it shows them (later portal phase). | OPEN |
