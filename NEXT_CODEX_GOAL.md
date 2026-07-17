# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build one compact fresh-symbol trace-comparison and replay-selection planning
artifact.

This advances feature/model research and prepares a possible later
backtest/local-paper validation step by comparing trace-only evidence before
any replay is run.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, use temporary Codex sidecars in parallel when useful:
  - Engine Research: compare trace evidence and shape the planning artifact.
  - Data: verify all compared traces use existing local Yahoo rows only.
  - Execution/Review: verify planning does not become replay, thresholds, gates,
    or broker behavior.
- These sidecars are runtime collaborators. Do not build a durable multi-agent
  platform, scheduler, daemon, coordinator, notification loop, dashboard, or
  auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not run local-paper replay or create order intents/fills.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, dashboard, or auto-commit worker.
- Do not run model training, ablation, replay reruns, threshold search,
  exit-policy simulation, or broker/local-paper execution.
- Do not download market data into the Git workspace.
- Do not acquire new market data.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep trace comparisons labeled as `source: diagnostic_overlay`.
- Do not turn trace probabilities into execution thresholds, order-intent
  generators, risk rules, broker policies, replay rules, feature rules, gates,
  or model-promotion rules.

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
   contract, or planning artifact schema. If the comparison can be produced by
   a direct artifact script with no repo code changes, prefer that.

## Evidence To Consume

- Independent fresh-symbol trace-only batch:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-independent-trace-only-batch-20260717-r1\metrics.json`
- Prior fresh-symbol trace-only batch:
  `D:\thericher-v2\model-artifacts\candidate-probability-trace-batch\engine-agent-fresh-symbol-trace-only-batch-20260717-r1\metrics.json`
- Data Agent lane-rotation inventory:
  `D:\thericher-v2\model-artifacts\data-agent\data-agent-fresh-symbol-lane-rotation-inventory-20260717-r1\metrics.json`
- Held-branch path-shape comparison:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-simplification\engine-agent-fresh-symbol-replay-path-shape-comparison-20260717-r1\metrics.json`
- Short source-context feature branch:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`

Known facts to preserve:

- MRVL, MU, SNDK, and COHR are held after duplicate-aware path/PnL evidence and
  must not be added to a replay queue by this planning pass.
- GLW, INTC, and QCOM have prior crossing traces and should be comparison
  context only.
- MPWR and STX crossed the fixed descriptive buy threshold in the independent
  trace-only batch.
- DELL and WDC did not cross the fixed descriptive buy threshold.
- APP remains deferred as a source-context training symbol.

## Required Work

1. Confirm the facts above from the consumed artifacts.
2. Produce one compact external planning artifact that compares at least:
   - MPWR and STX,
   - GLW, INTC, and QCOM,
   - DELL and WDC as non-crossing context,
   - held MRVL/MU/SNDK/COHR only as exclusion context.
3. Compare trace evidence without rerunning inference:
   - probability min/mean/max,
   - fixed descriptive threshold gap against `0.541000`,
   - crossing counts,
   - top diagnostic contexts,
   - lineage and local data source,
   - whether the symbol is held, comparison-only, non-crossing, or potential
     later replay candidate.
4. If the planning artifact recommends a later replay, cap it to a very small
   explicit symbol set and mark it as a future separate goal only. Do not run
   replay in this goal.
5. Refresh `NEXT_CODEX_GOAL.md` again before ending:
   - If the planning artifact finds a narrow replay question, make the next
     goal a bounded broker-free local-paper replay-selection run using existing
     traces only.
   - If it does not find a narrow replay question, rotate away from
     fresh-symbol work.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the planning artifact path,
- any sidecars used,
- whether Docker/GPU was used,
- whether future replay is justified and why.

## Suggested Commit Message

`Run independent fresh-symbol trace batch`

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
- local-paper source evidence carried forward, if any,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
