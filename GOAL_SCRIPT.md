# Long Goal Script

Paste this short launcher into Codex. Repository policy and
`NEXT_CODEX_GOAL.md` carry the detailed instructions.

```text
/goal
Working directory: C:\Users\Public\Documents\thericher-v2

Run .\scripts\start_next_codex_task.ps1. Then read and follow
`NEXT_CODEX_GOAL.md`, `HANDOFF.md`, `AGENTS.md`, and the active stateboards:
`agents/data.md`, `agents/engine-research.md`, `agents/execution.md`, and
`agents/orchestration.md`.

Act as the Codex Orchestrator. Decompose the single company objective into
disjoint, ready work packages. Run non-conflicting Data, Engine Research, and
Execution work in parallel; invoke temporary Validation only when a frozen
candidate and independent evaluation input are ready. Integrate evidence and
shared contracts before dependent work relies on them.

Treat a genuinely unknown private non-live provider, runtime, data-capability,
or throughput behavior as a bounded capability probe. Do not turn it into an
approval wait, foreground sleep, or durable rate/retry limit without official
source evidence or measured results. Keep existing documented or
evidence-backed controls until the source or measurement that recalibrates
them changes. External quota/cooldown waits belong to the named worker or
scheduler as `next_due`; continue another ready lane rather than waiting in
the foreground.

After each bounded objective has completion evidence, run the required
verification, commit, push, replace `NEXT_CODEX_GOAL.md` with exactly one next
company objective, refresh the stateboards, and continue. A lane-local block
does not stop another ready lane. Do not create per-agent next-goal files.

Stop and report only for an actual operator-authority decision: reading or
using `KIS_LIVE_*`, enabling live or real-money behavior, allocating live
capital, paid commitments, unclear data/model rights, public exposure, a major
framework or runtime replacement, an unapproved irreversible external action,
or an unresolved actual account-safety risk.

`KIS_PAPER_*` credential reads, data/account calls, paper submit/modify/cancel,
and goal-owned schedules are already approved by `AGENTS.md`. Use them only
through the named owned paths and scope of the current objective; never print
or persist secrets. Never read or route `KIS_LIVE_*`.

Keep market data under D:\market_data and generated artifacts under
D:\thericher-v2\model-artifacts. Follow the approved free-data/public-model,
storage, Claude challenge, KIS Paper, recovery, and orchestration policies in
`AGENTS.md`.
```
