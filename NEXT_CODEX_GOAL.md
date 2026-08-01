# Next Codex Goal

## Objective

Build and run one bounded CPU falsification of
`tiingo-d1-trend-mean-reversion-rotation-v1`: a trend-conditioned short-horizon
mean-reversion rotation over the existing immutable Tiingo D1 `SPY/QQQ/IWM`
snapshot. This advances the portfolio-selection stage of the engine without
claiming profitability, selecting a model, or creating an execution route.

## Start

1. Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`,
   `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active
   Engine Research, Research Steward, Data, Execution, and orchestration
   stateboards.
2. Ask Claude for a concise falsification-first drift check before freezing the
   campaign code. Include the causal decision/target timing, chronological
   split, event/discontinuity masking, costs, comparators, strongest kill test,
   and sealed-tail boundary. Do not include raw rows, credentials, or account
   facts.

## Fixed Source And Boundaries

- Read only the already retained local snapshot:
  `D:\market_data\us_equities\tiingo_etf_daily\canonical\snapshot=20260801T173121Z-tiingo-etf-d1-r1`
  with dataset hash
  `sha256:b47539a373bf2d625ad2380376808cf412219f6c5d932b66631bb3aa553683cf`.
  Reattest its manifest and hashes before use.
- No Tiingo API/network call, `.env` or credential read, KIS call, account
  read, broker order, local/live Paper action, dashboard, data download, or
  public service.
- Raw source rows remain on `D:`. Write only source-safe contract and aggregate
  result evidence to `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`; never write data, weights, predictions, or artifacts
  to Git.
- This is CPU-only. Do not allocate GPU, train a neural model, open the sealed
  tail, tune parameters, select a winner, ensemble candidates, or claim PnL or
  profitability.

## Frozen Campaign Contract

- Use the common completed D1 session calendar of `SPY`, `QQQ`, and `IWM`.
  At completed close `t`, each ETF is eligible only when its 60-session simple
  close-to-close trend is positive and its five-session simple return is
  negative. Score eligible ETFs by `(-five_session_return) / prior_20_session
  realized_volatility`, where volatility is the population standard deviation
  of the preceding 20 one-session simple close returns and a zero volatility
  rejects that ETF. Select the greatest score; ties use fixed symbol order
  `SPY`, `QQQ`, `IWM`. No eligible ETF means flat.
- A decision at `t` enters the selected ETF at `t+1` open and exits at `t+1`
  close. Exclude a decision when any fixed-universe component has a known
  dividend/split marker from `t-60` through `t+1`, or any absolute one-session
  close return above `20%` from `t-60` through `t`. This is retrospective
  source-local falsification only, not a prospective availability claim.
- Split decision dates before masking into chronological 60% development, 10%
  validation A, 10% validation B, and 20% sealed tail, with a 61-session purge
  between adjacent phases. Evaluate development only as plumbing evidence and
  validation A/B only for the frozen kill test. Do not read or report the
  sealed-tail rows after snapshot reattestation.
- Apply round-trip cost scenarios of `5`, `10`, and `20` bp to every active
  portfolio-day. Use `10` bp as the primary view. Fixed comparators are
  always-flat, equal-weight `SPY/QQQ/IWM` open-to-close, and a 60-session trend
  rotation that selects the greatest positive 60-session return using the same
  timing, mask, tie order, and costs.
- Kill the family if either validation block is flat-or-worse at `20` bp, or if
  across all three cost scenarios it is weaker than both active comparators.
  Do not alter a window, threshold, mask, split, tie rule, target, cost, or
  comparator after results are visible.

## Work

1. **Engine Research:** implement the pure campaign contract, verified local
   snapshot adapter, deterministic evaluation, and source-safe aggregate
   artifact writer. Keep numeric rows, scores, and individual returns in memory.
2. **Validation:** add focused tests for causal timing, common-calendar/split
   boundaries, masking, ties, all-flat behavior, cost accounting, kill logic,
   tail non-access, idempotent external artifact handling, and offline/no-
   credential/no-broker behavior.
3. **Research Steward:** record that this is CPU-only with no GPU or sealed-tail
   allocation. **Execution:** attest that it creates no intent, order, fill,
   account, or broker surface.

## Completion

- One immutable source-safe contract and CPU validation A/B result exist under
  the external artifact root.
- The sealed tail is untouched, and the result is either a clearly falsified
  family or a non-promoting validation fact that needs a separate future
  replication decision.
- Refresh this file with exactly one next objective, verify, commit, push, and
  continue without foreground waiting.

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

`Add Tiingo D1 mean reversion falsification`
