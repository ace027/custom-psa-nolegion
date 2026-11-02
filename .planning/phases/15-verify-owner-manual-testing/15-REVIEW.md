# Phase 15: Verify (owner manual testing) — Review Summary

## Result: ESCALATED

**Cycles Used**: 2
**Reviewers**: testing-qa-verification-specialist, engineering-senior-developer
**Completed**: 2026-11-02

## Findings Summary
- Must-fix (blocker, critical, major) found: 7; fixed: 2; unresolved: 5
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 1
- Hot spots (flagged by 2+ reviewers): `docs/verify/RUNBOOK.md`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | critical | `docs/verify/RUNBOOK.md:97-98` | The real-tenant Outlook spike rows P04-02 and P04-03 (read-only, `--write`, `--write --outside`) are not recorded as pass or fail. Both say "script did not work", and the cause is `ModuleNotFoundError: No module named 'pydantic_settings'`. That error is raised when `dev/graph_calendar_spike.py` imports `app.config` (line 5 of `app/config.py`). Nothing in the file shows a fix, a rerun, or an owner-accepted deferral. P04-04 to P04-06 are marked passing, but that does not cover the spike. | testing-qa-verification-specialist, engineering-senior-developer | 95% | fixed |
| F-002 | major | `docs/verify/RUNBOOK.md:83-89` | The multi-line traceback is gone and the Result is now `fail`, so the Markdown table renders. The note still says the traceback names the Graph spike and asks the owner to "check which script was run". It does not give the cause. The cause is that `dispatch-spike.md` includes a Graph calendar section that must run in the worker container. The suggested fix, `pip install -e .` on the host, goes against that file. | testing-qa-verification-specialist, engineering-senior-developer | 85% | open |
| F-003 | major | `docs/verify/RUNBOOK.md:216` | P14-01 ("Walk through portal-polish.md") has empty Result and Notes cells. It is the only row left blank. | testing-qa-verification-specialist, engineering-senior-developer | 95% | fixed |
| F-004 | major | `docs/verify/RUNBOOK.md:40` | The block-hour rollover decision is still `[ ]`. Its text says "OPEN: owner to either open a fix task for configurable rollover or mark deferred". No fix task and no deferral is recorded. | testing-qa-verification-specialist | 80% | open |
| F-005 | minor | `docs/verify/RUNBOOK.md:203` | Phase 13 links `[kb.md](kb.md)`, but `docs/verify/kb.md` does not exist. Phase 13 is marked N/A because the knowledge base was removed. The `ls` output shows no kb.md. The verify loop only checks that existing files are linked, so it does not catch the dead link. | testing-qa-verification-specialist | 90% | deferred |
| F-006 | critical | `docs/verify/RUNBOOK.md:47-54` | P04-02 and P04-03 now read `fail`, with a fix note, but there is still no rerun and no pass for the real-tenant spike. The success criterion needs `--write` and `--outside` to pass. The runbook also gives the wrong fix. It tells the owner to run `python dev/graph_calendar_spike.py` from a host venv, and to `pip install -e .` if that fails. `docs/verify/dispatch-spike.md` lines 35-44 say the spike needs the Docker stack, not host Python. Its commands are `docker compose run --rm worker python dev/graph_calendar_spike.py ...`. The two docs disagree. | testing-qa-verification-specialist | 85% | open |
| F-007 | major | `docs/verify/RUNBOOK.md:210` | P14-01 is marked `fail` with the note "Not run yet". Nothing failed. The check has not been run. The "Recording failures" section tells the owner to open a `/triad:quick` fix for every `fail`, so this row asks for a fix for something that is not broken. It also counts as a failure in any tally of results. | testing-qa-verification-specialist, engineering-senior-developer | 85% | open |
| F-008 | critical | `docs/verify/RUNBOOK.md:91-92` | P04-02 and P04-03 now read `fail`, with the cause named as a missing `pydantic_settings` install. Nothing shows the install, a rerun, or an owner-accepted deferral. The `--write` and `--write --outside` runs have never been recorded against the real tenant. `pydantic-settings>=2.4` is declared at backend/pyproject.toml:12, so the cause is a local environment gap, not a code bug. The Notes only say "rerun, set pass", which leaves the work undone. | engineering-senior-developer | 90% | open |

## Unresolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-002 | major | `docs/verify/RUNBOOK.md:83-89` | The multi-line traceback is gone and the Result is now `fail`, so the Markdown table renders. The note still says the traceback names the Graph spike and asks the owner to "check which script was run". It does not give the cause. The cause is that `dispatch-spike.md` includes a Graph calendar section that must run in the worker container. The suggested fix, `pip install -e .` on the host, goes against that file. | testing-qa-verification-specialist, engineering-senior-developer | 85% | open |
| F-004 | major | `docs/verify/RUNBOOK.md:40` | The block-hour rollover decision is still `[ ]`. Its text says "OPEN: owner to either open a fix task for configurable rollover or mark deferred". No fix task and no deferral is recorded. | testing-qa-verification-specialist | 80% | open |
| F-006 | critical | `docs/verify/RUNBOOK.md:47-54` | P04-02 and P04-03 now read `fail`, with a fix note, but there is still no rerun and no pass for the real-tenant spike. The success criterion needs `--write` and `--outside` to pass. The runbook also gives the wrong fix. It tells the owner to run `python dev/graph_calendar_spike.py` from a host venv, and to `pip install -e .` if that fails. `docs/verify/dispatch-spike.md` lines 35-44 say the spike needs the Docker stack, not host Python. Its commands are `docker compose run --rm worker python dev/graph_calendar_spike.py ...`. The two docs disagree. | testing-qa-verification-specialist | 85% | open |
| F-007 | major | `docs/verify/RUNBOOK.md:210` | P14-01 is marked `fail` with the note "Not run yet". Nothing failed. The check has not been run. The "Recording failures" section tells the owner to open a `/triad:quick` fix for every `fail`, so this row asks for a fix for something that is not broken. It also counts as a failure in any tally of results. | testing-qa-verification-specialist, engineering-senior-developer | 85% | open |
| F-008 | critical | `docs/verify/RUNBOOK.md:91-92` | P04-02 and P04-03 now read `fail`, with the cause named as a missing `pydantic_settings` install. Nothing shows the install, a rerun, or an owner-accepted deferral. The `--write` and `--write --outside` runs have never been recorded against the real tenant. `pydantic-settings>=2.4` is declared at backend/pyproject.toml:12, so the cause is a local environment gap, not a code bug. The Notes only say "rerun, set pass", which leaves the work undone. | engineering-senior-developer | 90% | open |

## Resolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | critical | `docs/verify/RUNBOOK.md:97-98` | The real-tenant Outlook spike rows P04-02 and P04-03 (read-only, `--write`, `--write --outside`) are not recorded as pass or fail. Both say "script did not work", and the cause is `ModuleNotFoundError: No module named 'pydantic_settings'`. That error is raised when `dev/graph_calendar_spike.py` imports `app.config` (line 5 of `app/config.py`). Nothing in the file shows a fix, a rerun, or an owner-accepted deferral. P04-04 to P04-06 are marked passing, but that does not cover the spike. | testing-qa-verification-specialist, engineering-senior-developer | 95% | fixed |
| F-003 | major | `docs/verify/RUNBOOK.md:216` | P14-01 ("Walk through portal-polish.md") has empty Result and Notes cells. It is the only row left blank. | testing-qa-verification-specialist, engineering-senior-developer | 95% | fixed |
| F-005 | minor | `docs/verify/RUNBOOK.md:203` | Phase 13 links `[kb.md](kb.md)`, but `docs/verify/kb.md` does not exist. Phase 13 is marked N/A because the knowledge base was removed. The `ls` output shows no kb.md. The verify loop only checks that existing files are linked, so it does not catch the dead link. | testing-qa-verification-specialist | 90% | deferred |

## Recommendation
Fix the unresolved findings by hand, accept the phase as is, or investigate further.

<escalation>
severity: blocker
type: quality
decision: unresolved critical F-006 in docs/verify/RUNBOOK.md
context: P04-02 and P04-03 now read `fail`, with a fix note, but there is still no rerun and no pass for the real-tenant spike. The success criterion needs `--write` and `--outside` to pass. The runbook also gives the wrong fix. It tells the owner to run `python dev/graph_calendar_spike.py` from a host venv, and to `pip install -e .` if that fails. `docs/verify/dispatch-spike.md` lines 35-44 say the spike needs the Docker stack, not host Python. Its commands are `docker compose run --rm worker python dev/graph_calendar_spike.py ...`. The two docs disagree.
</escalation>

<escalation>
severity: blocker
type: quality
decision: unresolved critical F-008 in docs/verify/RUNBOOK.md
context: P04-02 and P04-03 now read `fail`, with the cause named as a missing `pydantic_settings` install. Nothing shows the install, a rerun, or an owner-accepted deferral. The `--write` and `--write --outside` runs have never been recorded against the real tenant. `pydantic-settings>=2.4` is declared at backend/pyproject.toml:12, so the cause is a local environment gap, not a code bug. The Notes only say "rerun, set pass", which leaves the work undone.
</escalation>

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 1, engineering-senior-developer: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 2, engineering-senior-developer: **NEEDS WORK**

## Suggestions (Not Required)
- F-005 `docs/verify/RUNBOOK.md`: Phase 13 links `[kb.md](kb.md)`, but `docs/verify/kb.md` does not exist. Phase 13 is marked N/A because the knowledge base was removed. The `ls` output shows no kb.md. The verify loop only checks that existing files are linked, so it does not catch the dead link. (fix: Delete the "Checklists: [kb.md](kb.md)" line and keep the N/A rows.)

## Deferred (Medium Confidence)
- `docs/verify/RUNBOOK.md` [minor, 60%]: P01-01's Result is "All checks pass", which is non-standard. Its Notes describe a requirement: flat-fee (AYCE) clients should attach all time to the flat-fee agreement with no extra billing, so profitability can be tracked. The text reads as a behaviour request, not a confirmation, so it is unclear whether the current code meets it.

## Fixes Applied
- cycle 1: engineering-senior-developer on F-001, F-002, F-003, F-004 (partial); checks 9/9 passed

## Cycle Delta
- cycle 1: 4 must-fix, 1 suggestions, 1 deferred, 0 dropped (low confidence)
- cycle 2: 5 must-fix (resolved 2, new 3, unchanged 2), 0 suggestions, 0 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
