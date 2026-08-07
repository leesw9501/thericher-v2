# Next Codex Goal

## Objective

Build `kis-paper-iwm-m1-current-head-replayability-v1`.

Advance the market-data foundation by proving that the one newly retained,
isolated IWM/AMS current-head snapshot can be deterministically reattached as
canonical local `Bar` data and resampled into completed `1m`, `5m`, `10m`,
`1h`, and `3h` buckets. This is source-local input mechanics only, never a
data-qualification, model, PnL, Paper, or broker claim.

## Hard Boundaries

- Do not read `.env`, credentials, or `KIS_LIVE_*`; do not call KIS or any
  network/provider route.
- Do not invoke, alter, duplicate, or replace the QQQ/SPY scheduled task, its
  cache, cursor, terminal chain, or schedule.
- Read only the exact retained IWM snapshot through a named local cache reader;
  do not scan unrelated raw data or broaden to historical pagination, another
  symbol, a model input, strategy, local-Paper intent, performance/PnL claim,
  GPU campaign, or public service.
- Keep raw market data under `D:\market_data` and generated receipts under
  `D:\thericher-v2\model-artifacts`; never commit raw rows, prices, paths,
  credentials, or artifacts.

## Required Work

1. Run a concise Throughput Review. Confirm the IWM current-head receipt is
   accepted/retained and the primary QQQ/SPY task remains independent.
2. Ask Claude CLI for a short falsification-first drift check before changing
   local cache-reader or completed-bar/resampling semantics. Send no raw rows,
   prices, paths, or credentials; do not wait on it.
3. Freeze the local replay contract: one IWM/AMS snapshot identity, manifest
   and raw-hash attestation, canonical timestamp basis, completed-bar rule,
   five timeframe set, source-safe output fields, strongest tamper/isolation
   kill test, and the exact fact needed before any later repeated collection.
4. Implement or reuse the smallest local-only reader/adapter needed to emit
   canonical `Bar` values from that one snapshot and feed the existing
   timeframe resampler. Reject wrong target, Git-resident root, malformed or
   hash-mismatched snapshot, incomplete bucket, and cross-target state before
   an output is accepted.
5. Add focused no-network fake/local tests proving deterministic replay,
   tamper rejection, `1m`/`5m`/`10m`/`1h`/`3h` completed-bucket behavior, and
   no QQQ/SPY cache/scheduler/broker/credential route.
6. Run a CPU-only local smoke against the retained snapshot and write only a
   source-safe external receipt with categories and aggregate geometry. Refresh
   Data and orchestration stateboards.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Prove IWM current-head replayability`
