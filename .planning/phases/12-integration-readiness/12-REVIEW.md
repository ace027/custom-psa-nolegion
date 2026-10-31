# Phase 12: Integration readiness — Review Summary

## Result: STALE LOOP ABORTED

**Cycles Used**: 3
**Reviewers**: testing-qa-verification-specialist, testing-api-tester, engineering-backend-architect, design-ux-researcher
**Evaluators**: code-quality, ui-ux, integration, business-logic
**Completed**: 2026-10-31

## Findings Summary
- Must-fix (blocker, critical, major) found: 1; fixed: 0; unresolved: 1
- Suggestions (minor, advisory): 1
- Deferred (confidence 50-79%): 14
- Hot spots (flagged by 2+ reviewers): `frontend/src/pages/TicketDetail.tsx`, `frontend/src/clientScope.ts`

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | advisory | `backend/app/main.py:71-77` | The CSRF early-return 403 for a missing `X-Requested-With` header skips the response header block at lines 79-81. That response has no `X-Request-ID`, `X-Content-Type-Options` or `Cache-Control: no-store`. The `request_id_var` is set, but the id is never echoed back. | testing-api-tester | 85% | deferred |
| F-002 | major | `frontend/src/clientScope.ts:23-34` | F-002 is still not fixed. `useClientScope` is imported only by `frontend/src/IntegrationReadiness.test.tsx`. No page or component calls it. Pages still call `clientApiPath` and `clientRoute` directly, about 54 times across 18 non-test files outside `clientScope.ts`. `main.tsx:18` mounts `ClientScopeProvider value={null}`, so the provider carries no scope. | evaluator:code-quality | 85% | open |

## Unresolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-002 | major | `frontend/src/clientScope.ts:23-34` | F-002 is still not fixed. `useClientScope` is imported only by `frontend/src/IntegrationReadiness.test.tsx`. No page or component calls it. Pages still call `clientApiPath` and `clientRoute` directly, about 54 times across 18 non-test files outside `clientScope.ts`. `main.tsx:18` mounts `ClientScopeProvider value={null}`, so the provider carries no scope. | evaluator:code-quality | 85% | open |

## Resolved Findings
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | advisory | `backend/app/main.py:71-77` | The CSRF early-return 403 for a missing `X-Requested-With` header skips the response header block at lines 79-81. That response has no `X-Request-ID`, `X-Content-Type-Options` or `Cache-Control: no-store`. The `request_id_var` is set, but the id is never echoed back. | testing-api-tester | 85% | deferred |

## Recommendation
Two re-reviews in a row found the same issues. Fix them by hand, or re-plan the affected work.

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **PASS**
- Cycle 1, testing-api-tester: **PASS**
- Cycle 1, engineering-backend-architect: **PASS**
- Cycle 1, design-ux-researcher: **PASS**
- Cycle 1, evaluator:code-quality: **NEEDS WORK**
- Cycle 1, evaluator:ui-ux: **PASS**
- Cycle 1, evaluator:integration: **NEEDS WORK**
- Cycle 1, evaluator:business-logic: **NEEDS WORK**
- Cycle 2, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 2, testing-api-tester: **NEEDS WORK**
- Cycle 2, engineering-backend-architect: **NEEDS WORK**
- Cycle 2, design-ux-researcher: **NEEDS WORK**
- Cycle 2, evaluator:code-quality: **NEEDS WORK**
- Cycle 3, testing-qa-verification-specialist: **NEEDS WORK**
- Cycle 3, testing-api-tester: **NEEDS WORK**
- Cycle 3, engineering-backend-architect: **NEEDS WORK**
- Cycle 3, design-ux-researcher: **NEEDS WORK**
- Cycle 3, evaluator:code-quality: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `backend/app/main.py`: The CSRF early-return 403 for a missing `X-Requested-With` header skips the response header block at lines 79-81. That response has no `X-Request-ID`, `X-Content-Type-Options` or `Cache-Control: no-store`. The `request_id_var` is set, but the id is never echoed back. (fix: Build the 403 `JSONResponse`, then set the same three headers on it before returning. Alternatively, move the header-setting into a helper used by both paths.)

