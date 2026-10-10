# Phase 1: Block-hour / retainer agreements — Review Fixes

Fixes applied by the review loop, one section per cycle. Re-review decides whether each one holds.

## Cycle 1

**Date**: 2026-10-09
**Checks**: 16/16 passed
**Files changed**: `frontend/src/pages/billing/Agreements.tsx`

| Finding | Severity | File | Agent | Status | Notes |
|---------|----------|------|-------|--------|-------|
| F-001 | major | `frontend/src/pages/billing/Agreements.tsx` | engineering-frontend-developer | fix applied | F-001 fixed in Agreements.tsx. Row controls now have names that identify the agreement. - The Reason input is labelled "{name} reason". - Both Save buttons are "Save {name} quantity" and "Save {name} included hours". - The row buttons are "History {name}", "Resume {name}" and "End {name}". History also has aria-expanded. - The empty trailing header now holds an sr-only "Actions". |
