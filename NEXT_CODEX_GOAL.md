# Next Codex Goal

Continue TheRicher v2 from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first fixed-instrument daily development campaign and, only if its
Data contract is sound, run one bounded PyTorch CUDA breadth experiment.

Use existing daily data before acquiring more. Predeclare instruments in this
order: `SPY`, `QQQ`, `IWM`; do not substitute or rank them from observed
performance. This advances data qualification, feature/model research,
walk-forward validation, PnL attribution, and paper-execution readiness.

## Start

1. Run `.\scripts\start_next_codex_task.ps1` and read the required handoffs.
2. Orchestrate bounded Data, Engine Research, Execution, and temporary
   Validation work in parallel where files do not conflict.
3. Ask Claude for one falsification check before accepting the adjustment,
   split, target, or GPU experiment contract.

## Boundaries

- No credentials, KIS, broker/account calls, external orders, paid data, or
  live behavior.
- Market data stays under `D:\market_data`; artifacts stay under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Historical daily work is development evidence only. Do not claim ranking,
  promotion, sealed-holdout independence, or profitability.
- Do not add a job/report family, scheduler, daemon, dashboard, durable role,
  dependency framework, or broad model search.

## Required Work

### Data

1. Inspect only the newest useful daily snapshot for `SPY`, `QQQ`, and `IWM`.
2. Define and test one explicit OHLCV adjustment policy, ordering rule, quality
   summary, and hash-bound local subset/manifest on `D:`.
3. Distinguish parser, development-training, ranking, and sealed-holdout
   eligibility. Stop if the data cannot honestly support development training.

### Engine Research

1. Run all frozen naive baselines through a daily forward campaign with
   non-overlapping folds, purge/embargo, next-open execution, nonzero slippage,
   and durable `source: local_paper` replay evidence.
2. If Data marks development training eligible and Claude does not reject the
   contract, run one small fixed candidate set in Docker with PyTorch CUDA.
   Compare against naive baselines after costs; keep it development-only.
3. Do not start depth training or model promotion in this goal.

### Execution

1. Add the smallest deterministic pre-submit risk decision for persisted
   `BrokerOrderRequest`s using existing `RiskLimits` and typed account/buying-
   power evidence.
2. Prove oversized, stale, missing, unknown, and duplicate evidence fails
   closed before the fake transport. Keep KIS disabled.

### Validation And Integration

1. Independently test byte lineage, adjustment math, split/target timing,
   costs, replay hashes, risk fail-closed behavior, and artifact placement.
2. Run simplification review, update concise stateboards and `HANDOFF.md`, then
   refresh this file with the next single company objective.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report focused Data/CPU/risk/Validation commands and any Docker CUDA
command, artifact paths, GPU use, data gaps, intentionally omitted work,
commit hash, and push result.

## Suggested Commit Message

`Run fixed-instrument daily development campaign`
