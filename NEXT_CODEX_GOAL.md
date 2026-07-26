# Next Codex Goal

## Objective

Create a hash-bound, joint QQQ/SPY daily event-window and three-fold expanding
campaign contract that is ready for a later bounded model-breadth run.

The purpose is to make the existing long KIS-compatible daily history safe to
consume as a sequence input without treating its unadjusted prices as a
selection result. This objective advances the data-to-validation loop through
leakage control. It does not train a model, use the GPU, select a candidate, or
submit a Paper order.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest the existing QQQ/SPY KIS daily catalog, price-free Tiingo event
   sidecar, and event-boundary audit from their external manifests. Do not print
   rows, prices, credentials, provider responses, account facts, or broker data.

## Required Work

1. Build a pure offline joint event-window contract for the exact QQQ/SPY
   lineage. A candidate decision must be excluded for both symbols when either
   symbol has a qualified event anywhere in its actual feature/label dependency
   span `t-20..t+2`: the 20 completed-session feature rows are `t-19..t`, but
   the first return reads the predecessor close at `t-20`.
2. Freeze three expanding chronological validation folds over the reattested
   4,756-session daily catalog with initial development `[0, 3783)`. Each fold
   has a 252-session validation region and a 22-session pre-validation
   purge/warmup: `[3783, 3805) -> [3805, 4057)`, `[4057, 4079) -> [4079,
   4331)`, and `[4331, 4353) -> [4353, 4605)`. Preserve `[4605, 4756)` as the
   151-session unused tail for a later objective. Reject a contract that lacks
   enough eligible samples after joint masking rather than shrinking or moving
   these boundaries ad hoc.
3. Keep the contract source-safe and external: it may retain hashes, event
   dates/kinds, aggregate counts, fold boundaries, and eligibility identities,
   but not raw prices, returns, feature values, provider response bytes,
   credentials, or Git-resident artifacts.
4. Add focused tests for joint-symbol masking, 20-session feature containment,
   `t -> t+1 -> t+2` exclusion, deterministic fold geometry, immutable external
   artifact writing, and offline/no-credential/no-KIS/no-Tiingo behavior.
5. Ask Claude CLI for the required concise falsification-first leakage
   challenge before calling the contract model-executable. If its OAuth session
   remains unavailable, record only `review_unavailable` for that later
   model-execution boundary; preserve the contract as non-executable and keep
   independent lanes moving.
6. Have temporary Validation independently confirm the contract cannot expose a
   masked event window to a fold, access a network/credential/broker route, or
   write an artifact inside Git. Update the active stateboards with only the
   resulting cross-lane facts.

## Hard Boundaries

- This objective is offline. Do not read `.env`, call KIS or Tiingo, invoke a
  broker endpoint, inspect an account, submit/modify/cancel an order, or read
  any `KIS_LIVE_*` value. This restriction applies to this contract worker; it
  does not suspend an independently due, correctly scoped KIS Data worker.
- Do not train CPU/GPU models, run an architecture screen, tune a parameter,
  open/reuse a sealed holdout, select an ensemble, claim profitability, or
  produce a Paper decision.
- Keep all market bytes under `D:\market_data` and generated contract evidence
  under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never
  commit either.
- A Claude review failure is scoped to model-executability of this contract. It
  is not a hold on its deterministic construction, testing, or other ready work.

## Completion Evidence

- One immutable external contract with exact source lineage, joint-mask identity,
  fold geometry, eligible aggregate counts, and a source-safe content hash.
- Focused tests proving temporal/event masking, external artifact containment,
  and route isolation.
- Stateboards that name the candidate as non-executable until the named review
  boundary is satisfied, without treating it as a model result or Paper input.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A model-review tooling fault or an ineligible contract
does not stop independent ready work.
