# Next Codex Goal

## Objective

Build `kis-intraday-coverage-repair-rollout-v1`.

Roll the verified metadata-only cumulative-coverage repair into the existing
QQQ/SPY intraday-head task image and reattest its static route. This advances
the data-collection loop while leaving the next runtime observation task-owned;
it does not select a strategy, train a model, claim PnL, or authorize Paper or
live execution.

## Hard Boundaries

- Do not manually invoke KIS, the installed task, a collector, a scheduler, or
  any account/order/quote endpoint. Do not change task triggers, pacing, or
  concurrency.
- Build only the existing `kis-paper-intraday-head` service image with
  `--env-file .env.example`; never run the service or load `.env`.
- Do not read credentials, print or persist raw M1 rows, account values,
  private intents, broker payloads, or identifiers. Never read or route
  `KIS_LIVE_*`.
- Inspect only source-safe Task Scheduler facts, static source/Compose
  contracts, and the existing credential-free offline reader. The next task
  terminal is its own evidence, not an excuse for a manual duplicate.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.
- Do not change execution routes, Paper submission behavior, model eligibility,
  or GPU allocation from this goal.

## Required Work

1. Reattest that the existing task's static action still selects only the
   established intraday-head dispatcher and service. Keep the inspection
   source-safe and do not expose task arguments that could contain secrets.
2. Build the existing service image with `.env.example`, without running a
   container. Verify the image/service contract includes the repaired
   metadata-only coverage code and preserves the existing no-live boundary.
3. Run focused static/fixture tests that prove the identical-row completion
   repair, conflicting-fingerprint behavior, and candidate-batch exclusion.
4. Record that the current immutable terminal remains
   `input_unavailable/session_coverage_incomplete`; only a later task-owned
   terminal can provide a runtime observation of the new image.
5. Do not foreground-wait for that terminal. After the rollout package is
   verified and committed, refresh the stateboards and select an independent
   ready company objective while the task-owned observation remains due.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Repair intraday cumulative coverage`
