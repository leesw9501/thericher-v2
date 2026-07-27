# Next Codex Goal

## Objective

Run one fixed-specification, candidate-only QQQ/SPY D1 sequence screen on the
independent reattested `expanding-3` fold. It must not pool, tune from, or
select against the completed `expanding-1` and `expanding-2` screens. Produce
aggregate classification evidence only.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, the active stateboards, and the
   E3 source-safe fold/materializer/target receipts under the external artifact
   root.
3. Reattest the pinned E3 lineage before loading in-memory values. Expected
   fold artifact/identity are
   `sha256:40d6c9920a0edec12249f4b429c503b085b2e908466093496da8e0b6717128fc` /
   `sha256:1cf334306f1e2cc0e907d688d697c850aaf6ca0ef7ed2c42ee807f2c9633d11e`.
4. Attempt one concise Claude falsification-first drift-check before extending
   the explicit sequence-screen pin. Do not send raw values, labels,
   credentials, or account data; record an OAuth/tool failure as
   `review_unavailable` only.

## Required Work

1. Extend the existing candidate-only sequence screen and runner with only one
   explicit `expanding-3` pin. Preserve the completed E1/E2 artifacts and the
   frozen linear/compact-GRU candidate specifications, threshold, normalization
   policy, and v2 target/cost semantics. Do not create a generic campaign.
2. Consume only E3's exact `2671 / 145` sparse development/validation indices.
   Fit normalization on development only, retain `t-20..t+2`, and exclude the
   final 151-session tail.
3. Run one bounded CPU smoke and one network-disabled Docker CUDA screen with
   distinct immutable labels under the external artifact root. Persist only
   source-safe aggregate classification evidence, never rows, labels,
   predictions, weights, replay, PnL, broker data, or credentials.
4. Use temporary Data, Execution, and Validation roles for independent lineage,
   split/tail, source-safety, and import/route-isolation checks.
5. Add focused E3 pin/count/source-safety tests and refresh stateboards/runbook
   only with resulting facts.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke a broker/account endpoint, or
  access `KIS_LIVE_*`.
- Do not select a model, tune an input, form an ensemble, claim profitability,
  replay, create a Paper intent, or enable live behavior.
- Keep market bytes under `D:\market_data` and generated artifacts outside Git
  under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Completion Evidence

- Hash-bound CPU and CUDA aggregate summaries for E3 only.
- Independent Validation of E3 lineage, `2671 / 145` counts, tail isolation,
  source safety, and import/route isolation.
- No selection, replay, PnL, Paper, account, order, or broker artifact.

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
