# Next Codex Goal

## Objective

Build `iwm-m1-v2-observation-ledger-v1`.

Advance the market-data foundation by making each immutable IWM/AMS v2
current-head observation explicitly selectable for local replay before a future
append-only collector accumulates additional observations. This is a narrow
source-local data contract, never a data qualification, model, PnL, Paper
order, broker-performance claim, or generic registry platform.

## Hard Boundaries

- Do not read `.env`, credentials, or `KIS_LIVE_*`; do not call KIS or any
  network/provider route.
- Do not invoke, alter, duplicate, or replace the QQQ/SPY scheduled task, its
  cache, cursor, terminal chain, or schedule.
- Read only the named isolated IWM current-head receipt/snapshot roots. Do not
  scan unrelated raw data, add a new symbol, or infer a mutable "latest"
  observation.
- Do not create a schedule, worker, model input, strategy, local-Paper intent,
  account/order route, GPU campaign, performance/PnL claim, or public service.
- Keep raw market data under `D:\market_data` and generated receipts under
  `D:\thericher-v2\model-artifacts`; never commit either.

## Required Work

1. Run a concise Throughput Review. Confirm the current IWM v2 observation is
   bound/replayable while legacy v1 evidence remains incomplete, and the
   QQQ/SPY collector is independent.
2. Ask Claude CLI for a short falsification-first drift check before changing
   receipt-selection or replay identity semantics. Send no raw rows, prices,
   paths, or credentials; do not wait on the result.
3. Freeze one lean observation-selection contract: opaque observation ID,
   exact v2 receipt digest, exact snapshot digest, source-safe ordering field,
   legacy handling, selected replay identity, and strongest ambiguity kill test.
4. Implement the smallest offline-only selector/ledger needed to enumerate
   source-safe IWM observation metadata and reattach exactly one caller-selected
   v2 receipt/snapshot pair. Reject malformed, hash-mismatched, cross-target,
   duplicate, legacy-as-complete, ambiguous, Git-resident, or linked input.
5. Add focused fake/local tests proving deterministic selected replay with
   multiple valid observations, no mutable latest fallback, tamper rejection,
   legacy v1 incompleteness, and no QQQ/SPY/broker/credential/network path.
6. Run one CPU-only local smoke against the retained v2 observation and write
   only a source-safe external receipt with selection and aggregate geometry.
   Refresh Data and orchestration stateboards. Do not create a collector yet.

## Verification

Run focused tests and the local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add IWM observation selector`
