# Next Codex Goal

## Objective

Run one bounded, sealed local-paper falsification of the frozen NAS D1
volatility-conditioned trend candidate package. This is a fixed evaluation of
already-frozen CPU and CUDA candidates and declared naive comparators, not a
new training, parameter search, model selection, ensemble, promotion, or KIS
Paper decision.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and active stateboards.
2. Reattest the source-local NAS D1 panel and the frozen volatility/trend
   campaign precommit before opening any validation target.
3. Ask Claude for a concise falsification-first review of the sealed-evaluation
   contract. If OAuth remains expired, record `review_unavailable` and continue
   this private, candidate-only package without treating it as a promotion.

## Contract

- Consume only the existing six-symbol source-local NAS D1 panel and the exact
  CPU/CUDA r2 candidate artifacts from the volatility-conditioned campaign.
- Freeze evaluation slots, target timing, fixed after-cost local-paper model,
  comparators, aggregation, metrics, candidate identifiers, and strongest kill
  rule before reading validation targets or checkpoints.
- Use in-memory validation targets and replayable fills labelled
  `source: local_paper`. Retain only source-safe aggregate, immutable evidence
  outside Git; never retain raw bars, target values, predictions, per-fill rows,
  account identifiers, or checkpoint copies.
- Evaluate every frozen candidate independently against fixed comparators,
  including the ungated 5-day trend and volatility-gated 5-day trend rules.
  Do not rank candidates, choose a winner, tune any threshold, create an
  ensemble, or use an outcome as a KIS Paper input.
- The primary kill rule is fixed before evaluation: a candidate fails unless it
  strictly improves paired after-cost aggregate return versus ungated 5-day
  trend without worsening maximum drawdown. A pass remains candidate-only and
  cannot promote an action.

## Work

1. **Data:** provide only reattested source-local panel and phase identity;
   do not fetch, mutate caches, or reinterpret current listings as a PIT
   universe.
2. **Engine Research:** write immutable evaluation precommit, load only the
   frozen candidate checkpoints with safe weights-only loading, and run one
   network-disabled Docker sealed local-paper evaluation.
3. **Validation:** independently prove target isolation before the evaluation,
   external artifact containment, immutable artifact hashes, replayable
   `local_paper` fill source, terminal-flat accounting, and no KIS/network/
   credential route.
4. **Execution:** remain independent. Do not create an intent, query KIS, or
   submit, modify, or cancel any broker order.

## Boundaries

- No KIS call, `.env` or credential read, provider download, paid asset, public
  service, account/quote/order route, broker submission, or live behavior.
- Do not inspect or use prior sealed NAS r4 aggregate outcomes to choose,
  exclude, tune, or interpret this candidate set.
- Do not create report/gate scaffolding. A failed candidate closes only its own
  fixed claim and cannot block Data, Execution, scheduled collection, or a
  distinct ready Research package.

## Completion

- Immutable precommit and source-safe evaluation summary are written outside
  Git with reattested candidate/panel lineage.
- All frozen candidates receive a categorical independent result under the
  fixed kill rule, or a scoped immutable failure receipt identifies the exact
  input/runtime fault.
- Tests prove local-paper-only replay, target isolation, artifact containment,
  safe checkpoint loading, and no KIS/network/credential/broker access.
- Refresh stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Evaluate NAS volatility trend candidates`
