# Next Codex Goal

## Objective

Run the first bounded, candidate-only QQQ/SPY D1 sequence model screen for the
reattested `expanding-1` fold. It must consume only the local in-memory 20-by-3
completed-return windows and v2 in-memory QQQ target/cost labels, train on the
fixed sparse development indices, and report validation classification evidence
without a replay, model selection, or Paper decision.

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

   Active target/cost receipt:
   D:\thericher-v2\model-artifacts\research-contracts\snapshot=2026-07-24-qqq-spy-tiingo-events-v1-d1-target-cost-expanding-1-validation-first-v2.json
   ```

   Expected target/cost receipt hash/identity:
   `sha256:90beea4c501a946dd5502a2b0eb4a06b10a0ef36ed5f70f29c595a17dd6d7486` /
   `sha256:2c0ecbb889b8f1660929e87458e4a90d01f2390e41b25ed47e7201ab8a94b842`.

## Required Work

1. Build one narrow, fold-local sample iterator that reconstructs only sparse
   `expanding-1` windows from the verified materializer and v2 target adapter.
   It must expose exactly 20 rows of QQQ return, SPY return, and QQQ-minus-SPY
   return per sample, with labels kept in memory. Do not persist rows or labels.
2. Freeze one candidate screen contract: 2,345 development and 146 validation
   eligible decisions, no use of the 151-session untouched tail, fixed seed,
   fixed normalization fit only on development data, binary classification
   metrics, and no return/PnL/replay metric.
3. Run a deterministic CPU smoke first. If Docker CUDA is available, run at
   most one bounded CUDA candidate screen after the smoke using the same frozen
   sample contract. Compare only a fixed linear baseline and one compact
   sequence candidate; do not tune, choose a winner, ensemble, promote a
   checkpoint, or claim profitability.
4. Keep all summaries/checkpoints under
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; do not store
   raw data or labels in artifacts or Git. Prefer safe serialization and do not
   load untrusted checkpoint formats in any execution process.
5. Add focused tests for sample causality, sparse split preservation,
   development-only normalization, untouched-tail exclusion, no raw-label
   persistence, candidate-only scope, and no credential/KIS/Tiingo/broker/
   network behavior on pure paths.
6. Ask Claude CLI for a concise falsification-first screen review before
   relying on any result. If OAuth remains unavailable, record
   `review_unavailable`; candidate-only CPU/CUDA evidence may continue, but no
   selection, replay, Paper, or promotion follows.
7. Have temporary Validation independently inspect the frozen screen contract,
   one external source-safe result, and the CPU/CUDA scope. Refresh active
   stateboards with resulting cross-lane facts only.

## Hard Boundaries

- Do not read `.env`, call KIS or Tiingo, invoke a broker endpoint, inspect an
  account, submit/modify/cancel an order, or read any `KIS_LIVE_*` value.
- Do not run a replay, select an ensemble, claim profitability, derive a Paper
  decision, or enable live behavior.
- Keep market bytes under `D:\market_data` and generated artifacts under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`; never commit
  either.
- `review_unavailable` is a promotion/execution boundary only. It cannot become
  an approval hold for candidate-only research or another ready private lane.

## Completion Evidence

- One source-safe, hash-bound candidate screen contract/result that names the
  active materializer and v2 target/cost identities but contains no raw rows,
  labels, predictions, or PnL.
- CPU smoke evidence and, when CUDA is available, one bounded CUDA result under
  the external artifact root.
- Focused tests for causal sample construction, split isolation, scope, and
  route isolation.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A Claude tooling fault or one candidate failure does
not stop independent ready work.
