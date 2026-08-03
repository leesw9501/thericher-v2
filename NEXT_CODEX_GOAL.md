# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-supervised-dataset-contract-v1`: turn a valid
forward-campaign readiness receipt into the exact first private supervised
dataset contract for the `short` QQQ/SPY multi-timeframe engine.

This is the first target-opening boundary. It must be deterministic and
replayable, but its implementation and tests must proceed now even though the
current real inventory has zero forward target-ready pairs.

## Boundaries

- Ask Claude for one concise falsification-first drift check before choosing
  the target timestamp, chronological selection, or split semantics.
- Accept only a reattested
  `ready_for_private_campaign_freeze` readiness receipt whose opaque policy,
  forward-outcome contract, and inventory identities exactly match current
  Data evidence. A below-threshold result remains scoped input unavailable and
  does not block implementation or other lanes.
- On a ready inventory, select the first 30 target-ready pairs in verified
  chronological order. For each leg, derive only the predeclared log return
  from the last completed causal M1 close ending at 15:30 ET to the final
  completed outcome M1 close ending at 15:45 ET. Do not use a later bar or
  use row-index alignment across timeframes.
- Freeze the pair-level `20 train / 2 purge / 8 validation` chronology before
  any model sees a target. Persist raw/value-bearing dataset material only
  under `D:\market_data`; persist only hashes, shapes, split counts, and
  source-safe receipts under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`.
- Do not call KIS, read `.env` or credentials, use broker/account/order/Paper
  routes, enable live behavior, expose a service, train a model, allocate GPU,
  calculate PnL, or add a generic dataset platform.

## Required Work

1. Data Agent: add the smallest read-only loader for the selected existing
   forward witnesses and D:-resident snapshots. Reattest every witness and
   snapshot hash, reject malformed/missing/changed content, and make an absent
   or insufficient store a recoverable local result without creating paths.
2. Engine Research: freeze the immutable dataset/target/split contract and a
   source-safe external receipt. Bind it to the exact readiness receipt and
   selected snapshot identities; the target-bearing materialization stays only
   in D: and is not a model, comparative result, or GPU appointment.
3. Add focused tests for target endpoint timing, chronological first-30
   selection, pair-level purge, snapshot mutation/missing rejection, stale
   readiness rejection, external artifact isolation, D:-only value retention,
   and no credential/network/execution route.
4. Reattach the real inventory once. If it remains below threshold, report the
   exact count and leave no target-bearing dataset artifact behind. Update the
   Engine Research, Research Steward, Data, and orchestration stateboards.

## Completion Evidence

- a tested exact target/split contract and replayable fixture materialization;
- a real local inventory result with no false training or promotion claim;
- no raw or target values in Git/model artifacts; commit, push, and replace
  this file with the next single objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
