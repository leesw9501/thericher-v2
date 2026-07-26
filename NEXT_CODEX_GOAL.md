# Next Codex Goal

## Objective

Run one fixed-specification, candidate-only QQQ/SPY D1 sequence screen on the
independent reattested `expanding-2` fold. It must neither tune from nor select
against `expanding-1`; it produces aggregate classification evidence only.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, RUNBOOK.md, the active stateboards, and the
   three source-safe `expanding-2` external artifacts.
3. Reattest the pinned parent/fold/materializer/target lineage before loading
   any in-memory values. Expected fold input artifact/identity are
   `sha256:79723a4713b5a4751b6a62ddcd700b67542012bf3ff17a44958b7bd3d67c9305` /
   `sha256:6507570e49022133ff1055d49d610a6c32e80b92c0f881115f67d9e68e899f4e`.

## Required Work

1. Reuse the completed `expanding-1` screen's fixed linear and compact-GRU
   candidate specifications without changing hyperparameters, thresholds,
   normalization policy, or cost semantics from its summaries.
2. Use only `expanding-2` exact sparse indices: 2,511 development and 128
   validation decisions. Development-only normalization is required; retain
   `t-20..t+2` geometry and exclude the final 151-session tail.
3. Run one bounded CPU smoke and one network-disabled Docker CUDA screen,
   each writing only source-safe, aggregate classification evidence under the
   external artifact root. Do not persist rows, labels, predictions, model
   weights, replay, PnL, broker data, or credentials.
4. Temporary Validation must independently check lineage, counts, split/tail
   isolation, source safety, and import/route isolation.
5. Keep Claude's current OAuth failure as `review_unavailable`: it prevents
   selection, replay, promotion, and Paper use, but not this candidate-only
   evidence run.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke broker/account endpoints, or
  access `KIS_LIVE_*`.
- Do not select a model, tune an input, form an ensemble, claim profitability,
  replay, create a Paper intent, or enable live behavior.
- Keep generated artifacts outside Git under `D:\thericher-v2\model-artifacts`
  or `/app/model_artifacts`; keep market bytes under `D:\market_data`.

## Completion Evidence

- Hash-bound CPU and CUDA aggregate summaries for `expanding-2` only.
- Independent Validation result and focused isolation tests.
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
