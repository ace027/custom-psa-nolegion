# Sub-agent delegation

Cheap, fast sub-agents live in `.claude/agents/` (`finder`, `test-runner`, `doc-drafter`, `ci-triage`). Use them for mechanical work: searching, running checks, drafting docs, reading CI logs. Each keeps to about 100k tokens of context, because cost rises past that.

Keep these on the main model: money and billing math, auth and permissions, RLS and migrations, quoting rules, and security review. Never delegate a decision the owner must make.
