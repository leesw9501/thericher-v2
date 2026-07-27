# Next Codex Goal

## Objective

Build one fixed, source-safe QQQ/SPY D1 cross-fold falsification verifier over
the completed `expanding-1`, `expanding-2`, and `expanding-3` candidate-only
CPU/CUDA summaries. It may falsify a fixed candidate against a fold-local class
majority baseline, but it must not pool overlapping folds, rank candidates,
select a model, tune, ensemble, replay, create PnL, or produce a Paper input.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, DECISIONS.md, RUNBOOK.md, active stateboards,
   and the six immutable source-safe screen summary/precommit pairs under
   `D:\thericher-v2\model-artifacts\kis-daily-joint-event-d1-sequence-screen-v1`.
3. Reattest each exact E1/E2/E3 CPU/CUDA artifact hash, fold identity, target
   identity, split count, development-only normalization, candidate spec, and
   scope before comparing any aggregate metric.
4. Attempt one concise Claude falsification-first drift check for the proposed
   fixed failure rule. Do not send raw values, labels, credentials, account
   data, or unneeded artifact contents. Record an OAuth/tool failure as
   `review_unavailable` only.

## Required Work

1. Add a narrow offline verifier and runner with an explicit six-artifact pin
   map. Reject a missing, mismatched, non-canonical, non-external, unsafe, or
   unexpected artifact before reading aggregate metrics. Do not create a generic
   campaign/report framework.
2. Compare each frozen candidate only against the fold-local class-majority
   baseline derived from that summary's aggregate observed-positive/evaluated
   counts. Keep CPU and CUDA modes separate. Never pool, average, or weight
   overlapping folds; never output a winner, ranking, probability, threshold,
   prediction, label, row, PnL, replay, checkpoint, or action.
3. Predeclare the only allowed conclusion states: `falsified` when a candidate
   fails the fixed majority-baseline rule on a named mode/fold, otherwise
   `inconclusive`. Neither state is promotion, selection, or a Paper input.
4. Write one immutable source-safe external artifact under
   `D:\thericher-v2\model-artifacts`, then use temporary Data, Execution, and
   Validation roles to independently check lineage, no-pooling, source safety,
   and route isolation.
5. Add focused tests for pinning, unsafe/mismatched input rejection,
   fold-local-baseline logic, no-pooling, artifact-outside-Git behavior, and
   offline/no-credential/no-broker operation. Refresh stateboards/runbook only
   with resulting facts.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke a broker/account endpoint, or
  access `KIS_LIVE_*`.
- Do not retrain, start GPU work, select, rank, tune, ensemble, replay, create
  PnL, create a Paper intent, or enable live behavior.
- Keep market bytes under `D:\market_data` and generated artifacts outside Git
  under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Completion Evidence

- One hash-bound, source-safe external falsification artifact over exactly the
  six pinned summaries, with CPU/CUDA mode separation and no fold pooling.
- Independent Validation of exact lineage, no-pooling, source safety, and
  import/route isolation.
- No selected candidate, model artifact, replay, PnL, Paper, account, order,
  broker, or credential artifact.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or one candidate-local failure
does not stop independent ready work.
