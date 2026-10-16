# Retrospective Log

Retrospective findings from completed phases and milestones.
Referenced by `/triad:plan` for continuous improvement.

## Phase 3: Dispatch board — 2026-10-10

### Key Findings
Went well:
- 03-01 was complete on the first attempt.
- The plan critique caught a vague plan ("and so on").
- The review found real accessibility problems: an Undo toast on a fixed 8-second timer (F-001) and a focus ring at about 1.5:1 contrast (F-003, found only by design-ui-designer).
- Review passed with 18 of 18 checks, security was PASS, and all 6 ship gates passed.
- Results the tools reported as "not run" were verified by hand (polish tests; the CI timezone fix was proven in UTC+14).

Didn't work:
- 03-03 took 4 attempts:
  - Attempt 1: the container lacked Playwright's Chromium build, and the Vite dev server broke react-big-calendar's drag-and-drop addon while unit tests and the build passed.
  - Attempts 2 and 3: Partial, because the agent flagged an approved fix to Dispatch.tsx, outside the plan's files.
  - Attempt 4: the commit held only the SUMMARY (943a1dc).
- Agents used escalation types that aren't allowed.
- The review took 3 cycles (phases 1 and 2 took 1). F-001 went a cycle without being fixed, and the F-003 fix was never tested.
- The open-finding counts disagree (7, 4 or 4).
- Tool friction recurred: SPEND.json breaks the clean-tree gate; orchestrator edits are logged to PREFERENCES.md; Postgres must be restarted after each worker restart.
- CI failed between 00:00 and 05:00 UTC on Chicago-vs-UTC date tests.
- smoke.spec.ts "ticket lifecycle" still fails (not caused by phase 3).

### Action Items
| # | Action | Priority | Evidence |
|---|---|---|---|
| 1 | Plans using third-party UI libraries verify against the real Vite dev server, not only vitest and the build | High | 03-03 attempt 1, 4012615 |
| 2 | Plans touching e2e list scripts/e2e.sh and any file a fix may need in files_modified | High | O-014, O-015 |
| 3 | A build commit that contains only the SUMMARY fails the plan | High | 943a1dc vs 590aa90 |
| 4 | Stop the tools logging orchestrator edits as manual-edit preferences | Medium | Phases 2 and 3 |
| 5 | Exclude .planning/SPEND.json from the ship clean-tree gate | Medium | Phase 3 ship |
| 6 | Review fixes must run the checks; a major finding unfixed after one cycle goes to a different agent | Medium | FIXES.md, F-001, F-003 |
| 7 | The polish tool finds the test and typecheck commands, or fails instead of reporting not run | Medium | 03-POLISH.md |
| 8 | Run date-dependent tests in a non-UTC timezone in CI; use biz_today() | Medium | f69cd2f |
| 9 | Fix or triage smoke.spec.ts "ticket lifecycle" (line 50) | Medium | smoke.spec.ts:50 |
| 10 | List the allowed escalation types in the build prompt | Low | 03-03 escalations |
| 11 | Settle the open-finding count; decide on F-002 and F-004 | Low | 03-REVIEW.md |
| 12 | Prefer engineering-frontend-developer for UI-heavy plans and engineering-senior-developer for backend and logic plans (thin evidence) | Low | O-011 to O-016 |
| 13 | Include design-ui-designer in reviews of UI phases | Low | O-019, F-003 |

### Metrics
- Plans completed: 3
- Build attempts: 6 for 3 plans (03-03 took 4: 1 failed, 2 partial, 1 complete)
- Review pass rate: 1/1 (100%), 3 cycles, 2 must-fix fixed, 7 minor left open
- Security: PASS, 0 critical/high, 1 medium, 3 low, 1 info
- Escalations: 2 rounds on 03-03 (out-of-scope edit), 0 blockers, all approved
- Agents used: 2 builders (engineering-senior-developer, engineering-frontend-developer), 4 reviewers (testing-qa-verification-specialist, engineering-frontend-developer, design-ui-designer, engineering-senior-developer), 1 security reviewer
- Files modified: 28
- Ship gates: 6/6

---

## Phase 4: Outlook push + free/busy — 2026-10-15

### Key Findings
**Went well**
- 4/4 plans complete. Review PASSED in 2 cycles, with 6/6 must-fix findings fixed.
- Review fix commits carried real code and tests (c76fc01, 117d24d), unlike phase 3.
- Security review PASS. SEC-001 and SEC-002 (LOW) fixed with tests in 52dbadf.
- Backend 899 and frontend 199 tests pass, e2e dispatch 4/4. Ship gates 6/6. CI green on the first run of PR #7 (merged c383939).
- The boundary grep held "only the worker calls Graph" in every run.

