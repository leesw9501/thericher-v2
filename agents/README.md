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
