# Next Codex Goal

## Objective

Reattest the third independent QQQ/SPY D1 `expanding-3` fold as a source-safe,
candidate-only input. Produce only its fold input, one materializer geometry
receipt, and one deterministic v2 target/cost receipt. Do not pool, compare,
select, or replay the completed `expanding-1` and `expanding-2` screens.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, the active stateboards, and the
   parent plus completed E1/E2 source-safe contracts under the external
   artifact root.
3. Attempt one concise Claude falsification-first drift-check before extending
   an explicit fold pin. Do not send raw market values, labels, credentials, or
   account data. Record an OAuth/tool failure as `review_unavailable` only.

## Required Work

1. Rebuild and hash-verify the existing parent locally, then create exactly one
   external `expanding-3` fold-input artifact. It must bind the same parent
   lineage, exact `2671 / 145` sparse development/validation counts,
   `t-20..t+2` dependency, and final 151-session tail exclusion.
2. Extend the pure materializer and v2 target/cost adapter with only one
   explicit `expanding-3` pin. Do not introduce a generic multi-fold campaign
   or alter E1/E2 identities, candidate specifications, thresholds, or result
   artifacts.
3. Write one immutable, source-safe E3 validation materializer receipt and one
   immutable, source-safe E3 target/cost receipt under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
4. Use temporary Data, Execution, and Validation roles for independent lineage,
   source-safety, and route-isolation checks. Keep their work parallel where
   ownership does not conflict.
5. Add focused tests for E3 pin/count/geometry and Docker external-mount
   handling. Refresh the stateboards and runbook with only changed facts.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke a broker/account endpoint, or
  access `KIS_LIVE_*`.
- Do not train a model, run a CUDA screen, select a model, tune an input, form
  an ensemble, claim profitability, replay, create an intent, or enable live
  behavior.
- Keep market bytes under `D:\market_data` and generated artifacts outside Git
  under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Persist no rows, prices, labels, predictions, weights, PnL, broker data,
  account data, or credentials in the new receipts.

## Completion Evidence

- Hash-bound E3 fold input and source-safe materializer/target-cost receipts.
- Independent Validation of parent lineage, `2671 / 145` counts, tail
  isolation, source safety, and import/route isolation.
- Focused tests and no training, replay, Paper, account, or broker artifact.

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
