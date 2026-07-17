# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one compact MPWR hold/rotate decision artifact from existing replay and
trade-path attribution evidence.

This advances backtest and walk-forward validation by deciding whether the MPWR
fresh-symbol branch should be held after duplicate-aware PnL attribution, or
whether a different lane should rotate next.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars only if useful:
  - Engine Research: verify the hold/rotate criteria from existing artifacts.
  - Data: verify no data acquisition is needed.
  - Execution/Review: verify no replay, broker, gate, or promotion drift.
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
- Do not read market data unless needed to verify a path already recorded in
  the consumed attribution artifact.
- Do not acquire new market data.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Do not include STX, GLW, INTC, QCOM, DELL, WDC, APP, or held
  MRVL/MU/SNDK/COHR as new replay/model targets.
- Do not turn decision output into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.

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
   job kind, dispatch path, agent governance, artifact contract, replay
   contract, attribution contract, or local-paper behavior. If the decision can
   be produced by reading existing artifacts with a one-off script, prefer that.

## Evidence To Consume

- MPWR replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-mpwr-replay-selection-20260717-r1\metrics.json`
- MPWR trade-path attribution artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\fresh-symbol-mpwr-trade-path-attribution-20260717-r1\metrics.json`
- Fresh-symbol trace-comparison planning artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-trace-comparison-replay-planning-20260717-r1\metrics.json`
- Held fresh-symbol duplicate-aware/path-shape context:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-simplification\engine-agent-fresh-symbol-replay-path-shape-comparison-20260717-r1\metrics.json`

Known facts to preserve:

- MPWR is the only symbol being decided.
- MPWR replay-selection produced `24` fills, all `source: local_paper`.
- MPWR attribution produced `12` raw closed segments and `0` open segments.
- Duplicate-aware collapse produced `4` unique market moments, each repeated
  across the three threshold variants.
- Unique fee-aware sum was `-5.3088`, with `2` negative and `2` non-negative
  moments.
- Raw fee-aware sum was `-15.9264`; use unique PnL to avoid threshold-variant
  inflation.

## Required Work

1. Confirm the facts above from the consumed artifacts.
2. Produce one compact external decision artifact recording:
   - consumed artifact paths,
   - source evidence separation,
   - raw versus duplicate-aware PnL,
   - repeated threshold-variant evidence,
   - whether MPWR branch should be held,
   - which lane should rotate next,
   - no replay, broker, KIS, gate, threshold-search, exit-policy, or promotion
     semantics.
3. Refresh `NEXT_CODEX_GOAL.md` again before ending with one single objective.
   Prefer lane rotation away from MPWR/fresh-symbol replay unless the decision
   artifact identifies a specific bounded non-replay follow-up.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the decision command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what lane should rotate next and why.

## Suggested Commit Message

`Record MPWR hold rotate decision`

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
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