## Deferred (Medium Confidence)
- `frontend/src/pages/TicketDetail.tsx` [minor, 70%]: AI notes use `bg-violet-100` for the card, and the "AI" badge inside them also uses `bg-violet-100`. The badge has no background contrast against its card, so it shows as bare text. The note card's border is `border-violet-100`, the same colour as its fill, so the card has no visible edge. System notes have a similar problem: the `bg-slate-200` badge sits on a `bg-slate-100` card.
- `frontend/index.html` [minor, 70%]: `<title>PSA</title>` is hardcoded. `branding.ts` is used only by `App.tsx`, `main.tsx` and `Login.tsx`, so the product name is not fully driven from the branding config.
- `backend/tests/test_integration_readiness.py` [minor, 55%]: There are no tests for the migration's data backfills. The `asset_sources` to `assets.source` mapping (`rmm` for NinjaOne, `import` for other synced assets) and the `ticket_notes.author_type` backfill of author-less notes as `system` are untested. `test_seeded_downgrade_to_0032_and_back` and `test_downgrade_rewrites_rule_conditions` cover the downgrade and the rule-condition rewrite, but I did not see assertions on those two backfills.
- `frontend/src/pages/TicketDetail.tsx` [minor, 55%]: The note header uses `text-xs text-slate-500`. On system notes the background is `bg-slate-100`. Slate-500 on slate-100 is roughly 4.4:1, just under the 4.5:1 WCAG 2.1 AA minimum for small text.
- `backend/app/timesheets.py` [major, 70%]: `_minutes()` and the approved-hours report sum `TimeEntry.minutes_actual` with no `entry_type == 'labour'` filter. `get_timesheet` in `/home/user/custom-psa-nolegion/backend/app/timekeeping.py` (lines 233-307) does the same: `total_minutes` and the day totals include automation entries. Timesheet rows carry no entry type, so the UI cannot tell automation from labour.
- `backend/alembic/versions/0033_integration_readiness.py` [minor, 50%]: The downgrade maps `api` tickets to `ui`, so ticket origin is lost. After a round trip, former `manual` and `api` tickets are indistinguishable. The 'api' source and the unique `(source, external_ref)` rows are also flattened. Dropping `external_ref` first avoids a unique clash, but `external_ref` data is discarded. The same applies to the assets `external_id` and the `rmm_client_id` link.
- `docs/ENTRA_SETUP.md` [minor, 55%]: The Entra redirect URI moved to `/api/v1/auth/callback`. The unversioned alias is removed and there is no redirect, so an existing app registration with the old URI will break login. The doc lists the new URI but gives no upgrade or cut-over note.
- `backend/app/timesheets.py (also backend/app/timekeeping.py)` [major, 60%]: The weekly timesheet total used for submit and approval (`_minutes`) and the timesheet day and week totals sum `minutes_actual` across all non-voided time entries. They do not filter on `entry_type`. `timekeeping.timesheet()` also returns ticket rows without `entry_type`. Automation minutes are therefore counted as hours worked, and the UI cannot tell them from labour.
- `backend/app/asset_sync.py` [minor, 50%]: Synced assets are created with `source="rmm"` or `"import"`, but `Asset.external_id` is never set. The vendor id is stored only on `AssetSource.external_id`. The unique index on (source, external_id) therefore never applies to assets the system itself creates. I found no API input that sets `external_id` on an asset either.
- `backend/app/automation.py` [minor, 55%]: `SOURCES` lists six values and omits `project`. Migration 0033 deliberately keeps `project` as a valid ticket source, and `app/projects.py` sets it. A rule condition on `source` cannot match or exclude project tickets.
- `frontend/src/pages/quotes/SurveyPage.tsx (also frontend/src/pages/billing/CreditMemos.tsx, frontend/src/pages/billing/Payments.tsx)` [minor, 75%]: These pages still build client-scoped calls by hand with `?organization_id=${...}`. They do not go through `clientScope.ts`, and the module offers no helper for query-style scoping.
- `frontend/src/pages/quotes/SurveyPage.tsx, frontend/src/pages/billing/Payments.tsx, frontend/src/pages/billing/CreditMemos.tsx` [minor, 70%]: These files still build client-scoped calls by hand, for example `/quotes?organization_id=${...}` and `/invoices?organization_id=${orgId}&payment_status=open`. They bypass `clientScope.ts`. `clientScope.ts` has no helper for filter-style `?organization_id=` calls.
- `frontend/src/clientScope.ts` [advisory, 50%]: `clientRoute` only delegates to `clientApiPath`. It is the same function under a second name, so it ties UI routes to API paths.
- `frontend/src/clientScope.ts` [minor, 75%]: `main.tsx` mounts `ClientScopeProvider value={null}` at the root. The provider carries no scope, so it does nothing there. The hook always falls back to `useParams().id`.

## Fixes Applied
- cycle 1: engineering-backend-architect on F-002 (blocked); checks 23/23 passed
- cycle 2: engineering-backend-architect on F-002 (blocked); checks 23/23 passed

## Cycle Delta
- cycle 1: 1 must-fix, 1 suggestions, 10 deferred, 0 dropped (low confidence)
- cycle 2: 1 must-fix (resolved 0, new 0, unchanged 1), 0 suggestions, 3 deferred, 0 dropped (low confidence)
- cycle 3: 1 out-of-domain finding(s) filtered (testing-api-tester on api-design, owner engineering-backend-architect); see .planning/logs/authority-decisions-2026-10-31.log
- cycle 3: 1 must-fix (resolved 0, new 0, unchanged 1), 0 suggestions, 1 deferred, 0 dropped (low confidence)

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
