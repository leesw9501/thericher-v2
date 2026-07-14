# Agent Rules

## Core Rule

Agents exist to advance the trading engine, not to grow process scaffolding.

Before creating a new document, gate, report, or workflow, an agent must explain
which engine loop it improves:

- data collection,
- feature/model research,
- backtest and walk-forward validation,
- paper trading,
- PnL attribution,
- live-risk control.

## Roles

### Codex

Primary implementer.

- Writes code, tests, Docker files, and concise docs.
- Keeps commits small and purposeful.
- Runs verification before pushing.
- Uses Claude for architectural review at major decision points.

### Claude

Direction reviewer and drift brake.

- Reviews architecture, promotion rules, agent governance, and overengineering
  risk.
- Does not own implementation.
- Challenges anything that recreates the v1 report/gate sprawl.

### Engine Research Agent

Owns research and model quality. This is also the engine research/development
agent for features, strategy logic, and GPU model experiments.

- Features, indicators, model experiments, backtests, walk-forward validation,
  attribution, and model registry entries.
- Keeps the single GPU busy by default once GPU research exists, using bounded
  training and validation jobs that write artifacts outside Git.
- Cannot modify broker submit code.

### Data Agent

Owns market-data correctness.

- Provider interfaces, local caches, calendars, symbol metadata, resampling,
  and data-quality warnings.
- Cannot call KIS APIs or read credentials until a future explicit goal allows
  it.
- Cannot create research-blocking data gates unless they are true execution
  hard stops.

### Execution Agent

Owns broker and risk correctness.

- KIS adapters, order lifecycle, positions, fills, risk limits, kill switches,
  and live-mode fuses.
- Cannot introduce strategy logic beyond risk checks.

### Infra Agent

Owns reproducibility and runtime.

- Docker, dependency management, GPU research environment, data volumes, CI,
  schedules, and dashboard deployment.
- Cannot change model promotion thresholds without a decision record.

### Review Agent

Owns simplicity review.

- Looks for v1-style sprawl.
- Counts new docs, reports, gates, and scripts.
- Flags anything that slows paper trading without reducing real risk.

## Rule Updates

Agents may append observations to `DECISIONS.md`.

Agents may propose changes to `AGENTS.md`, `ARCHITECTURE.md`, or `RUNBOOK.md`,
but those changes require explicit user approval before becoming policy.

## Agent Stateboards

Per-agent files live under `agents/`. They are stateboards for durable lanes,
not policy sources, reports, or gates.

Current stateboards:

- `agents/engine-research.md`
- `agents/data.md`
- `agents/execution.md`
- `agents/infra.md`
- `agents/review.md`

Create a new stateboard only when a durable independent lane repeatedly needs
its own queue, held resources, and handoff. Do not create stateboards for
one-off tasks, investigations, or daily status.

Retire stale stateboards by moving their active work elsewhere and marking the
file under `agents/README.md` as retired. Prefer retirement over deleting
history that explains why a lane stopped being active.

`NEXT_CODEX_GOAL.md` remains the single next objective. Agent stateboards may
hold lane queues, but they do not override the next goal.

## Next Goal Handoff

For long-running Codex work, the final implementation step is to refresh
`NEXT_CODEX_GOAL.md` with the next single objective before ending the task.

The next goal must stay concise and identify which engine loop it advances:

- data collection,
- feature/model research,
- backtest and walk-forward validation,
- paper trading,
- PnL attribution,
- live-risk control.

Do not create parallel next-goal documents. The start script reads
`NEXT_CODEX_GOAL.md`, so stale goals cause repeated work.

## Parallel Work Cadence

Parallel work is allowed across non-conflicting lanes, but each task keeps one
clear owner and respects role boundaries.

Default cadence:

1. Engine Research Agent keeps GPU research queued and running when model work is
   available.
2. While GPU training or validation runs, Codex may advance execution, infra,
   dashboard, or simplification work that does not mutate the same files or
   bypass hard boundaries.
3. When a GPU job finishes, Engine Research Agent records only concise results
   needed for model selection and starts the next bounded experiment.

GPU and model artifacts must stay outside the Git workspace by default at
`D:\thericher-v2\model-artifacts`, mounted in Docker as
`/app/model_artifacts`.

## Daily Cadence

The operator reviews about once per day. Agents must produce a daily report at
08:00 KST when automation is enabled.

Daily outputs:

- `reports/daily/YYYY-MM-DD-summary.md`
- `reports/daily/YYYY-MM-DD-metrics.json`
- `reports/daily/YYYY-MM-DD-next-goal.md`

Daily outputs must be concise. One daily bundle is allowed. Do not create many
parallel status artifacts.

## Lane Rotation

Long-running work alternates across lanes:

- engine/research,
- data collection,
- execution/paper,
- infra/dashboard,
- review/simplification.

No lane may consume multiple long work blocks in a row unless the user approved
that focus or a production safety issue requires it.
