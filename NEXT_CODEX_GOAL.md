# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one artifact-only Review/Simplification pass over post-MPWR fresh-symbol
leftovers.

This advances backtest and walk-forward validation by deciding whether the
fresh-symbol branch should be retired from the active queue after MPWR hold and
post-MPWR data inventory, without forcing more process or compute.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars only if useful:
  - Review: check sprawl, stale queue, and retirement criteria.
  - Engine Research: verify no replay/training/trace compute is justified.
  - Data/Execution: verify no data acquisition or broker/local-paper mutation.
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
  threshold search, replay rerun, exit-policy simulation, broker execution, or
  data acquisition.
- Do not perform a broad recursive scan of `D:\market_data`.
- Do not turn review output into execution thresholds, risk rules, broker
  policies, replay rules, feature rules, gates, or model-promotion rules.
- Do not store generated GPU/model artifacts or market data in the repo. Use
  `D:\thericher-v2\model-artifacts` for external review artifacts.

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
   simplification can be produced by reading existing artifacts with a one-off
   script, prefer that.

## Evidence To Consume

- Post-MPWR Data Agent inventory:
  `D:\thericher-v2\model-artifacts\data-agent\data-agent-post-mpwr-lane-rotation-inventory-20260717-r1\metrics.json`
- MPWR hold/rotate decision artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-decision\fresh-symbol-mpwr-hold-rotate-decision-20260717-r1\metrics.json`
- Trace-comparison planning artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\fresh-symbol-trace-comparison-replay-planning-20260717-r1\metrics.json`
- Fresh-symbol path-shape context:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-simplification\engine-agent-fresh-symbol-replay-path-shape-comparison-20260717-r1\metrics.json`

Known facts to preserve:

- MPWR is held after duplicate-aware local-paper attribution.
- MRVL, MU, SNDK, and COHR remain held from the prior fresh-symbol branch.
- DELL and WDC stayed below the descriptive threshold.
- STX is a single thin crossing context, not a replay trigger.
- GLW, INTC, and QCOM are already-traced comparison context, not immediate
  replay or acquisition triggers.
- APP remains deferred as possible source-context training scope.
- No immediate data-lane, Engine Research, GPU, replay, or acquisition follow-up
  is justified by the latest artifacts.

## Required Work

1. Produce one compact external simplification artifact recording:
   - consumed artifact paths,
   - stale/held active-queue items,
   - which symbols or branches should be retired, held, or left as passive
     context,
   - why no replay, training, trace compute, acquisition, gate, threshold
     search, exit-policy, promotion, or durable platform work follows.
2. Update `HANDOFF.md` and agent stateboards only as needed to keep the active
   queues clean.
3. Refresh `NEXT_CODEX_GOAL.md` again before ending with one single objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the simplification command or primitive used,
- any sidecars or executable workers used,
- whether Docker/GPU was used,
- produced artifact paths,
- what active queue context was retired or held,
- what lane should rotate next and why.

## Suggested Commit Message

`Retire post-MPWR fresh-symbol queue`

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
