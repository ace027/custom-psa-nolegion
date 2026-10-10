# Phase 2: Security Review

**Verdict**: PASS
**Unresolved blockers for ship**: 0

## OWASP Top 10
| Item | Result | Evidence |
|---|---|---|
| A01 Broken Access Control | PASS | Every route uses require(); approve/reject are admin-only and re-checked in scheduling.py; creating time off for someone else needs an approver; cancel is owner or approver; schedules are self or approver; appointments are scoped through ctx.scope and forced RLS. Decision notes are now redacted (F1 fixed). |
| A02 Cryptographic Failures | N/A | No crypto in this phase |
| A03 Injection | PASS | SQLAlchemy expressions only; the timezone goes through ZoneInfo, and traversal strings are rejected |
| A04 Insecure Design | WARN | The pending queue can be flooded and is truncated without notice (LOW, deferred); admins auto-approve their own time off (accepted by design) |
| A05 Security Misconfiguration | PASS | An OverflowError on extreme datetimes caused a 500; times are now bounded to 1970–2200 and return 422 (F2 fixed) |
| A06 Vulnerable Components | PASS | 0 dependency findings |
| A07 Auth Failures | N/A | Existing session layer, plus the X-Requested-With check on writes |
| A08 Data Integrity | PASS | Status transitions enforced in the app with DB check constraints; there is no DELETE grant |
| A09 Logging | PASS | All 7 write actions are audited in the same transaction |
| A10 SSRF | N/A | No outbound requests |

## STRIDE
| Boundary | Threat | Category | Attack Vector | Mitigation | Status |
|---|---|---|---|---|---|
| Browser→API | Cross-site write | Spoofing | Cross-site POST | SameSite cookie and the X-Requested-With check | MITIGATED |
| Browser→API | Tech approves own time off | Elevation | POST /time-off/{id}/approve | TIMEOFF_APPROVE is admin-only, checked twice | MITIGATED |
| Browser→API | Time off created or cancelled for others | Elevation/Tampering | POST /time-off, /cancel | Approver or owner checks | MITIGATED |
| Browser→API | Another user's reason or decision note | Info disclosure | GET /time-off | Both are redacted for anyone who is neither the owner nor an approver | MITIGATED |
| Browser→API | Concurrent time-off decisions | Tampering | Parallel requests | SELECT FOR UPDATE | MITIGATED |
| Browser→API | Concurrent appointment move and cancel | Tampering | Parallel requests | SELECT FOR UPDATE on the write paths | MITIGATED |
| Browser→API | Extreme datetimes cause a 500 | DoS | from=9999-12-30 | Bounded to 1970–2200 and returns 422 | MITIGATED |
| Browser→API | Large ranges | DoS | /availability, /appointments | 31- and 62-day caps, 50-id cap, row limits | PARTIAL |
| Browser→API | Pending-request flood | DoS | Repeated POST /time-off | None | UNMITIGATED (LOW) |
| Browser→API | Approver repudiation | Repudiation | Approve/reject | Audited with before and after snapshots | MITIGATED |
| API→DB | Cross-org appointment access | Info disclosure | Another org's id | Scope.apply, forced RLS org_scope, composite FK | MITIGATED |
| API→DB | Staff tables have no RLS | Elevation | SQL-level compromise | App checks only; no DELETE grant | PARTIAL |

## Attack Surface
All routes are under /api and are staff-only. Unsafe methods also need the X-Requested-With: psa header.
- GET/PUT /users/{id}/schedule: SCHEDULE_READ / SCHEDULE_WRITE; self or approver.
- GET /time-off: SCHEDULE_READ; query user_id, status, from/to (aware, 1970–2200); limit 1000.
- POST /time-off: SCHEDULE_WRITE; creating for another user needs an approver; at most 366 days; reason ≤500 characters.
- POST /time-off/{id}/approve and /reject: TIMEOFF_APPROVE; only while pending; note ≤500 characters.
- POST /time-off/{id}/cancel: SCHEDULE_WRITE; owner or approver.
- GET /appointments: SCHEDULE_READ; scoped; range at most 62 days unless ticket_id is given.
- POST /appointments: SCHEDULE_WRITE; scoped ticket lookup; at most 24 hours.
- GET/PATCH /appointments/{id}, POST /appointments/{id}/cancel: SCHEDULE_READ / SCHEDULE_WRITE; scoped; writes lock the row.
- GET /availability: SCHEDULE_READ; at most 31 days; at most 50 user ids.

### Dependency Vulnerability Findings
_none_

### Secret Detection Findings
_none_

### Supply Chain Findings
_none_

## Findings
| ID | OWASP Cat | Severity | Finding | File(s) | Remediation | Status |
|----|-----------|----------|---------|---------|-------------|--------|
| SEC-001 | A01:Broken Access Control | MEDIUM | FIXED: billing and read_only users could read time-off decision notes for other users. Notes often restate the private reason. | backend/app/scheduling.py:time_off_view | decision_note is now redacted by the same rule as reason. Tested in test_time_off_request_approve_reject. | OPEN |
| SEC-002 | A05:Security Misconfiguration | LOW | FIXED: datetimes near year 1 or 9999 raised OverflowError, which returned a 500. | backend/app/scheduling.py:_aware | Times must now fall between 1970 and 2200 or the request gets a 422. Tested in test_availability_validation. | OPEN |
| SEC-003 | A04:Insecure Design | LOW | FIXED: appointment update and cancel read the row without a lock. A concurrent move and cancel could interleave. | backend/app/scheduling.py:get_appointment | The write paths now use get_appointment(lock=True), which runs SELECT FOR UPDATE. | OPEN |
| SEC-004 | A04:Insecure Design | LOW | Pending time off has no per-user cap and no overlap check. GET /time-off silently truncates at 1000 rows. | backend/app/scheduling.py:create_time_off, list_time_off | Deferred: add a pending-request cap or pagination when the list UI lands. | OPEN |
| SEC-005 | A04:Insecure Design | LOW | When no ids are given, availability covers every active admin and tech with no cap. The work is N+1 per user. | backend/app/scheduling.py:availability_for | Deferred. This is bounded by MSP headcount; batch the queries if it becomes slow. | OPEN |
| SEC-006 | A01:Broken Access Control | INFO | Busy-time checks use org-scoped appointment queries, and client_visible is not enforced anywhere yet. Both matter only once scoped principals or portal appointment routes exist. | backend/app/scheduling.py:_busy_appointments | Before scoped principals or a portal route ship, compute busy time without the org scope and filter on client_visible. | OPEN |
| SEC-007 | A08:Data Integrity | INFO | The staff tables user_time_off and user_work_hours have no RLS. Status transitions are enforced only in the app. | backend/alembic/versions/0024_scheduling.py | Optional: add a trigger that guards status transitions. | OPEN |
| SEC-008 | A04:Insecure Design | INFO | An admin's own time off is approved automatically, and a tech can cancel approved time off without re-approval. | backend/app/scheduling.py:create_time_off, cancel_time_off | Accepted. This matches the owner's design decision. | OPEN |
| SEC-009 | A09:Logging | INFO | Time-off reasons and appointment notes are kept in audit snapshots, which only admins can read. | backend/app/audit.py:REDACTED_KEYS | Document a retention policy if reasons may hold health data. | OPEN |
