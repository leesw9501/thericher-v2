# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one compact artifact-only path-shape comparison over the duplicate-aware
fresh-symbol replay evidence.

This advances PnL attribution and backtest validation by comparing the `17`
unique MRVL/MU/SNDK/COHR market moments that survived duplicate collapse before
any broader replay, model training, exit-policy simulation, feature rule, or
threshold iteration.

## Current Agent Reality

- Engine Research Agent has an executable single-shot Docker research worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot metadata worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- For this goal, actually use temporary Codex sidecars in parallel when useful:
  - Engine Research: inspect positive vs negative path-shape evidence.
  - Data: confirm no new data read/acquisition is needed.
  - Execution/Review: verify source separation and no rule/gate semantics.
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
- Do not run model training, ablation, trace recomputation, replay reruns,
  threshold search, exit-policy simulation, or data acquisition.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep diagnostic/path context labeled as `source: diagnostic_overlay`.
- Preserve all referenced fills as `source: local_paper`.
- Do not turn this comparison into a live execution threshold, order-intent
  generator, risk rule, broker policy, feature rule, exit rule, gate, or
  model-promotion rule.

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
   job kind, dispatch path, agent governance, attribution contract, or replay
   contract. If the comparison can be done as a direct artifact script, prefer
   that over adding code.

## Evidence To Consume

- Duplicate-aware simplification artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-replay-selection-duplicate-aware-decision-20260717-r1\metrics.json`
- Trade-path attribution artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-fresh-symbol-replay-selection-trade-path-20260717-r1\metrics.json`
- Replay-selection compact artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-selection\engine-agent-fresh-symbol-replay-selection-20260717-r1\metrics.json`

Known facts to confirm:

- `100` referenced fills remained `source: local_paper`.
- `50` raw closed paths collapsed to `17` unique market moments.
- Duplicate-aware unique fee-aware delta summed to `-11.7695`.
- SNDK and COHR losses survived duplicate collapse.
- MRVL was mildly positive across `4` unique moments.
- MU was positive but only `1` unique market moment.

## Required Work

1. Confirm the simplification artifact matches the facts above and remains
   local-paper-only with diagnostic-only path context.
2. Compare duplicate-aware positive and negative path shapes without rerunning
   replay:
   - adverse excursion,
   - favorable excursion,
   - holding duration,
   - exit timing,
   - symbol concentration,
   - repeated threshold-variant count.
3. Record whether the losses appear path-shape-specific or simply duplicated
   threshold noise.
4. Record whether any follow-up is justified:
   - artifact-only model-input question,
   - artifact-only exit-timing question,
   - no follow-up and rotate lanes.
5. Produce at most one compact external artifact recording:
   - consumed artifact paths,
   - grouping and comparison rules,
   - local-paper source verification carried forward,
   - diagnostic-overlay source verification,
   - hold/rotate recommendation,
   - no promotion/gate/execution-rule semantics.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- the comparison command or focused smoke used,
- any sidecars used,
- whether Docker/GPU was used,
- produced artifact path, if any,
- whether a future model/replay/exit follow-up is justified.

## Suggested Commit Message

`Simplify fresh-symbol replay attribution`

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
