# Next Codex Goal

## Objective

Build `intraday-m1-collector-duplicate-conflict-recovery-v1`.

Advance the market-data collection loop by repairing the exact task-owned
QQQ/NAS and SPY/AMS current-head `minute_duplicate_conflict` recovery seam.
The next scheduled collector must be able to retain a valid causal head while
categorically preserving or quarantining only a conflicting candidate. This is
data-recovery work, not a coverage, model, PnL, Paper, or broker result.

## Hard Boundaries

- Do not read `KIS_LIVE_*`, enable live behavior, call account/order routes, or
  submit, modify, or cancel any broker order.
- KIS Paper market-data access is standing-authorized only through the existing
  named Data-owned collector path when a bounded post-fix capability probe is
  genuinely needed. Never print or persist credentials, tokens, raw rows,
  prices, provider payloads, or cache paths in Git or artifacts.
- Do not manually invoke, duplicate, or replace the existing scheduled task.
  Its next owned run remains the first actual-collection consumer of a verified
  repair.
- Keep raw data under `D:\market_data` and generated evidence under
  `D:\thericher-v2\model-artifacts`; never commit either.
- Do not create a strategy, model, target, local-Paper intent, performance/PnL
  claim, GPU campaign, new scheduler, or public service.

## Required Work

1. Run a concise Throughput Review. Inspect the exact source-safe terminal and
   capture chain plus the collector/reconciliation code. Before changing shared
   duplicate, cursor, cache-retention, or recovery semantics, obtain a concise
   Claude falsification-first drift-check; do not wait on it.
2. Freeze one recovery contract before implementation: accepted duplicate
   identity, conflicting-candidate disposition, retained-head invariant, cursor
   behavior, source-safe terminal category, and strongest kill test.
3. Implement the smallest deterministic recovery that preserves a valid
   retained causal head, never overwrites a conflicting row, and closes only
   that collector scope as a categorical recovery when it cannot continue.
4. Add focused tests for exact duplicate idempotence, conflicting duplicate
   preservation/quarantine, no overwrite of retained cache, durable cursor
   recovery, source-safe receipts, external-only raw storage, and no
   account/order/live/credential path.
5. If the repair is testable and an actual capability fact remains unknown, use
   at most one owned collector probe with its existing in-memory client and
   record only source-safe accepted-page/error/pace facts. Otherwise leave the
   next scheduled task as owner. Refresh Data and orchestration stateboards.

## Verification

Run focused tests, any source-safe probe used, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Recover task-owned M1 duplicate conflicts`
