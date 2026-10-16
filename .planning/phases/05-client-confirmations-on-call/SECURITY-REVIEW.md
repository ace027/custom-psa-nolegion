# Phase 5: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| # | Category | Result | Evidence |
|---|---|---|---|
| A1 | Injection | PASS | ORM/bound params; email is sent via Graph JSON (no raw SMTP headers); subject capped |
| A2 | Broken Auth | PASS | every oncall route require(SCHEDULE_READ/WRITE); portal route portal_required |
| A3 | Sensitive Data | WARN | body excludes notes/cancel_reason; raw exception text in notice reason (F3); recipient in audit (F4) |
| A4 | XXE | N/A | no XML |
| A5 | Access Control | PASS | portal uses _visible + org join + RLS scope; oncall staff-only |
| A6 | Misconfiguration | PASS | forced RLS on appointment_notices; minimal grants; emails default off |
| A7 | XSS | PASS | no dangerouslySetInnerHTML/innerHTML; text emails |
| A8 | Deserialization | N/A | pydantic-typed JSON only |
| A9 | Known Vulns | PASS | 0 dependency findings, no new deps |
| A10 | Logging | PASS | all oncall writes and sends audited; failures log.exception |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Staff browser→API | Unauthorized on-call writes | E | billing/read_only calling writes | require(SCHEDULE_WRITE) | MITIGATED |
| Staff browser→API | Forged members/users | T | unknown/inactive ids | _check_users, unique/FK | MITIGATED |
| Staff browser→API | Large schedule window | D | multi-year window | 31-day cap | MITIGATED |
| Staff browser→API | 500 from extreme anchor_date | D | anchor 9999-12-31 | none | UNMITIGATED (F1) |
| Staff browser→API | Exception text in notice reason | I | ClientNoticeOut.reason | staff-only, 500 cap | PARTIAL (F3) |
| Portal→portal API | Cross-org/cross-contact read | I | other contacts' tickets | _visible, org join, RLS | MITIGATED |
| Portal→portal API | Notes leak | I | serialization | PortalAppointmentOut has no notes | MITIGATED |
| Portal→portal API | Reach on-call data | E | portal cookie on /api/oncall | staff require() | MITIGATED |
| Worker→email | Header injection via subject | T | CRLF | Graph JSON, caps | MITIGATED (F2) |
| Worker→email | Email flood | D | repeated edits | unique pending + debounce | MITIGATED |
| DB role→tables | Cross-client notices | I | unscoped session | forced RLS | MITIGATED |
| DB role→tables | No RLS on oncall_* | I | future portal bug | app-layer perms (owner decision) | PARTIAL (INFO) |

## Attack Surface
- Routes: GET/POST /api/oncall/rotations, PATCH /api/oncall/rotations/{id}, GET/POST /api/oncall/rotations/{id}/overrides, DELETE /api/oncall/overrides/{id}, GET /api/oncall/now, GET /api/oncall/schedule (schedule:read for reads, schedule:write for writes); GET /api/portal/appointments (portal session, org + ticket visibility).
- Worker: client_notices.send_due (scope all, batch 50, SKIP LOCKED, only when mail configured).
- Tables: appointment_notices (forced RLS); oncall_rotations/members/overrides (staff-internal, no RLS).
- Columns: appointments.notify_client, settings.appointment_emails_enabled (default off).

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A4:Insecure Design | LOW | anchor_date unbounded: a schedule:write user can set an anchor near 9999-12-31 and /oncall/schedule raises OverflowError (500) for everyone until edited. | backend/app/oncall_schemas.py:21,41; backend/app/oncall.py:45-48,125 | Bound anchor_date (2000-2100) in RotationCreate/RotationPatch; catch OverflowError in schedule() and return 422. | FIXED |
| SEC-002 | A3:Sensitive Data | LOW | Notice skip reason stores raw exception text visible to staff via client_notice.reason. | backend/app/client_notices.py:203 | Store a fixed 'error: see worker log' (with the class name) and keep details in log.exception. | FIXED |
| SEC-003 | A1:Injection | INFO | ticket.subject control characters are not normalised in the email subject/body; harmless over the Graph JSON API but would become header injection on raw SMTP. | backend/app/client_notices.py:124,143 | Use ' '.join(ticket.subject.split()) in _render. | FIXED |
| SEC-004 | A3:Sensitive Data | INFO | Client email address stored in audit detail.to (PII retention). | backend/app/client_notices.py:266 | Store contact_id/email_message_id instead, or confirm audit retention covers erasure. | OPEN |
| SEC-005 | A5:Access Control | INFO | oncall_* tables have no RLS by owner decision; protection is app-layer only. | backend/alembic/versions/0026_client_notices_oncall.py:125-128 | Optional test that portal routes never touch Oncall* models. | OPEN |
