# Next Codex Goal

## Objective

Falsify one fixed, ETF-source-local D1 trend-regime control using the completed
source-partitioned eligibility receipt. This is a deterministic offline Research
screen, not stock selection, model promotion, an ensemble, or a KIS Paper input.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`,
   and all active stateboards.
3. Reattest the current source-scoped universe and D1 eligibility receipt before
   loading the named ETF streams. Do not scan `D:` broadly.
4. Ask Claude for a concise falsification-first challenge of the fixed causal
   rule, leakage checks, chronological split, cost comparator, and kill rule.
   Do not send rows, prices, credentials, account data, or sealed labels. An
   OAuth failure is `review_unavailable`, not a hold on this private screen.

## Work

1. **Data:** consume only the ETF source partition (`QQQ`, `SPY`, `IWM`) from
   the reattested receipt. Reopen each verified D1 stream independently; retain
   IWM's source-limited history scope. Do not compare, rank, align, or blend
   instruments, and do not use the current NAS basket for this control.
2. **Engine Research:** freeze one causal, non-overlapping D1 trend-regime rule:
   at completed session `t`, a symbol is long-eligible only when its closing
   price is above its completed 50-session simple moving average and its
   completed 20-session average is above its completed 50-session average.
   Enter at `t+1` open, exit at `t+2` open, and skip a new signal while that
   one-share local-paper position is open. Use no fitted parameters.
3. **Validation:** use a fixed chronological 70/30 development/validation
   boundary per ETF, with no tuning between them. Compare the exact same
   non-overlapping cadence against an always-long local-paper comparator with
   the existing fixed daily fee/slippage model. The fixed rule is falsified if
   it fails to exceed its comparator after costs on every ETF validation slice.
4. **Evidence:** write one source-safe external precommit and summary under
   `D:\thericher-v2\model-artifacts`; retain only hashes, dates/counts,
   aggregate metrics, categorical result, and limitations. All fills must be
   `source: local_paper`. Do not persist raw rows, feature values, weights,
   checkpoints, credentials, account data, or broker payloads.
5. **Execution:** leave the installed prospective QQQ scheduler lane-owned.
   Reattach only naturally arriving receipts; do not invoke it manually or make
   it a completion condition.

## Boundaries

- Do not call KIS, read `.env` or credentials, download data, submit/modify/
  cancel orders, enable live behavior, or expose a public service.
- Do not retune, revive, ensemble, or route the falsified CACC-D1, tree,
  linear, or sequence candidates.
- Do not use the result to rank symbols, select a model, allocate GPU work, or
  create a Paper input. GPU stays available for a separately eligible frozen
  campaign.
- Market data remains under `D:\market_data`; generated artifacts remain under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; neither enters
  Git.

## Completion

- One reattestable source-local ETF D1 precommit/summary exists externally.
- The rule, causal timestamps, non-overlap behavior, split, costs, comparator,
  and falsification outcome are deterministic and tested.
- No source partition becomes a rank, model, ensemble, Paper, or live input.
- The prospective scheduler remains independent of this objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Add ETF D1 trend-regime baseline`
