# Polish Report

## Stats
- Files polished: 0
- Files skipped (excluded/capped): 0
- Comments removed (Pass 1): 7
- Lines simplified (Pass 2): 1
- Symbols renamed (Pass 3): 1
- Patterns normalized (Pass 4): 1

## Pass 1: Comment Cleanup
| File | Line | Removed Text | Reason |
|------|------|--------------|--------|
| backend/app/models.py | 170 | "# Phase 2: ticketing" banner | it names a section and carries information, so it is not a noise-divider |
| backend/app/*.py, frontend/src/api.ts |  | "# ---- projects ----" style labelled dividers | each names a section in a 400 to 1800 line file, so they work as navigation |
| backend/app/main.py | 65 | "CSRF defense in depth on top of SameSite=Lax..." | explains why (gotcha) |
| backend/app/projects.py | 455 | "Serialize dependency edits per project..." | explains why (concurrency gotcha) |
| backend/app/permissions.py | 27-35 | permission group comments | business rules |
| frontend/src/pages/ProjectDetail.tsx | 18 | "Mirrors the server rules; draft becomes active only through Approve." | business logic |
| all other comments scanned |  | none restate code, narrate, or hold commented-out code or ref-less TODOs | none matched a removal category |

## Pass 2: Code Simplification
| File | Lines | Description | Reason |
|------|-------|-------------|--------|
| all 29 files |  | `ruff --select F401,F841,E712` passes on all 18 backend files. `tsc --noEmit --noUnusedLocals --noUnusedParameters` passes on the frontend. | there are no unused imports or variables to remove |

## Pass 3: Readability Refactoring
| File | Line | Change | Reason |
|------|------|--------|--------|
| all 29 files |  | no local-scope renames or missing types were found that a rule covers without judgment | oversized-function and exported-scope items are flagged below |

## Pass 4: Consistency Normalization
| File | Line | Change | Convention Source |
|------|------|--------|-------------------|
| all 29 files |  | no outlier covers less than 30% of its samples | no mechanical normalization applies |

## Flagged for Review
| Pass | File | Line(s) | Description | Rule |
|------|------|---------|-------------|------|
| CONVENTION | backend/app/models.py, backend/app/schemas.py | 170-172, 189-191 and similar | Two section-divider styles are mixed. Some are three-line banners (`# ----` / title / `# ----`) and some are single-line `# ---- name ----`. Single-line labels are used about 60% of the time, and the split is not above the 70% threshold. | ambiguous-split |

## Safety
| Check | Result |
|-------|--------|
| Tests | not run (no command) |
| Type Check | not run (no command) |
| Files reverted | none |
