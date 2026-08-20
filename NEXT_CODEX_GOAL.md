# Next Codex Goal

## Objective

Complete `tiingo-d1-trend-mean-reversion-rotation-falsification-v1`: run the
already frozen SPY/QQQ/IWM D1 trend-pullback mean-reversion rotation once
against its exact pinned Tiingo snapshot, independently verify its aggregate
receipt, and retain the result only as source-separated retrospective
falsification evidence.

## Boundaries

- Reattach only the existing immutable
  `snapshot=20260801T173121Z-tiingo-etf-d1-r1` identity through the verified
  loader. Do not download, refresh, or select another Tiingo snapshot.
- Do not read credentials, call KIS, a broker, Docker, or a network. Do not use
  GPU, train a model, create an ensemble, or modify Execution behavior.
- Freeze the existing 60-session trend, 5-session pullback, 20-session
  volatility, 61-session purge, 5/10/20-bps all-in cost band, and fixed
  comparators before the outcome is read. Do not tune after an outcome.
- Keep generated evidence under `D:\thericher-v2\model-artifacts`; keep raw
  market data under `D:\market_data`. Do not retain rows, prices, scores,
  per-decision outputs, credentials, or weights in Git or artifacts.
- This repeat-source control is non-promoting regardless of outcome. It cannot
  become a point-in-time claim, GPU appointment, KIS/Paper input, order,
  capital, or live behavior.

## Required Work

1. Reattach the pinned snapshot and frozen source-reuse/precommit contract
   before evaluating any result.
2. Run the existing offline rotation runner once with a unique external label;
   keep terminal output aggregate-only and source-safe.
3. Independently verify exact precommit, source, and summary bindings. Classify
   the fixed kill rule narrowly without reopening prior source-reuse families.
4. Add focused tests only if an actual isolation, identity, or receipt-binding
   gap is found.
5. Refresh active stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run required
   verification; commit, push, replace this file with exactly one material next
   objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
