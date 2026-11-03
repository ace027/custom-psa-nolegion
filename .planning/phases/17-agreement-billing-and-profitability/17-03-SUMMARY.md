# Plan 17-03 Summary: Profitability and utilisation by agreement

## Result
**Status**: Complete with Warnings
**Wave**: 2
**Agent**: engineering-backend-architect
**Completed**: 2026-11-03

## Agent Selection Rationale

| Candidate | Semantic | Heuristic | Memory | Total | Source |
|-----------|----------|-----------|--------|-------|--------|
| engineering-backend-architect | — | 11 | 2.97 | 13.97 | mandatory |
| engineering-senior-developer | — | 20 | 3.02 | 23.02 | heuristic |
| testing-api-tester | — | 15 | 3.3 | 18.3 | heuristic |

- **Task type detected**: implementation
- **Confidence**: LOW
- **Adapter**: claude-code
- **Model tier**: sonnet

## Completed Tasks
- [x] Task 1: Metrics (done)
- [x] Task 2: API and CSV (done)
- [x] Task 3: Tests and docs (done)

## Files Modified
- `backend/app/schemas.py`

## Verification Results
6/6 verification commands passed (run by Triad after the agent finished).

## Verification Commands
| Command | Exit Code | Result |
|---------|-----------|--------|
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/ruff format --check app tests` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/python -m app.openapi_export --check` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py tests/test_report_metrics.py tests/test_reports.py tests/test_reports_api.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py tests/test_report_metrics.py` | 0 | PASS |
| `cd backend && /tmp/claude-0/-home-user-custom-psa-nolegion/1935dcd7-aeca-58e8-849e-09f8a10c3370/scratchpad/venv312/bin/pytest -q -p no:warnings tests/test_agreement_profitability.py` | 0 | PASS |

## Key Decisions
- The extended response models live in `schemas.py`, the file the plan allows, and subclass the `report_schemas` models; the default response shape only gains `group` and null agreement fields

## Issues Encountered
- Calling `report_metrics` directly with a bad group raises Conflict (409); over HTTP the Literal param makes it 422, as the plan asks

## Escalations
| # | Severity | Type | Decision | Status | Resolution |
|---|----------|------|----------|--------|------------|
| 1 | info | out-of-scope-file | Move the Phase 17 report response models from backend/app/schemas.py into backend/app/report_schemas.py, where the other report models live, at a later cleanup. | pending | INVALID: type "out-of-scope-file" is not one of architecture, dependency, scope, schema, api, deletion, infrastructure, quality |

- #1 context: The plan named schemas.py, but the report models are in report_schemas.py, which isn't in files_modified. Without new models the API would have dropped the agreement fields. Putting them in schemas.py works and keeps to the file list, but they sit apart from the other report models.

## Handoff Context
- **Key outputs**: backend/app/schemas.py
- **Decisions made**: The extended response models live in `schemas.py`, the file the plan allows, and subclass the `report_schemas` models; the default response shape only gains `group` and null agreement fields
- **Open questions**: (none)
- **Conventions established**: Plan 17-04 UI: pass `group=agreement` and read `agreement_id` (null means 'No agreement'), `agreement_name` and `agreement_type` on profitability rows, and the `agreements` list on utilisation

## Requirements Covered
- Profitability and utilisation by agreement

## Token Usage
15 requests, 565460 input tokens (516953 cached), 8611 output tokens, $0.5181
