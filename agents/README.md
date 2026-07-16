# Agent Stateboards

These files are lane stateboards, not reports, gates, or policy sources.
`AGENTS.md` owns agent policy. `NEXT_CODEX_GOAL.md` owns the single next Codex
objective.

Use these stateboards to keep long-running work moving while preserving role
boundaries. They should help at least one engine loop:

- data collection,
- feature/model research,
- backtest and walk-forward validation,
- paper trading,
- PnL attribution,
- live-risk control.

## Active Stateboards

- `engine-research.md`: features, strategy experiments, model training, GPU
  jobs, backtests, and walk-forward validation.
- `data.md`: market data ingestion, local caches, calendars, resampling, and
  data-quality warnings.
- `execution.md`: local paper execution, broker adapters, order lifecycle,
  fills, positions, and execution hard stops.
- `infra.md`: Docker, dependencies, GPU runtime, artifact mounts, schedules,
  and deployment plumbing.
- `review.md`: simplicity review, v1-sprawl checks, and boundary drift checks.

## Capability Reality Check

In repo documents, "agent" means a lane role plus stateboard unless it is listed
below as an executable worker. Only Engine Research and Data currently have
single-shot CLI workers. There are no persistent autonomous agents,
orchestrators, or Codex thread workers owned by the repo.

## Executable Workers

- Engine Research Agent: `thericher-v2-engine-research-agent`, single-shot
  Docker `research` job enqueue/run worker with artifacts under
  `D:\thericher-v2\model-artifacts\engine-research-agent`.
- Data Agent: `thericher-v2-data-agent`, single-shot non-GPU data inventory
  worker with artifacts under
  `D:\thericher-v2\model-artifacts\data-agent`.

Execution, Infra, and Review do not have executable workers yet. Do not create
one unless the next goal names a durable lane need and the worker improves a
specific engine loop.

## Codex Runtime Sub-Agents

In a Codex task, temporary sub-agents may be used as role-scoped sidecar
reviewers or workers when the user asks for parallel agent work. These are not
repo-owned executable workers and do not replace the stateboards above.

Use them for disjoint, bounded work such as:

- Engine Research sidecar: inspect experiment artifacts or propose a bounded
  diagnostic shape.
- Data sidecar: inspect existing local data evidence without credentials or
  broad scans.
- Execution sidecar: verify local-paper-only evidence and broker boundaries.
- Infra sidecar: verify Docker/artifact mount assumptions.
- Review sidecar: check v1-style sprawl, docs growth, gates, dashboards, or
  coordinator drift.

Main Codex remains the integrator. Sidecars should not mutate overlapping
files, create durable workers, add schedulers, or bypass `NEXT_CODEX_GOAL.md`.

## Stateboard Shape

Each agent file keeps the same compact sections:

- `Engine Loop`
- `Owns`
- `Must Not`
- `Held Resources`
- `Active Queue`
- `Running Jobs`
- `Operator Help Needed`
- `Done Recently`
- `Next Handoff`

Keep entries short. Long experiment outputs belong outside the repo or in a
future model registry, not in these files.

## Retired Stateboards

None.

## Review Notes

If stateboards become long historical ledgers, prefer compacting old details
into `HANDOFF.md` or an external artifact summary instead of adding new report
families.
