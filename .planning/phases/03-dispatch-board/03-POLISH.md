# Polish Report

## Stats
- Files polished: 6
- Files skipped (excluded/capped): 0
- Comments removed (Pass 1): 1
- Lines simplified (Pass 2): 2
- Symbols renamed (Pass 3): 8
- Patterns normalized (Pass 4): 0

## Pass 1: Comment Cleanup
| File | Line | Removed Text | Reason |
|------|------|--------------|--------|
| all 18 files |  | no restates-code, commented-out-code, stale-todo or signature-restatement comments found | the labelled `# ---- name ----` and `/* ---- name ---- */` headers name a section, so they are not noise-dividers, and the other comments explain intent or gotchas |

## Pass 2: Code Simplification
| File | Lines | Description | Reason |
|------|-------|-------------|--------|
| frontend/src/pages/TicketAppointmentsCard.tsx | 45-47 | "[...(…)].filter(…).sort(…)" → "(…).filter(…).sort(…)" | the spread copy was dead because `filter` already returns a new array |
| frontend/src/pages/TicketAppointmentsCard.tsx | 23-26 | "reuse `s` for the zone-name lookup instead of a second `new Date(a.starts_at)`" | removes a duplicate construction, same value |

## Pass 3: Readability Refactoring
| File | Line | Change | Reason |
|------|------|--------|--------|
| frontend/src/pages/Dispatch.tsx | 136 | "update" → "updateParams" | `update` was vague, and the function only rewrites the URL search params; all 8 call sites changed |
| frontend/src/pages/Dispatch.tsx | 69 | "hhmm = (d: Date)" → "hhmm = (d: Date): string" | missing-return-type |
| frontend/src/pages/Dispatch.tsx | 102 | "todayIn = (zone: string)" → "(zone: string): string" | missing-return-type |
| frontend/src/pages/Dispatch.tsx | 115 | "uniqueLabels = (a: Appointment)" → "(a: Appointment): string[]" | missing-return-type |
| frontend/src/scheduling/board.ts | 41 | "ms = (iso: string)" → "(iso: string): number" | missing-return-type |
| frontend/src/scheduling/BookingDialog.tsx | 126 | "ticketLabel = (t: Ticket)" → "(t: Ticket): string" | missing-return-type |
| frontend/src/scheduling/api.ts | 113-125 | "getAppointment, createAppointment, updateAppointment, cancelAppointment, getSchedule" gain explicit `Promise<…>` return types | missing-return-type; `listAppointments` and `getAvailability` already had them |
| frontend/e2e/dispatch.spec.ts | 31,69 | "login, cancelAll" gain `: Promise<void>` | missing-return-type |

## Pass 4: Consistency Normalization
| File | Line | Change | Convention Source |
|------|------|--------|-------------------|

## Flagged for Review
| Pass | File | Line(s) | Description | Rule |
|------|------|---------|-------------|------|
| REFACTOR | backend/app/scheduling.py | 153-169 | `_schedule_view` and `_weekly` both build the weekly-hours dict | cross-file-dedup, behavior risk |

## Safety
| Check | Result |
|-------|--------|
| Tests | not run (no command) |
| Type Check | not run (no command) |
| Files reverted | none |
