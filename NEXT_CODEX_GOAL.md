# Next Codex Goal

## Objective

Prepare the second independent QQQ/SPY D1 validation fold without using the
first-fold model results to tune anything. Reattest only `expanding-2` from the
active v2 parent, then build its pure fold-local materializer and deterministic
v2 target/cost semantics as source-safe external evidence.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest the existing external parent only:

   ```text
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json
   ```

   Its expected artifact hash/identity remain
   `sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814` /
   `sha256:d8c1a382ca8a16b87288ede8f31df22797574940e50f0c208d4e28dc2677c2a6`.

## Required Work

1. Produce one immutable, source-safe `expanding-2` fold input under the
   external artifact root. It must be locally reattested against the rebuilt
   parent, retain its exact `2,511` development and `128` validation sparse
   decisions, and not copy raw market values into the artifact.
2. Generalize only the pure D1 materializer and target/cost adapter boundary
   necessary to bind one verified named fold at a time. Do not merge folds,
   create a generic multi-fold campaign, or change `expanding-1` identities or
   receipts. Preserve `t-20..t+2`, QQQ `t+1/t+2` target semantics, 1/2-bps
   costs, `0.0001` half-even quantization, and Decimal precision 34.
3. Write one new immutable source-safe materializer receipt and one new
   source-safe target/cost receipt for `expanding-2`. They may contain lineage,
   count, timestamp/index geometry, formula, and scope metadata only; no rows,
   prices, returns, labels, predictions, model weights, PnL, credentials,
   accounts, orders, or broker payloads.
4. Add focused tests for named-fold isolation, exact sparse counts, final
   151-session tail exclusion, `expanding-1` regression protection, target
   context independence, Docker `/app/market_data` and `/app/model_artifacts`
   mount handling, and no Data/Execution/broker/network path on pure imports.
5. Ask Claude CLI for one concise falsification-first drift-check before
   relying on the generalized fold boundary. If OAuth remains unavailable,
   record `review_unavailable`; reattestation and non-executable evidence may
   continue, but no selection, replay, Paper, or promotion follows.
6. Have temporary Validation independently inspect the `expanding-2` input and
   one materializer/target receipt. Refresh stateboards with only changed facts.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke a broker endpoint, inspect an
  account, submit/modify/cancel an order, or read any `KIS_LIVE_*` value.
- Do not train, replay, select a model, tune from the first-fold summaries,
  form an ensemble, claim profitability, derive a Paper decision, or enable
  live behavior.
- Keep market bytes under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- `review_unavailable` limits promotion/execution only. It cannot become a hold
  for this candidate-only contract work or another ready private lane.

## Completion Evidence

- External immutable `expanding-2` fold input plus materializer and target/cost
  receipts with verified hashes and source-safe scope.
- Focused fold-isolation, causal-geometry, target-determinism, mount, and pure
  route-isolation tests.
- Independent Validation result; no model/replay/Paper artifact.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or one fold-local failure does
not stop independent ready work.
