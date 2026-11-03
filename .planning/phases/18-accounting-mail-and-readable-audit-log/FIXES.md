# Phase 18: Accounting mail and readable audit log — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-11-03
**Checks**: 19/19 passed
**Files changed**: `frontend/src/pages/Audit.test.tsx`, `frontend/src/pages/Audit.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | blocker | `frontend/src/pages/Audit.tsx` | engineering-frontend-developer | fix applied | Audit.tsx now types `/audit/entity-types` as `{value,label}[]`. It renders `key={t.value} value={t.value}` with `t.label` as the option text. The test mock returns the real response shape. A new test checks that the "Contact" label renders and that picking it sends `entity_type=contact`. |
| F-002 | major | `frontend/src/pages/Audit.test.tsx` | engineering-frontend-developer | fix applied | Audit.tsx now types `/audit/entity-types` as `{value,label}[]`. It renders `key={t.value} value={t.value}` with `t.label` as the option text. The test mock returns the real response shape. A new test checks that the "Contact" label renders and that picking it sends `entity_type=contact`. |
