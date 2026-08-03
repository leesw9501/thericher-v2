# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-cpu-campaign-executor-v1`: the smallest fixed,
CPU-first research execution path that can consume the D:-only profiled-MTF
forward supervised dataset when it exists.

It must turn the already frozen `short` QQQ/SPY input/target/split contract
into a repeatable candidate comparison without waiting for market time. The
implementation and fixture evidence proceed now; the current real zero-pair
result remains scoped input unavailable.

## Boundaries

- Ask Claude for one concise falsification-first check before freezing the
  feature representation, candidate family, and evaluation interpretation.
- Reattest the forward supervised dataset, readiness receipt, snapshot hashes,
  chronological pair order, and `20/2/8` pair split before any candidate sees
  a target. A stale/missing/zero dataset must return scoped input unavailable,
  create no model/GPU artifact, and block only this exact campaign run.
- Use the fixed `short` causal windows (`1m/5m/10m/1h/3h`) without pretending
  their rows are timestamp-aligned. Derive features only from completed input
  bars ending at 15:30 ET; targets remain the already frozen 15:45 ET returns.
- Start with one CPU-only, predeclared no-trade baseline and a small fixed
  family of deterministic classical controls. Do not tune after validation,
  claim profitability/PnL, select a winner, create a Paper intent, or allocate
  GPU in this objective.
- Do not call KIS, read `.env` or credentials, use broker/account/order/Paper
  routes, enable live behavior, expose a service, download data, or create a
  generic campaign platform.
- Keep target/feature values and any fixture-only materialization under
  `D:\market_data`; external receipts under
  `D:\thericher-v2\model-artifacts` contain source-safe hashes, shapes,
  metrics categories, and status only. Never store generated models in Git.

## Required Work

1. Data/Engine: add the smallest immutable reader for a materialized forward
   supervised dataset and its referenced snapshots. It must reject D: content
   mutation, stale receipt binding, missing row/snapshot identity, invalid
   first-30 ordering, or pair-split drift without creating paths.
2. Engine Research: freeze one compact CPU campaign contract with its exact
   causal MTF feature shape, baseline, fixed classical controls, loss/metric
   interpretation, strongest kill test, and stop rule. Keep all candidate
   configuration predeclared before the validation pairs are opened.
3. Add a focused fixture runner that proves deterministic replay, no target
   leakage into features, pair-level purge exclusion, source-safe external
   receipt isolation, and no network/credential/execution import. It must
   produce `input_unavailable` against the real current zero-pair inventory.
4. Reattach the real local source once. Update Data, Engine Research, Research
   Steward, and orchestration stateboards. Do not make a GPU custody
   appointment from this CPU contract.

## Completion Evidence

- a tested D:-only dataset reader and fixed CPU campaign contract;
- fixture-only deterministic baseline/control execution with no promotion;
- a real local zero-or-ready receipt with truthful scoped status;
- no raw/feature/target/model values in Git or model artifacts; commit, push,
  and replace this file with the next single objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
