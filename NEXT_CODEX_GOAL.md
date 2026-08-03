# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active stateboards in `agents/` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `profiled-mtf-forward-campaign-readiness-v1`: make the next predictive
research campaign automatically recognizable from Data's existing source-safe
forward-outcome inventory, without opening any raw snapshot, price, feature,
return, target, or label.

The engine must be able to continue useful preparation while the Data-owned
forward collector accumulates sessions. This is a small contract bridge, not a
second scheduler, generic campaign platform, model, backtest, or Paper route.

## Boundaries

- Consume only `KisMtfProfiledForwardOutcomeInventory` and its opaque contract
  and manifest identities. Do not open individual witness files or D:-resident
  raw snapshots.
- Freeze the already predeclared initial campaign shape only as readiness
  metadata: `short` QQQ/SPY pairs, 30 target-ready pairs, `20/2/8` temporal
  train/purge/validation allocation, 20bp round-trip cost sensitivity,
  no-trade baseline, blocked-session target-permutation kill test, CPU-first,
  and a ten-minute maximum CUDA appointment. Do not calculate or inspect
  outcomes, returns, labels, scores, or PnL.
- A count below 30 is a scoped `input_unavailable` result, not an approval,
  scheduler, GPU, Paper, or company-wide hold. At or above 30, emit only a
  source-safe `ready_for_private_campaign_freeze` receipt; a later goal owns
  label opening and the distinct frozen predictive campaign.
- Do not read `.env` or credentials; call KIS; use a broker/account/order
  route; create a Paper action; enable live behavior; expose a service; add a
  provider; modify market-data cache; or introduce a generic workflow layer.
- Artifacts belong only under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`, never Git. Do not persist raw values, targets,
  predictions, weights, or model artifacts.

## Required Work

1. Engine Research: implement the minimal immutable readiness contract and
   source-safe external receipt. Bind it to the exact forward-outcome observer
   contract and opaque target-ready manifest hash; reject forged, inconsistent,
   malformed, or stale inventory identities.
2. Data Agent: reattach the existing forward-outcome inventory only and report
   its categorical readiness. Do not collect, mutate, or reinterpret source
   data. Execution has no work in this objective.
3. Add focused tests proving the below-threshold and ready cases, immutable
   identity binding, malformed-input rejection, external artifact isolation,
   idempotent receipt behavior, and absence of credential/network/execution
   routes.
4. Update Engine Research, Research Steward, Data, and orchestration
   stateboards with the resulting readiness state. Do not allocate GPU merely
   for a readiness receipt.

## Completion Evidence

- one tested source-safe readiness receipt tied to the exact opaque Data
  inventory;
- explicit non-blocking behavior below threshold and no target/model/PnL/Paper
  claim;
- external-only artifacts, commit, push, and replacement of this file with the
  next single objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```
