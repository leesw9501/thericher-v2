# Next Codex Goal

## Objective

Build and run one bounded, CPU-only **L2 logistic trade-quality gate** for the
existing daily three-ETF relative-strength selector.

The gate must leave selection, sizing, entry timing, hold period, exit, and
execution untouched. It may only choose `enter` or `abstain` for an otherwise
eligible selector trade, then compare replayable `local_paper` outcomes against
the unmodified selector and cash.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, and all active
   stateboards under `agents/`.
3. Inspect the active KIS daily cache index and manifest metadata only. Do not
   need credentials, KIS, or network access for this objective.

## Frozen Contract

- Input: `kis.paper.private.daily.backfill-v1.common-panel`, `QQQ/SPY/IWM`,
  694 common daily sessions, `MODP=0_unadjusted`; preserve the corporate-action
  limitation.
- Geometry: 414 development sessions, two-session purge, 138 chronological
  validation sessions, then two-session embargo. Do not read the final 138
  `burned_precontract` sessions.
- At completed session `t`, calculate only: selected ETF 20-session return,
  its 20-session margin over runner-up, selected ETF 20-session realized
  volatility, and fraction of the three ETFs with positive 20-session return.
- Target: exact after-cost sign of the selector's `t+1` open to `t+2` open
  local-paper trade under the frozen 1 bp/side fee and zero slippage model.
- Model: one fixed L2 logistic model, development-only standardization, no
  threshold search, `enter` only at probability `>= 0.50`.
- Primary metric: validation mean normalized after-cost return per scheduled
  decision, abstentions scored as zero, plus candidate-minus-selector
  5-decision moving-block-bootstrap 95% lower bound.
- Secondary checks: accepted-trade count, Brier score versus the development
  prevalence predictor, maximum drawdown, and a predeclared 2 bp/side slippage
  stress.
- Stop and retire without retuning when development has fewer than 100 eligible
  entries or fewer than 25 observations of either label; or validation has
  fewer than 20 accepted trades, a non-positive primary lower bound, worse
  Brier/drawdown, or fails slippage stress. A pass is retrospective only and
  cannot promote an execution change.

## Work Packages

### Data Agent

- Re-attest the local index/manifests and derive isolated hash-bound development
  and validation slices. Do not call KIS or alter the source cache.

### Engine Research Agent

- Implement the candidate and a concise external campaign artifact under
  `D:\thericher-v2\model-artifacts`.
- Use deterministic CPU dependencies already present or a small compatible
  no-cost dependency if genuinely needed. Do not use GPU for this candidate.
- Record contract, inputs, model parameters, metrics, stop-rule verdict, and
  local-paper replay hashes outside Git.

### Validation

- Independently verify no validation/holdout bars reach development fitting,
  no KIS/network/credential path is required, all fills remain `local_paper`,
  and a failed stop rule cannot change execution behavior.

### Execution Agent

- Preserve the KIS virtual-paper canary recovery state as ready independent
  work. Do not modify broker routing for this research candidate.

## Boundaries

- No KIS call, credential read, broker action, paid data/model/service, public
  service, or live behavior is needed for this goal.
- Generated artifacts belong only under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`; market-data bytes remain under `D:\market_data`; do
  not commit either.
- Do not create a report/gate family. The campaign artifact and existing
  stateboards are sufficient.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add daily trade quality gate baseline`
