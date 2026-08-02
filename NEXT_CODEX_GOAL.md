# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `causal-mtf-prediction-window-binding-v1`.

Add the smallest pure Engine Research boundary that proves each existing
multi-timeframe `ModelPrediction.feature_window_end` is the actual end of its
declared completed causal bar window. This advances the per-symbol
multi-timeframe decision layer while the Data-owned QQQ/SPY forward observer
accumulates independently.

Do not create a new evidence bundle, feature-envelope framework, model family,
or policy graph. Reuse the existing causal sequence-window and target-position
policy contracts. The result is a fail-closed structural binding, not a model
quality or trading claim.

## Hard Boundaries

- Do not call KIS, Tiingo, Norgate, or another provider. Do not read `.env`,
  credentials, account data, or `KIS_LIVE_*`.
- Do not submit, simulate, or replay a Paper/broker/local-paper order. Do not
  modify the QQQ/SPY prospective observer, its Data scheduler, or its store.
- Do not open targets or returns, calculate PnL, train/tune/load weights, use
  CUDA/GPU, allocate Research Steward GPU custody, or write a model artifact.
- Do not introduce a new `ModelPrediction` metadata convention, source-manifest
  field, feature-schema field, evidence dataclass, wrapper policy, or second
  freshness/missing/duplicate/future implementation when an existing contract
  already owns that behavior.
- Keep the work pure and in-memory: no filesystem, network, environment,
  execution, artifact, or schedule surface.

## Required Work

1. Ask Claude for a concise falsification-first drift check before changing
   the causal-window/policy boundary. Record a timeout or malformed response as
   `review_unavailable`, never as agreement or a hold.
2. Inventory every current direct consumer of
   `CausalMultiTimeframeSequenceWindow` and `propose_target_exposure`. Choose
   the narrowest integration point that binds actual causal windows without
   weakening existing callers or duplicating `_index_evidence` checks.
3. Add one pure structural predicate or equally small existing-contract
   extension. For every supplied prediction, it must require matching
   symbol/market/timeframe and exact equality between
   `feature_window_end` and the matching causal window's completed final-bar
   end. Existing policy-owned missing, duplicate, generated-at, future, and
   freshness handling stays single-sourced.
4. First run a real-producer compatibility test: construct one existing
   `CausalMultiTimeframeSequenceWindow` and compare it with predictions from
   `build_multitimeframe_momentum_evidence`. If legitimate producer output
   cannot satisfy exact binding because bucket anchoring differs, close this
   package as `input_unavailable` with the factual mismatch and do not invent a
   tolerance or alternate bucket rule.
5. Add focused tests proving the compatible path is deterministic and the
   strongest forgery fails closed: an H1 or 3h prediction stamped at the cutoff
   rather than its actual completed bar end must not be accepted. Cover wrong
   symbol/market/timeframe, missing window, non-causal/future window, and
   import/I-O isolation only where those checks are not already owned by the
   existing policy or sequence-window tests.
6. Update the Engine Research, Execution, orchestration, handoff, and decision
   stateboards with the exact result and Claude verdict. State explicitly that
   the 0-record QQQ/SPY observer is not a foreground wait and no GPU/model/PnL/
   Paper/live result was created.

## Verification

Run focused tests and an injected CPU-only producer smoke, then:

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

Report the selected integration point, Claude verdict, producer compatibility
result, strongest forgery result, tests, and why no model/GPU/PnL/Paper/live
claim was created. Commit and push completion evidence before replacing this
file with exactly one next objective and continuing.
