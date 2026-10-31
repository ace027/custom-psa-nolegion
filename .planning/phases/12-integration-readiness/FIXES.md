# Phase 12: Integration readiness — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-31
**Checks**: 23/23 passed
**Files changed**: none

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-002 | major | `frontend/src/clientScope.ts` | engineering-backend-architect | not fixed | The primary fix is to make client pages call `useClientScope()` and drop their hand-built `/invoices?organization_id=` and `/quotes?organization_id=` paths. That means editing `Payments.tsx`, `CreditMemos.tsx`, `SurveyPage.tsx`, `OrganizationDetail.tsx` and similar page files, and none of them are on my writable list. The alternative is to delete the hook and reword the criterion. That fails too. `main.tsx` imports `ClientScopeProvider`, which has no other purpose than feeding the hook, so removing the hook leaves a dead provider. I can't edit `main.tsx` or the criterion text. |

## Cycle 2

**Date**: 2026-10-31
**Checks**: 23/23 passed
**Files changed**: none

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-002 | major | `frontend/src/clientScope.ts` | engineering-backend-architect | not fixed | blocked |
