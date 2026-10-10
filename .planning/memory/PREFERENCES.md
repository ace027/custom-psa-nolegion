# Memory — User Preferences

Managed by the memory manager. Learnings recorded with /triad:learn are kept below the table.

## Preferences

| ID | Date | Branch | Decision Point | Context | Proposed | User Choice | Signal | Agent | Tags |
|----|------|--------|----------------|---------|----------|-------------|--------|-------|------|
| D-001 | 2026-10-09 | dev | manual-edit | Phase 1, post-build manual edit to backend/app/models.py | Agent output for backend/app/models.py (see plan 01-01 SUMMARY.md) | User edited backend/app/models.py — +3/-2 lines: -    block_covered: Mapped[bool] = mapped_column(Boolean, nu / -                                                server_defa / +    block_covered: Mapped[bool] = mapped_column( / ... | corrective | engineering-senior-developer | manual-edit, py, engineering |
| D-002 | 2026-10-09 | dev | manual-edit | Phase 1, post-build manual edit to backend/app/schemas.py | Agent output for backend/app/schemas.py (see plan 01-01 SUMMARY.md) | User edited backend/app/schemas.py — +4/-2 lines: -        default=None, le=BLOCK_MINUTES_MAX, / +        default=None, / +        le=BLOCK_MINUTES_MAX, / ... | corrective | engineering-senior-developer | manual-edit, py, engineering |
| D-003 | 2026-10-09 | dev | manual-edit | Phase 1, post-build manual edit to backend/tests/test_block_agreements.py | Agent output for backend/tests/test_block_agreements.py (see plan 01-01 SUMMARY.md) | User edited backend/tests/test_block_agreements.py — +37/-19 lines: + / -        json={"organization_id": org_ctx["org"], "name": "F / -              "unit_price_cents": 500, "start_date": "2026- / ... | corrective | engineering-senior-developer | manual-edit, py, engineering |
| D-004 | 2026-10-09 | dev | review-verdict | Phase 1 review | PASS | accepted | positive | system | review |
| D-005 | 2026-10-09 | dev | review-verdict | Phase 2 review | PASS | accepted | positive | system | review |
| D-006 | 2026-10-10 | dev | review-verdict | Phase 3 review | PASS | accepted | positive | system | review |
