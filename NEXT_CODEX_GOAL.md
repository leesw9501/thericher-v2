# Next Codex Goal

## Objective

Build one offline D1 sequence materializer for the reattested `expanding-1`
QQQ/SPY fold input. It must turn the existing local catalog into exact
in-memory feature/target windows for that one fold while preserving the frozen
`t-20..t+2` dependency and its sparse joint eligibility.

This is data plumbing only. It does not fit, score, replay, select, ensemble,
or route a model decision.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest only these external immutable artifacts:

   ```text
   Parent:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json

   Fold input:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-1-v1.json
   ```

   Expected parent hash/identity:
   `sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814` /
   `sha256:d8c1a382ca8a16b87288ede8f31df22797574940e50f0c208d4e28dc2677c2a6`.

   Expected fold hash/identity:
   `sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b` /
   `sha256:b019c7e9a10eb2add48bbaa815c046a9b216ca9069c4ca8e4f836bc91085a1db`.

## Required Work

1. Add a small offline materializer that accepts only the verified
   `expanding-1` input plus the matching local QQQ/SPY catalog. It must reject
   a hash, lineage, session-index, joint-mask, or review-state mismatch before
   exposing windows.
2. Materialize one decision index at a time in memory. Bind its 20 completed
   feature sessions, predecessor return dependency at `t-20`, decision at `t`,
   and label/open references at `t+1` and `t+2`. Never replace the sparse
   eligibility tuple with a continuous range.
3. Keep feature/target values in memory only. A source-safe external receipt
   may contain identities, schema, counts, timestamps, and index bounds, but
   no raw bars, prices, returns, labels, predictions, or checkpoints.
4. Do not modify generic `CampaignContract` and do not build a model-facing
   generic campaign yet. The output must stay offline, candidate-only, and
   `model_execution_eligible: false` under `review_unavailable`.
5. Add focused tests for exact `t-20..t+2` alignment, sparse hole preservation,
   stale/tampered input rejection, no raw-value persistence, and no
   credential/KIS/Tiingo/broker/network behavior.
6. Ask Claude CLI for a concise falsification-first leakage check before
   relying on the materializer for later model work. If OAuth remains
   unavailable, preserve the non-executable boundary and continue independent
   ready work.
7. Have temporary Validation independently inspect one frozen materialized
   input and its source-safe receipt. Refresh active stateboards with resulting
   cross-lane facts only.

## Hard Boundaries

- This objective is offline. Do not read `.env`, call KIS or Tiingo, invoke a
  broker endpoint, inspect an account, submit/modify/cancel an order, or read
  any `KIS_LIVE_*` value.
- Do not train CPU/GPU models, run a replay, tune a parameter, open/reuse a
  sealed holdout, select an ensemble, claim profitability, or produce a Paper
  decision.
- Keep market bytes under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- `review_unavailable` is a model-execution boundary only. It cannot become an
  approval hold for this materializer or another ready private lane.

## Completion Evidence

- One reattested, source-safe `expanding-1` D1 sequence input contract or
  receipt bound to both active artifact identities.
- Focused tests proving exact sequence alignment, sparse-mask preservation,
  no raw persistence, and route isolation.
- Stateboards that identify the next non-executable campaign-preparation step
  without treating the materializer as a model or Paper input.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or one materializer-input
rejection does not stop independent ready work.
