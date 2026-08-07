# Next Codex Goal

## Objective

Build `kis-paper-iwm-m1-bound-observation-v2`.

Advance the market-data foundation by making one fresh isolated IWM/AMS
current-head KIS Paper observation whose source-safe v2 receipt binds the
immutable snapshot identity, then prove the matching local replay can use the
existing completed-bar and `1m`/`5m`/`10m`/`1h`/`3h` resampler contracts. This
is source-local input mechanics only, never data qualification, a model, PnL,
a Paper order, or broker-performance claim.

## Hard Boundaries

- Use only `KIS_PAPER_*` through the existing named market-data client and
  isolated IWM path. Do not read or route `KIS_LIVE_*`.
- Make at most one current-day IWM/AMS page request. Do not follow a
  continuation cursor, page historical data, retry with a second request, or
  broaden to another symbol.
- Do not invoke, alter, duplicate, or replace the QQQ/SPY scheduled task, its
  cache, cursor, terminal chain, or schedule.
- Do not call account, position, order, modify, cancel, or live routes; do not
  expose credentials, raw rows, prices, paths, or artifacts.
- Keep raw market data under `D:\market_data` and generated receipts under
  `D:\thericher-v2\model-artifacts`; never commit either.

## Required Work

1. Run a concise Throughput Review and confirm the primary QQQ/SPY collector
   remains independent.
2. Ask Claude CLI for a short falsification-first drift check before relying on
   the receipt-to-snapshot completion binding. Send no raw rows, prices, paths,
   or credentials; do not wait on the result.
3. Run focused fake/local tests first. Verify a v2 receipt binds exactly its
   snapshot, old v1 evidence stays incomplete, ambiguity/tampering is rejected,
   and a bound fixture supports the five resampler timeframes.
4. Invoke the existing isolated IWM collector exactly once with `--execute`.
   Preserve the source-safe outcome even if it is unavailable; do not make a
   second provider request in this objective.
5. If the one page is accepted, run the offline replay script against its
   matching v2 receipt and record only categorical status and aggregate completed
   bucket counts. If the page is unavailable, record its category and leave the
   existing legacy snapshot unchanged.
6. Refresh Data and orchestration stateboards with the exact outcome and next
   recovery action. Do not promote any result to coverage, model, GPU, Paper,
   or execution eligibility.

## Verification

Run focused tests and any one-page collection/replay smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Bind IWM current-head observation receipt`
