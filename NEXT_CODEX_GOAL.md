# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded Data Agent lane-rotation inventory after the MPWR hold decision.

This advances data collection and backtest/walk-forward validation by checking
existing local data and artifact provenance for the next useful evidence batch,
or by proving that no immediate data-lane follow-up is worth running.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars only if useful:
  - Data: inspect the inventory criteria and local/artifact provenance.
  - Engine Research: verify the inventory does not smuggle in replay/training.
  - Execution/Review: verify no broker, gate, promotion, or sprawl drift.
- These sidecars are runtime collaborators. Do not build a durable multi-agent
  platform, scheduler, daemon, coordinator, notification loop, dashboard, or
  auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, dashboard, or auto-commit worker.
- Do not run model training, ablation, trace compute, trace recompute,
  threshold search, replay rerun, exit-policy simulation, or broker execution.
- Do not turn data inventory output into execution thresholds, risk rules,
  broker policies, replay rules, feature rules, gates, or model-promotion
  rules.
- Do not acquire new market data unless it is no-auth, lawful,
  license-compatible, useful to this active inventory, and strictly bounded by
  exact missing symbols or date ranges found during the inventory.
- Do not perform a broad recursive scan of `D:\market_data`; prefer targeted
  known roots and existing artifact provenance.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts`, `D:\market_data`, `/app/model_artifacts`,
  or `/app/market_data` as appropriate.
- Treat MPWR, MRVL, MU, SNDK, and COHR as held for fresh-symbol replay/training
  unless this inventory only references them as provenance context.

## Required First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/README.md`
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before adding or changing any helper,
   job kind, dispatch path, agent governance, artifact contract, data contract,
   replay contract, attribution contract, or local-paper behavior. If the
   inventory can be produced by reading existing artifacts and known local-data
   roots with a one-off script, prefer that.

## Evidence To Consume

- MPWR hold/rotate decision artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-decision\fresh-symbol-mpwr-hold-rotate-decision-20260717-r1\metrics.json`
- MPWR replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-mpwr-replay-selection-20260717-r1\metrics.json`
- MPWR trade-path attribution artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\fresh-symbol-mpwr-trade-path-attribution-20260717-r1\metrics.json`
- Fresh-symbol lane-rotation inventory artifact:
  `D:\thericher-v2\model-artifacts\data-agent\data-agent-fresh-symbol-lane-rotation-inventory-20260717-r1\metrics.json`
- Trace-comparison planning artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-trace-comparison-replay-planning-20260717-r1\metrics.json`
- Known local Yahoo snapshot, if a targeted local-row check is needed:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Known facts to preserve:

- MPWR is held after duplicate-aware local-paper attribution.
- MPWR evidence remains local-paper simulator evidence only, not broker-paper or
  live evidence.
- Existing fresh-symbol replay/training branches are held unless a later
  bounded artifact defines a new question.
- Data acquisition is not currently requested by the evidence.

## Required Work

1. Inventory existing artifact provenance and only the necessary targeted local
   data roots for a next-lane recommendation.
2. Decide whether the next useful evidence batch should be:
   - another bounded data/provenance cleanup,
   - a future trace-only GPU batch,
   - a future artifact-only review/simplification pass,
   - or no immediate data-lane follow-up.
3. Produce one compact external artifact recording:
   - consumed artifact paths,
   - any targeted local data paths inspected,
   - data found or missing,
   - acquisition decision and stop reason,
   - held-symbol exclusions,
   - recommended next lane/objective,
   - no replay, broker, KIS, gate, threshold-search, exit-policy, promotion, or
     durable multi-agent semantics.
4. Refresh `NEXT_CODEX_GOAL.md` again before ending with one single objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the inventory command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- local data found or missing,
- acquisition decision and stop reason,
- what lane should rotate next and why.

## Suggested Commit Message

`Run post-MPWR data lane inventory`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced artifacts,
- local-paper source evidence if referenced,
- diagnostic-overlay source evidence if referenced,
- what was intentionally not built,
- next goal.
