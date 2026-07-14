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

### Strategy Agent

Owns research and model quality.

- Features, indicators, model experiments, backtests, walk-forward validation,
  attribution, and model registry entries.
- Cannot modify broker submit code.

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
- execution/paper,
- infra/dashboard,
- review/simplification.

No lane may consume multiple long work blocks in a row unless the user approved
that focus or a production safety issue requires it.