**Didn't work**
- Two-wave mode put 04-04 in Wave A ahead of 04-03, which it depends on, so nothing ran. --single-wave fixed it.
- Migration 0025 (04-02) lacked the DELETE grant that 04-03 needed, so 04-03 was BLOCKED until the owner approved adding it.
- One bug (a getSchedule error mapped to an empty list, wiping cached blocks) produced 5 of 6 must-fix findings. A 04-01 test asserted the buggy behavior.
- Recurring from phase 3:
  - SUMMARY-only build commit (9388478, code committed as 42478af)
  - SPEND.json breaks the clean-tree gate
  - orchestrator edits logged as manual-edit preferences
  - invalid escalation type

### Action Items
| # | Action | Priority | Evidence |
|---|---|---|---|
| 1 | build_phase must honor plan dependencies when assigning waves; use single-wave when plans chain | High | Phase 4 first build, legion.log |
| 2 | A build commit containing only the SUMMARY fails the plan (recurred from phase 3) | High | 9388478 vs 42478af; 943a1dc vs 590aa90 |
| 3 | When planning, check that a schema/migration plan grants every privilege later waves need | High | O-023, 0025 busy_blocks DELETE |
| 4 | Tests and reviews flag errors mapped to empty data that feeds a destructive refresh | Medium | F-001..F-005, 04-01 test, c76fc01 |
| 5 | List the allowed escalation types in the build prompt; an owner-approved edit to another plan's file is not an escalation (recurred) | Medium | O-024 |
| 6 | Exclude .planning/SPEND.json from the ship clean-tree gate (recurred) | Medium | Phase 4 ship |
| 7 | Stop logging orchestrator edits as manual-edit preferences (recurred) | Medium | D-007..D-012, reverted uncommitted |
| 8 | Explain or fix the review pass rate metric (0/1 shown for a PASSED review) | Low | Phase 4 metrics |
| 9 | Triage the 23 deferred findings and 4 INFO security items, starting with the hot-spot files | Low | 04-REVIEW.md, SECURITY-REVIEW.md |
| 10 | Run the real-tenant spike and the other owner checks in Phase 14: Verify | Low | .planning/VERIFY.md, PRF-001 |

### Metrics
- Plans completed: 4
- Review pass rate: 0/1 (0%)
- Escalations: 1 (0 blockers)
- Agents used: 2 (engineering-backend-architect, engineering-frontend-developer)
- Files modified: 27

---

## Phase 5: Client confirmations + on-call — 2026-10-16

### Key Findings
Went well: 5/5 plans complete; review PASSED in 1 cycle with 0 must-fix; parallel waves with no shared files had no conflicts; PR #9 merged green first time; owner decisions escalated (staff-only on-call, cancel email after hide/mute); security PASS with LOW fixes in c6d50a9; polish no changes.
Didn't work: 3/5 plans re-run (05-01, 05-03, 05-05); 05-01 and 05-05 marked Partial despite passing verification; build again committed only SUMMARY.md for 05-01 (3ae105e) and 05-05 (55d20c8) — code committed by hand (885485f, 80938c9), and 05-02 (786feea) depended on uncommitted 05-01 code; 05-03 BLOCKED by a planning gap (oncall tables given organization_id/RLS though staff-internal like user_time_off); conftest reset missed new tables; ship clean-tree gate tripped by SPEND.json and SHIP-REPORT.md; backend suite now ~12 min.

### Action Items
| # | Action | Priority | Evidence |
|---|--------|----------|----------|
| 1 | Build must fail or auto-commit when code is left uncommitted after the SUMMARY commit; verify a plan's dependencies are committed before the next wave starts | High | 3ae105e, 55d20c8, 885485f, 80938c9, 786feea; recurred from Phase 4 |
| 2 | Schema-plan checklist: mirror tenancy/RLS of comparable tables, decide staff-internal vs client-scoped, and register new tables in tests/conftest.py reset list | High | 05-03 BLOCKED (O-034), 885485f, c6d50a9 |
| 3 | A plan whose verification commands all pass is Complete; agent uncertainty goes in Issues | Medium | 05-01-SUMMARY, 05-05-SUMMARY, O-031, O-037 |
| 4 | Exclude .planning/SPEND.json and SHIP-REPORT.md from the clean-tree gate; ignore stale runner notices after gates pass | Medium | Phase 4 and Phase 5 ship |
| 5 | Investigate backend suite runtime (per-test TRUNCATE, IO wait) | Medium | 703-717s for 970 tests vs ~3.5 min earlier |
| 6 | When parallel plans touch the same frontend area, re-run plan-level tests after the sibling plan lands | Low | 05-05 Dispatch.test.tsx vs 05-04 |
| 7 | Triage the 27 deferred review items, hot-spot files first | Low | 05-REVIEW.md deferred, hot spots |

### Metrics
- Plans completed: 5
- Review pass rate: 1/1 (100%)
- Escalations: 0 (0 blockers)
- Agents used: 3 (engineering-backend-architect, engineering-senior-developer, engineering-frontend-developer)
- Files modified: 28

---
