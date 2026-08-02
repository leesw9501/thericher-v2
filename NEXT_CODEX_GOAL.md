# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `causal-mtf-momentum-expert-adapter-v1`.

Give the existing completed-bar multi-timeframe momentum experts one direct,
pure input path from `CausalMultiTimeframeSequenceWindow`. This makes the
model-side expert inputs use the same revalidated 1m/5m/10m/1h/3h causal bar
windows that the target-position policy can bind to its predictions.

The adapter is an existing-model extension, not a new feature-envelope,
source-contract wrapper, model family, or strategy claim. The prior
prediction-window binding remains the output-side check; this objective closes
the corresponding existing momentum input-side path.

## Hard Boundaries

- Do not call KIS, Tiingo, Norgate, or another provider. Do not read `.env`,
  credentials, account data, or `KIS_LIVE_*`.
- Do not submit, simulate, or replay a Paper/broker/local-paper order. Do not
  modify the QQQ/SPY prospective observer, its Data scheduler, or its store.
- Do not open targets or returns, calculate PnL, train/tune/load weights, use
  CUDA/GPU, allocate Research Steward GPU custody, or write a model artifact.
- Do not introduce a generic feature tensor/envelope framework, a
  `ModelPrediction` metadata convention, a source-contract wrapper, a new
  model family, or a second causal-window validator. Reuse
  `CausalMultiTimeframeSequenceWindow` and its existing builder.
- Keep the work pure and in-memory: no filesystem, network, environment,
  execution, artifact, or schedule surface.

## Required Work

1. Record the preceding short Claude drift-check timeout as
   `review_unavailable`; it is not agreement or a hold. Before adding any new
   abstraction, verify from current direct consumers that an existing
   `MultiTimeframeMomentumEvidence` extension is narrower than a new wrapper.
2. Add the smallest public pure adapter to the existing multi-timeframe
   momentum module. It accepts one causal multi-timeframe window and the
   existing momentum config, revalidates the selected bars with the existing
   builder, and emits the same typed evidence/prediction contracts using each
   expert's required completed trailing bars.
3. Require every configured expert timeframe to exist in the canonical causal
   window and require at least `lookback + 1` bars for that expert. Preserve
   the existing per-expert feature-window end, symbol, market, and decision
   cutoff semantics. Return the existing categorical unready evidence for a
   model-input insufficiency where that type can represent it; do not invent
   a tolerance, fallback resampling, or implicit lookback expansion.
4. Add a real CPU compatibility test: derive one causal window from the same
   completed session bars and prove the current raw-bar momentum builder and
   the new direct-window adapter produce identical ready evidence. Pass the
   adapter output through the existing policy with the same window.
5. Add focused fail-closed tests for the strongest forgery: a matching outer
   QQQ header containing SPY H1 or 3h bars. Also cover a future/incomplete or
   non-contiguous selected bar, an insufficient expert lookback, and
   import/I-O isolation without duplicating sequence-window test coverage.
6. Refresh Engine Research, Execution, orchestration, handoff, and decision
   stateboards with the exact result. State that the 0-record QQQ/SPY observer
   is not a foreground wait and that no GPU/model-training/PnL/Paper/live
   result was created.

## Verification

Run focused tests and an injected CPU-only adapter smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper remains blocked by known interrupted roots, preserve
that fact and run its fresh-root mode plus the remaining verification commands.

## Completion

Report the selected integration point, Claude result, raw-vs-window
compatibility result, strongest forgery result, tests, and why no
GPU/model-training/PnL/Paper/live claim was created. Commit and push completion
evidence before replacing this file with exactly one next objective and
continuing.
