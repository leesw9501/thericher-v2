# Next Codex Goal

## Objective

Complete `firstrate-m5-mean-reversion-after-cost-control-v1`: test one fixed,
source-local 5m SPY/QQQ mean-reversion rule through the existing deterministic
local-paper simulator and reject it unless it beats `always_flat` after costs
for each symbol across the fixed 1/3/5-bps-per-side band.

## Boundaries

- Reattach the existing FirstRate normalization, timeframe-mechanics, and
  window-preflight evidence before consuming source-local Bars. Do not download
  data, call KIS, read credentials, call a broker, or use a Docker service.
- Freeze the conventional long-only rule before an outcome is read: enter after
  a completed 14-bar RSI is at or below 30, exit after a completed RSI is at or
  above 50, and force terminal flatness. Use next-bar local-paper fills only.
- Use the fixed 5m source-local geometry, 60-bar observation window, 61-bar
  embargo, and fixed 1/3/5-bps cost band. Do not tune RSI windows, thresholds,
  holding rules, costs, timeframe, or direction after seeing outcomes.
- Keep all generated summaries and validation receipts outside Git under
  `D:\thericher-v2\model-artifacts`. Do not store raw bars, features, model
  weights, credentials, or broker data in Git or artifacts.
- This is a non-promoting source-local breadth control: no model training,
  GPU allocation, ensemble, KIS/Paper consumer, Execution change, or live
  behavior follows regardless of result.

## Required Work

1. Freeze a source-safe campaign/precommit contract with the rule, data
   identities, chronological split, baseline, costs, kill test, and artifact
   root before any outcome is calculated.
2. Implement the rule and runner by extending existing FirstRate local-paper
   control patterns without duplicating unrelated closed-lineage behavior.
3. Add focused tests for completed-bar RSI timing, next-bar/local-paper-only
   fills, terminal flatness, cost-band comparison, deterministic replay, and
   artifact-root isolation.
4. Run one CPU-only external smoke, independently validate its aggregate
   receipt, and record `rejected` unless every fixed symbol/cost comparison
   beats `always_flat`.
5. Refresh the active stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run the
   required verification; commit, push, replace this file with exactly one
   material next objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
