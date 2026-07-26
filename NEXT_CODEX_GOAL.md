# Next Codex Goal

## Objective

Freeze one offline, fold-local D1 target and cost semantic adapter for the
reattested `expanding-1` QQQ/SPY materializer. It must convert an eligible
in-memory materialized window into one deterministic QQQ long-versus-flat
training target using only the already bound `t+1` and `t+2` opens, while SPY
remains a feature reference.

This is target plumbing only. It does not fit, score, replay, select, ensemble,
route, or submit a model decision.

## First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Read HANDOFF.md, AGENTS.md, ARCHITECTURE.md, DECISIONS.md, RUNBOOK.md,
   agents/orchestration.md, agents/data.md, agents/engine-research.md, and
   agents/execution.md.
3. Reattest only these external immutable inputs:

   ```text
   Parent:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-contract-v2.json

   Fold input:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-joint-event-window-fold-input-expanding-1-v1.json

   Materializer receipt:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-materializer-expanding-1-validation-first-v1.json
   ```

   Expected parent/fold/receipt hashes are respectively:
   `sha256:f908dd5570c795e94e92f54b3a9e243ee0c6cef641a557561bfc4db4983bb814`,
   `sha256:a15c26b6ce8f9c8c1e204cd8300b46241e2e7d894548666c73d32d030f790f0b`,
   and `sha256:247142b6f84f7e0ce88e538ea6832c083be2d1b29b66b079c99a2ad6d6b2f748`.

## Required Work

1. Add one pure offline target/cost adapter that accepts only a verified,
   reattested `expanding-1` materializer/window. It must reject a stale
   lineage, wrong fold, review-state mismatch, unverified receipt, sparse-hole,
   or `t+1/t+2` geometry mismatch before exposing a target.
2. Freeze a QQQ long-versus-flat binary target from QQQ `t+1` entry open and
   `t+2` exit open. Reuse the existing QQQ/SPY architecture screen's fixed
   per-fill economics: `1` fee basis point and `2` slippage basis points on
   both entry and exit. This is a deterministic label convention, not cost
   calibration, PnL evidence, or a trade instruction.
3. Keep feature and target values in memory. A source-safe external semantic
   receipt may contain only identities, formula/version, cost parameters,
   counts, timestamps, and index bounds; it must not persist raw bars, prices,
   returns, realized labels, predictions, checkpoints, credentials, orders, or
   PnL.
4. Do not modify generic `CampaignContract`, create a model-facing generic
   campaign, train CPU/GPU models, run a replay, tune a parameter, open/reuse a
   sealed holdout, select an ensemble, claim profitability, or produce a Paper
   decision.
5. Add focused tests proving causal `t+1/t+2` target alignment, sparse-mask
   preservation, exact fee/slippage semantics, stale/tampered input rejection,
   no raw target persistence, and no credential/KIS/Tiingo/broker/network
   behavior.
6. Ask Claude CLI for a concise falsification-first leakage and target-semantics
   check before relying on the adapter. If OAuth remains unavailable, preserve
   `review_unavailable` and continue this non-executable contract work.
7. Have temporary Validation independently inspect one frozen target contract
   and source-safe receipt. Refresh active stateboards with resulting
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
  approval hold for this target/cost adapter or another ready private lane.

## Completion Evidence

- One reattested, source-safe `expanding-1` D1 target/cost semantic receipt
  bound to the active parent, fold, and materializer identities.
- Focused tests proving causal target alignment, cost semantics, sparse-mask
  preservation, no raw persistence, and route isolation.
- Stateboards that identify the next non-executable campaign-preparation step
  without treating the adapter as a trained model or Paper input.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or one target-input rejection
does not stop independent ready work.
