# Phase 13: Knowledge base — Review Summary

## Result: PASSED

**Cycles Used**: 1
**Reviewers**: testing-qa-verification-specialist, engineering-frontend-developer
**Completed**: 2026-10-31

## Findings Summary
- Must-fix (blocker, critical, major) found: 0; fixed: 0; unresolved: 0
- Suggestions (minor, advisory): 2
- Deferred (confidence 50-79%): 3
- Hot spots (flagged by 2+ reviewers): none

## Findings Detail
| ID | Severity | Location | Issue | Reviewers | Confidence | Status |
|----|----------|----------|-------|-----------|------------|--------|
| F-001 | advisory | `none` | No defect found. The backend and frontend checks I ran passed: - Backend pytest on `test_kb.py`, `test_kb_portal.py`, `test_permissions.py`, `test_backup_restore.py` and `test_seed_and_migrations.py`: 40 passed. - `openapi_export --check` and `ruff check`: clean. - `vitest` on `KnowledgeBase.test.tsx`: 11 passed. - `npm run typecheck`: no errors. | testing-qa-verification-specialist | 80% | deferred |
| F-002 | minor | `frontend/src/pages/kb/KnowledgeBase.tsx:45-90` | The article list has no loading state. While `list.isLoading` is true, the table renders only its header, and nothing indicates that data is loading. Changing the search or a filter changes the query key, so the table empties on every change because there is no `placeholderData`. The same gap is in `portal/KbPages.tsx` `KbList` (lines 14-30) and in `KbArticlePage` (lines 37-52). The staff `ArticlePage` (line 14 onward) also shows a blank page while loading. | engineering-frontend-developer | 85% | deferred |

## Reviewer Verdicts
- Cycle 1, testing-qa-verification-specialist: **PASS**
- Cycle 1, engineering-frontend-developer: **NEEDS WORK**

## Suggestions (Not Required)
- F-001 `none`: No defect found. The backend and frontend checks I ran passed: - Backend pytest on `test_kb.py`, `test_kb_portal.py`, `test_permissions.py`, `test_backup_restore.py` and `test_seed_and_migrations.py`: 40 passed. - `openapi_export --check` and `ruff check`: clean. - `vitest` on `KnowledgeBase.test.tsx`: 11 passed. - `npm run typecheck`: no errors. (fix: None needed.)
- F-002 `frontend/src/pages/kb/KnowledgeBase.tsx`: The article list has no loading state. While `list.isLoading` is true, the table renders only its header, and nothing indicates that data is loading. Changing the search or a filter changes the query key, so the table empties on every change because there is no `placeholderData`. The same gap is in `portal/KbPages.tsx` `KbList` (lines 14-30) and in `KbArticlePage` (lines 37-52). The staff `ArticlePage` (line 14 onward) also shows a blank page while loading. (fix: Render "Loading…" when `isLoading` is true. Pass `placeholderData: keepPreviousData` on the list queries so results stay visible while the next page or search loads. Add the same loading text to both article pages.)

## Deferred (Medium Confidence)
- `frontend/src/pages/kb/ArticlePage.tsx` [minor, 70%]: Saving or archiving an article invalidates only `["kb","articles"]`. The `["kb","suggestions", ticketId]` cache is not invalidated. The portal list and article caches (`["portal","kb",...]`) are not invalidated either.
- `frontend/src/pages/kb/ArticlePage.tsx` [minor, 55%]: The Archive button runs the mutation on a single click, with no confirmation. An archived article drops out of suggestions and, if it was client-visible, out of the portal.
- `frontend/src/pages/KbSuggestionsCard.tsx` [advisory, 60%]: The card imports `VisibilityBadge` from the `kb/KnowledgeBase` page module. `ArticlePage` imports `StatusBadge` from the same module. Shared presentational components live inside a page component file.

## Fixes Applied
- minor findings: engineering-frontend-developer on F-002, F-003, F-004, F-005 (partial); left as is: F-002 (portal part): not fixed. portal/KbPages.tsx (KbList, KbArticlePage) is not in my writable list. / F-003 (portal caches): not fixed. ["portal","kb"] is not invalidated, because the portal files are outside my scope and I did not confirm that staff and portal share a session. / F-005: not fixed. Moving the badges needs a new file (kb/badges.tsx) or an edit to ui.tsx, and neither is in my writable list. It is advisory.; checks 10/10 passed, 3 file(s) changed

## Coverage
No coverage data found (looked for coverage/coverage-summary.json, coverage-summary.json, coverage/lcov.info, lcov.info, coverage.xml, coverage/cobertura-coverage.xml, coverage/coverage.xml, coverage.txt, coverage/coverage.txt). Advisory only: run the test suite with coverage to check review.coverage_thresholds.
