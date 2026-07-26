# Next Codex Goal

## Objective

Build a fold-local, offline consumer for the active schema-v2 QQQ/SPY joint
event-window contract so a later bounded research campaign can use its exact
eligibility without collapsing overlapping expanding folds into one generic
`CampaignContract`.

This objective prepares a safe input adapter only. It does not train, replay,
select, ensemble, promote, or submit a Paper decision.

## First Reads

1. Run:

~~~powershell
.\scripts\start_next_codex_task.ps1
~~~

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest only the active external v2 artifact:

   ```text
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json
   ```

   Its expected artifact hash is
   `sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814`
   and its expected contract identity is
   `sha256:d8c1a382ca8a16b87288ede8f31df22797574940e50f0c208d4e28dc2677c2a6`.
   Do not use the historical v1 artifact as the active input.

## Required Work

1. Add a pure offline loader/rebuilder that verifies the active artifact's
   schema, hash, lineage, joint-event identity, fixed fold geometry, and
   `review_unavailable` status before exposing a fold-local input.
2. Make one fold-local input at a time. It must bind the exact development,
   purge, validation, target-policy, and sparse joint-eligibility identity for
   that fold. It must never silently replace sparse eligibility with a
   continuous date range.
3. Keep the existing generic `CampaignContract` unchanged. If an adapter is
   useful, it may prepare one independent generic campaign per fold later, but
   it must reject an attempt to encode all expanding folds as one generic
   campaign.
4. Add focused tests for artifact/hash tampering, stale v1 rejection,
   fold-local identity preservation, event-mask identity preservation, no raw
   value persistence, and offline/no-credential/no-KIS/no-Tiingo/no-broker
   behavior.
5. Ask Claude CLI for a concise falsification-first architecture check before
   relying on the adapter for model work. If OAuth remains unavailable, retain
   `review_unavailable` and keep the adapter non-executable; continue other
   ready work.
6. Have temporary Validation independently test the active artifact and one
   fold-local consumer after it is frozen. Update active stateboards with only
   resulting cross-lane facts.

## Hard Boundaries

- This objective is offline. Do not read `.env`, call KIS or Tiingo, invoke a
  broker endpoint, inspect an account, submit/modify/cancel an order, or read
  any `KIS_LIVE_*` value.
- Do not train CPU/GPU models, run a replay, tune a parameter, open/reuse a
  sealed holdout, select an ensemble, claim profitability, or produce a Paper
  decision.
- Keep all market bytes under `D:\market_data` and generated evidence under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- `review_unavailable` is a model-execution boundary only. It must not become
  an approval hold for the adapter or another ready private lane.

## Completion Evidence

- One reattested, source-safe fold-local input contract or immutable adapter
  evidence bound to the active v2 artifact.
- Focused tests that prove exact one-fold eligibility preservation and route
  isolation.
- Stateboards that keep the adapter non-executable and identify its next
  consumer without treating it as a model or Paper input.

## Verification

~~~powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
~~~

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or a fold-local input rejection
does not stop independent ready work.
