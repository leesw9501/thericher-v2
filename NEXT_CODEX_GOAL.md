# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`,
`DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`, `agents/data.md`,
`agents/engine-research.md`, `agents/research-steward.md`,
`agents/execution.md`, and `agents/orchestration.md` first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build and run `norgate-d1-trio-intraday-structure-gbt-preflight-v1`.

This is the first bounded source-local predictive-engine experiment after the
active Norgate build matched the immutable fixed `SPY/QQQ/IWM` D1 source. It
must determine only whether a single frozen causal gradient-boosted-tree model
has discrimination above a date-block permutation null. It is not a PnL,
profitability, ranking, portfolio, Paper, or GPU objective.

## Frozen Scope

- Use only the existing immutable fixed-trio D1 materialization and reattach
  the external active-build revision receipt provider-free before model work.
  Do not update/download Norgate data, call KIS, read `.env` or credentials,
  access accounts, submit/cancel an order, enable live behavior, expose a
  public endpoint, or use a paid service.
- Keep all generated contracts, summaries, and optional serialized model
  artifacts under `D:\thericher-v2\model-artifacts`, never Git. Persist no raw
  bars, dates, row-level labels, predictions, credentials, or source paths.
- Use one fixed `sklearn.ensemble.HistGradientBoostingClassifier` CPU
  configuration only. Do not sweep feature windows, thresholds, model
  hyperparameters, seeds, or classifiers. Do not allocate GPU, load public
  weights, open a sealed holdout, build an ensemble, or create a Paper input.
- The completed cross-ETF 20-day momentum diagnostic is closed. Do not retune
  it or reuse its outcome as a feature-selection pass.

## Required Contract

1. Decisions at completed D1 session `t` may use only same-session price-ratio
   features from completed bars through `t`: body, range, and close-location
   structure aggregated over frozen `1/5/10/20` session windows. Do not use
   cross-session price ratios, price levels, calendar dates, or volume in this
   first preflight.
2. The label is the sign of the next session's within-session `close/open`
   ratio. A uniform multiplier applied to every OHLC value in any one session
   must leave both the feature vector and label unchanged. Prove this in tests.
3. Freeze the exact 511-session chronological geometry: development ends before
   the existing 21-session purge, validation uses only target-evaluable dates,
   and all preprocessing/model fitting uses development rows only. Validate the
   exact decision-to-label indices and prove future labels cannot alter features
   or the fitted development state.
4. Evaluate only aggregate, date-clustered balanced accuracy. Record
   `always_flat` as a no-decision reference and `always_long` as a directional
   comparator, but do not compute after-cost PnL or claim an execution edge.
5. Require at least 120 validation date groups. Compare the actual model only
   against 64 fixed nonzero circular date-block label shifts. Predeclare a
   minimum 0.08 date-balanced-accuracy advantage above 0.50 and the 95th
   percentile null threshold. If either condition fails, close
   `noise_not_separable`; do not tune or retry. If both pass, record
   `review_required` and ask Claude for a falsification review before any
   interpretation. A one-session label-shift control must also be recorded and
   an anomalously strong shifted result must fail the claimed alignment.

## Required Work

1. Data: build the smallest provider-free loader boundary that verifies the
   fixed source hashes and the matching active-build receipt before the Engine
   module receives `Bar` data. Preserve all existing source limitations.
2. Engine: implement the frozen feature/label geometry, model fit, aggregate
   metrics, date-block null, availability-shift control, result validation, and
   source-safe external receipt. Keep the core offline and deterministic.
3. Validation: add focused tests for causal index geometry, multiplier
   invariance, development-only fitting, null determinism, no raw artifact
   leakage, external-root containment, no network/credential/broker access,
   and a synthetic `noise_not_separable` outcome.
4. Run a real CPU-only preflight against the fixed local source. Report only
   safe hashes, counts, categorical outcome, and metric categories. Do not
   output raw data or individual predictions.
5. Update Data, Engine Research, Research Steward, orchestration, handoff, and
   decision stateboards with the frozen contract, result, and next readiness.

## Claude Review

Claude already returned `uncertain` for a raw cross-session target because
adjustment semantics and 140 date groups cannot resolve a small effect. This
goal adopts its required multiplier-invariant feature/label, fixed-model,
date-block-null, and effect-floor conditions. Ask Claude again only if the
actual result clears the frozen strong-result condition or implementation
widens scope.

## Verification

Run focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
```

If the clean-root helper precondition is still blocked by its known interrupted
run roots, do not delete, rename, or bypass them. Record that scoped recovery
fact and run the helper's independent fresh-root mode plus the remaining
verification commands.

## Completion

Report the categorical preflight outcome, focused and full verification,
artifact location/hash, Claude result if invoked, commit hash, intentionally
omitted GPU/Paper/PnL work, and the next recommended objective. Commit and push
completion evidence before replacing this file with exactly one next objective
and continuing.
