# Next Codex Goal

## Objective

Build `kis-intraday-coverage-contract-diagnosis-v1`.

Determine whether the existing QQQ/SPY current-session M1 coverage result has
a narrow deterministic aggregation or retention defect that is repairable
offline. This advances the data-collection loop while preserving the current
causal input boundary; it does not select a strategy, train a model, claim PnL,
or authorize Paper or live execution.

## Hard Boundaries

- Do not manually invoke KIS, Docker, `thericher-kis-paper-intraday-head`, a
  collector, a scheduler, or any account/order/quote endpoint.
- Do not read credentials or `.env`, print or persist raw M1 rows, account
  values, private intents, broker payloads, or identifiers. Never read or
  route `KIS_LIVE_*`.
- Inspect only credential-free source code, tests, source-safe receipt/cache
  metadata, and the existing offline terminal reader. Do not replace its
  task-owned pointer with a latest-artifact scan.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.
- Do not change provider pacing, task schedules, execution routes, Paper
  submission behavior, model eligibility, or GPU allocation from this goal.

## Required Work

1. Trace the current-session coverage calculation from the existing exact
   terminal binding through the source-safe capture metadata and current-head
   aggregation/retention code. Keep all raw M1 rows unopened.
2. Decide with focused fixture tests whether `incomplete` can arise from a
   deterministic aggregation/retention defect. State the strongest kill test:
   if the same valid metadata still yields incomplete coverage under the
   intended contract, retain the scoped source limitation.
3. If and only if a defect is proven, make the smallest credential-free repair
   and add regression tests. Do not rebuild or run a collector, Docker service,
   task, or scheduler in this objective.
4. If no repairable defect is proven, record the categorical no-repair result
   and select an independent next company objective rather than waiting for a
   new market session.
5. Refresh `HANDOFF.md`, the Data, Engine Research, Execution, and
   orchestration stateboards, plus `RUNBOOK.md`. Ask Claude for a short
   falsification-first drift check before relying on a repair or changing the
   next data direction.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Diagnose intraday coverage contract`
