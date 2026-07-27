# Next Codex Goal

## Objective

Build the first source-partitioned D1 liquidity-eligibility fact for offline
opportunity research. It must test only whether each already attested current
instrument has enough completed local D1 history and observed daily turnover for
offline research eligibility. It must not turn that fact into a historical
universe, a cross-sectional ranking, a model signal, a Paper input, or a claim
of executable liquidity.

## Start

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`,
   and all active stateboards.
3. Reattest the existing source-scoped liquid-universe manifest and its two
   source partitions before reading any bars. Do not broadly scan `D:`.
4. Ask Claude for a short falsification-first challenge of the proposed D1
   liquidity interpretation. Do not send rows, prices, volumes, credentials,
   account data, or sealed labels. An OAuth failure is `review_unavailable`,
   not a hold on private offline work.

## Work

1. **Data:** define one small, deterministic D1 eligibility contract. Per
   source partition only, require at least 60 completed D1 bars, 20 recent
   completed D1 bars with positive volume, and a 20-bar median dollar-turnover
   threshold of USD 10,000,000. Freeze the thresholds and source/feature
   semantics in a source-safe external receipt; do not persist raw prices,
   volumes, rows, or derived numeric turnover values.
2. **Data:** use only the verified QQQ/SPY/IWM private daily catalog and the
   verified six-symbol current NAS panel. Preserve source partitions: do not
   align, compare, rank, or blend the ETF and NAS groups. A source-limited IWM
   history fact remains visible rather than being repaired or excluded by
   inference.
3. **Engine Research:** add one pure offline consumer that receives the
   per-instrument `eligible` or `ineligible` D1-research fact together with its
   source partition and limitations. It must not score, rank, select a symbol,
   fit a model, run local-paper replay, use the GPU, read credentials, call a
   provider, or reach a broker.
4. **Validation:** add focused tests for deterministic reattestation,
   source-partition isolation, completed-bar-only calculations, threshold
   boundaries, safe external outputs, no network/credential/broker access, and
   rejection of historical-membership, ranking, Paper, or executable-liquidity
   misuse.
5. **Execution:** leave the installed prospective QQQ scheduler lane-owned.
   Reattach a naturally arriving terminal receipt only; do not manually invoke
   it and do not make it a completion condition.

## Boundaries

- Do not call KIS, read `.env` or credentials, submit/modify/cancel an order,
  enable live behavior, expose a public service, or download data for this goal.
- `KIS_LIVE_*` remains unreadable and unavailable.
- Keep market data under `D:\market_data`, generated artifacts under
  `D:\thericher-v2\model-artifacts`, and never commit either.
- D1 turnover is an offline data-eligibility proxy only. It does not establish
  intraday liquidity, spread, depth, market impact, shortability, fillability,
  historical PIT membership, a stock rank, model quality, or Paper eligibility.
- Do not retune, revive, ensemble, or route the falsified CACC-D1, tree,
  linear, or sequence candidates.

## Completion

- One immutable source-safe D1 eligibility receipt is externally stored and
  reattestable from existing local sources.
- An offline consumer preserves each source partition and the eligibility fact
  without producing a score, action, model, replay, or broker input.
- Every limitation remains explicit and no raw rows, price/volume values,
  credentials, account data, order data, weights, or model artifacts persist.
- Any scheduled QQQ evidence remains lane-owned and does not delay this goal.

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

`Add source-partitioned D1 liquidity eligibility`
