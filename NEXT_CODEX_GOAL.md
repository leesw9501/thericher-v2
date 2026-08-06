# Next Codex Goal

## Objective

Build `intraday-head-source-safe-collection-recovery-projection-v1`: extend
the existing exact task-owned intraday-head terminal reader so the current
06:20 KST `collection_exit_nonzero` terminal can be reattached to its exact
hash-bound same-run capture receipt and classified with one deterministic,
source-safe collection recovery category.

The completed observation proves only this exact chain: Scheduler result `1`,
terminal `recovery/collection_exit_nonzero`, verified `incomplete` capture
binding, and capture-target categories
`rejected/minute_duplicate_conflict`. QQQ session and v4 validation were
`not_applicable`, so this is not a model, data-quality, Paper, fill, PnL, or
alpha result.

## Hard Boundaries

- Do not call KIS, invoke or alter any task, submit/modify/cancel a Paper
  order, or read any credential or `KIS_LIVE_*` value.
- Do not scan for a latest receipt, inspect raw market rows, or consult mutable
  cache state as an integrity root.
- Do not expose raw bars, prices, provider payloads, credentials, accounts,
  intents, order IDs, exact receipt paths, or secret-like values in Git, logs,
  artifacts, or review prompts.
- Preserve current and historical immutable terminal/capture receipts. A
  mismatch must remain a scoped recovery, never a repaired or relabeled fact.
- Do not create a scheduler, route, worker, data qualification, model claim,
  GPU campaign, or Paper permission.

## Required Work

1. Reuse the exact task-owned pointer and its terminal receipt. Verify the
   same-run capture binding's run ID, observation time, receipt hash, coverage
   digest, and coverage category before interpreting any capture field.
2. Project only source-safe target status/reason categories. A matching receipt
   with both target results `rejected/minute_duplicate_conflict` must classify
   as `rejected_duplicate_conflict`; other valid shapes retain their explicit
   categorical recovery, without a raw-data fallback.
3. Give every missing, malformed, unsafe, hash-mismatched, run-mismatched,
   timestamp-mismatched, or coverage-mismatched capture receipt the distinct
   `evidence_unavailable` outcome. Do not scan a directory or consult
   `index.json` to repair it.
4. Add focused tests for the valid exact binding, each binding mismatch class,
   source-safe output, and offline/no-credential/no-network behavior.
5. Keep the projection read-only and outside Git for runtime evidence. Refresh
   the Data and orchestration stateboards with the current recovery and the
   next task-owned due fact.

## Verification

Run focused reader/projection tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Project intraday collection recovery evidence`
