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
