# Agent Stateboards

`AGENTS.md` owns policy. `NEXT_CODEX_GOAL.md` owns the company objective. These
files are concise current projections for durable role lanes; they are not
reports, policy sources, or historical ledgers.

## Operating Model

```text
Operator -> Codex Orchestrator -> Role Agents
```

Codex decomposes one company objective into disjoint work packages and assigns
them to ready roles. Data, Research, and Execution may progress in parallel. A
blocked lane does not stop another ready lane. Codex integrates shared contracts,
verification, Git, recovery, and the next objective.

For private KIS Paper work, role agents record unavailable inputs and failed
runs as scoped evidence, not permission latches. A historical marker, model
result, or schedule outcome cannot stop another correctly scoped ready lane.

## Active Durable Stateboards

- `data.md`: acquisition, canonical data, provenance, calendars, dataset
  manifests, splits, resampling, and data quality.
- `engine-research.md`: hypotheses, campaign contracts, CPU/GPU models,
  backtests, walk-forward validation, and analytical attribution.
- `execution.md`: local simulation, account/order/fill/position contracts,
  reconciliation, accounting PnL, risk, emergency behavior, and later KIS.

## Independent And Invoked Roles

- Validation is a temporary independent role. It receives frozen inputs, writes
  linked evidence, and exits; it has no durable stateboard yet.
- Infra is invoked for Docker, GPU, dependencies, mounts, storage, CI, and
  runtime reproducibility.
- Review is a lightweight integration checkpoint. Claude challenges the
  bias-prone decision boundaries listed in `AGENTS.md`.

Historical `infra.md` and `review.md` stateboards are retired. Preserve them as
short pointers to Git/external evidence; do not reopen a standing queue without
repeated independent work.

## Capability Reality

- Engine Research has the single-shot
  `thericher-v2-engine-research-agent` worker.
- Data has the single-shot `thericher-v2-data-agent` worker.
- Execution has the goal-owned `kis-paper-canary` recovery worker and the
  `kis-paper-session` Docker worker for a narrow quote-derived virtual-paper
  buy-limit/reconciliation cycle. The latter may be invoked by one scoped local
  schedule; neither is a general scheduler or broker platform.
- Temporary Codex sub-agents can implement or review disjoint role work during
  an active Codex task.
- No repo-owned daemon, autonomous coordinator, or permanent LLM process
  currently exists. Codex may run an external goal-owned schedule under the
  current `AGENTS.md` policy; a schedule is not durable lane identity.

The stateboard is the durable lane identity. A runtime sub-agent or worker is a
bounded executor, not permanent memory.

## Stateboard Shape

Keep only current, high-signal sections:

- status and engine loop,
- ownership and prohibitions,
- resources,
- current objective and ready queue,
- running work,
- operator help,
- durable knowledge,
- recovery,
- a few evidence pointers,
- next handoff.

Replace stale status instead of appending history. Details remain in Git at the
pre-compaction commit `8f416f8` and in external artifacts.

## Shared Memory

Each active role receives logical working-memory, permanent-knowledge, history,
evidence, and recovery views over one planned shared substrate:

```text
D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl
D:\thericher-v2\model-artifacts\_control\catalog.sqlite
```

Until that substrate is implemented, stateboards and exact artifact pointers
are the recovery bridge. Do not create per-agent databases, vector stores,
history documents, daily goal files, or recovery reports.

## Lifecycle

Start new work as a temporary role assignment. Create a stateboard only after a
role has a distinct authority boundary and recurring work across multiple Codex
tasks or owns an independent resource. Move an empty role to invoked/standby
status. Retire duplicate or stale roles without deleting the Git history that
explains them. Codex reviews this portfolio at each company-goal boundary and
may make these reversible lifecycle changes without waiting for routine
operator approval; authority, cost, credential, capital, and live-risk changes
still follow `AGENTS.md`.
