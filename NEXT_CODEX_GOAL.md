# Next Codex Goal

## Objective

Prepare a Data-owned KIS Paper SPY 1m fresh-session capture runner that can
materialize one source-safe prospective baseline receipt after a completed
15:30 ET decision window. This advances KIS-reconstructible input evidence;
it is not a KIS order, account operation, historical backtest, model-training,
or profitability target.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Data, Engine Research, Research Steward, Execution, and orchestration
   stateboards.
2. Ask Claude for a concise falsification-first drift check before adding or
   changing a KIS capture/receipt runner. Never include credentials, raw prices,
   account facts, fills, labels, or raw market rows.

## Boundaries

- `KIS_PAPER_*` market-data reads are authorized for `SPY/AMS/1m` only. Reuse
  the existing private KIS head/cache collection path where it fits. Do not
  read `KIS_LIVE_*`, query account/position/open-order state, or submit/modify/
  cancel any KIS order.
- Retain raw KIS rows and mutable capture state only under `D:\market_data`.
  Keep only source-safe receipts/artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never put them
  in Git.
- A receipt must bind the verified cache/source identity, the fixed 09:30-16:00
  America/New_York session, complete 1m coverage through the fixed 15:30 ET
  cutoff, and the content-bound prospective baseline observation. It must not
  serialize OHLCV values, paths, credentials, account data, order data, fills,
  quantities, or PnL.
- If a fresh completed session is unavailable, preserve a source-safe
  `not_yet_observed` or input-local result for that runner only. Do not wait in
  the foreground, fabricate bars, or block another ready lane.
- Do not train, tune, select, ensemble, allocate GPU work, or claim PnL or
  profitability in this objective. Any local-paper replay remains broker-free
  and retains `source: local_paper`.

## Work

1. **Data:** inspect and reuse the existing KIS Paper intraday head/cache
   contracts. Build a bounded runner/adapter that selects exactly one complete
   SPY/AMS regular session, attests cache/source identity and bar completeness,
   and passes only eligible injected bars to the prospective session-record
   factory. Make its retry/schedule ownership explicit without adding an
   orchestrator sleep or a second scheduler platform.
2. **Engine Research:** turn an eligible record into the fixed content-bound
   observation receipt exactly once, and persist only its source-safe canonical
   payload outside Git. A missing, stale, incomplete, duplicate, or
   non-contiguous input must create no decision receipt or source substitution.
3. **Execution:** reattest that this runner has no account, intent, broker, or
   KIS order surface. Keep the existing local-paper replay evidence distinct
   from any KIS-derived receipt.
4. **Validation:** add focused cache/runner tests for correct session selection,
   DST/session geometry, source-safe redaction, idempotent receipt persistence,
   `not_yet_observed` recovery, and absence of credential/network/broker access
   in offline unit tests. A bounded authorized KIS Paper market-data probe may
   verify only the runner's named read path and must record no raw response.

## Completion

- One KIS-reconstructible SPY fresh-session capture/receipt path is implemented
  and tested.
- It either captures one eligible source-safe observation or leaves an owned,
  non-blocking `not_yet_observed` recovery state for the next market session.
- No account query, KIS order, live route, model training, GPU artifact, raw
  data in Git, or PnL/profitability claim occurs.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue without foreground waiting for market time.

## Verification

```powershell
uv run --extra dev pytest -q <changed paths>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
docker compose --profile research config --quiet
```

## Suggested Commit Message

`Prepare prospective SPY capture runner`
