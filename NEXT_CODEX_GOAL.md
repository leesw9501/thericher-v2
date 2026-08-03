# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-outcome-witness-v1`: extend the existing
forward-only QQQ/SPY MTF observation path so a sealed 15:30 ET causal input
commitment can be paired with each leg's completed 15:45 ET outcome-window
commitment. This makes future target-ready pairs recoverable for the frozen
predictive campaign dependency without opening labels, training a model, or
creating a Paper decision.

## Boundaries

- Ask Claude for one concise falsification-first drift check before changing
  the forward-observation persistence contract or a KIS collection schedule.
- Reuse the existing verified local KIS private intraday loader, canonical
  session calendar, and prospective-observer historical exclusion. Do not add
  another provider, source format, feature platform, or scheduler framework.
- KIS Paper market-data collection is allowed only through the existing owned
  collector when a missing forward outcome needs it. KIS account/order routes,
  `.env`/credential output, KIS live, public access, and all broker actions
  remain out of scope.
- Store raw market data only under `D:\market_data`; write commitments,
  receipts, and metadata only under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`. Never persist raw OHLCV, close values, return labels,
  account data, tokens, or identifiers in Git or artifacts.
- Keep the scope target-free: a witness may attest that an outcome window is
  recoverable, but it must not calculate or expose its return label, fit a
  model, compare a baseline, claim PnL, allocate GPU, or form an order intent.

## Required Work

1. Data Agent: inventory the existing forward observer and intraday collector
   contracts. Add the smallest value-free paired witness that binds an eligible
   future 15:30 input commitment to verified complete QQQ and SPY 15:31-15:45
   minute coverage and opaque outcome-content commitments. Historical 21
   sessions must remain excluded.
2. Make duplicate, conflict, unavailable, recovery, and post-window mutation
   behavior explicit and idempotent. A mutable whole-cache identity must not
   rewrite an earlier sealed input or outcome witness; a changed completed
   constituent must fail or produce a distinct conflict rather than silently
   overwrite evidence.
3. If the market is closed or no forward pair is present, run a local no-op
   verification and leave an exact `input_unavailable`/`zero_target_ready`
   fact. Do not make Codex wait. If a schedule is needed, attach it to the
   existing Data-owned worker with one bounded retry/recovery record.
4. Engine Research: consume only the source-safe count/identity result and
   restate the frozen 30-pair predictive dependency. Do not open outcomes or
   create model, CUDA, ensemble, validation, or Paper work.
5. Add focused tests for causal completed coverage, historical exclusion,
   source-safe persistence, duplicate/conflict recovery, post-window mutation,
   no credential/network/execution import behavior, and no KIS live/order
   route. Update Data, Engine, and orchestration stateboards.

## Completion Evidence

- one tested source-safe forward input/outcome witness contract;
- a local actual-cache result with target-ready count or a categorical exact
  gap, without a foreground market-time wait;
- no raw market values or labels outside `D:\market_data`, and no broker/live
  activity;
- commit and push, then replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
