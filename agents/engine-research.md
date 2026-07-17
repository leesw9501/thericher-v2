# Engine Research Agent

## Status

- Campaign preparation only; no research job is running.
- GPU training is held until the Data Agent publishes a campaign-ready dataset.
- Current projection only; history remains in Git `8f416f8` and external artifacts.

## Engine Loop

- Feature/model research.
- Backtest and walk-forward validation.
- PnL attribution.

## Owns

- Research hypotheses, features, strategy logic, and model experiments.
- CPU baselines, public-model comparisons, and bounded campaign preparation.
- Campaign evaluation, walk-forward analysis, attribution, and registry inputs.

## Must Not

- Modify broker submit code or introduce execution strategy outside risk checks.
- Call KIS, read credentials, acquire data, or write generated artifacts to Git.
- Start GPU training before a Data-owned campaign-ready dataset exists.
- Present existing 1m experiments as candidate ranking or promotion evidence.
- Add artifact-specific job kinds; use the one campaign contract and existing
  research primitives.
- Convert research weakness into broker, execution, or promotion policy.

## Resources

- GPU: NVIDIA GeForce RTX 4090, 24564 MiB; available but held by policy.
- External artifact root: `D:\thericher-v2\model-artifacts`.
- Docker artifact path: `/app/model_artifacts`.

## Current Objective

- Prepare one reproducible research campaign for the next Data-owned dataset.
- The campaign contract must bind dataset identity, universe, split windows,
  labels, decision timestamps, fill timestamps, costs, models, and metrics.
- Resolve target/fill semantics before training: current next-close targets do
  not match a strategy filled at the next open.
- CPU baseline, public-model, test, and campaign-config preparation may proceed
  as bounded development work; none establishes candidate rank.

## Breadth Queue

1. Validate the Data-owned dataset manifest, coverage, quality notes, and hash.
2. Freeze broad symbol/session coverage under the single campaign contract.
3. Define non-overlapping forward walk-forward folds with embargo where needed.
4. Reserve one untouched final holdout that is not used for model or threshold
   choice.
5. Run cheap CPU naive, classical, and public-model reference baselines before
   allocating GPU depth.
6. Report per-symbol, per-session, and aggregate metrics with fee and slippage
   sensitivity.

## Depth Queue

1. Start bounded GPU training only after Breadth dataset checks pass.
2. Compare a small fixed model set against the CPU/reference baselines.
3. Tune only inside training/validation folds; never tune on the final holdout.
4. Validate with forward, non-overlapping walk-forward results and nonzero
   slippage scenarios.
5. Attribute PnL by symbol, session, regime, entry, exit, fees, and slippage.

## Running

- None.
- GPU remains idle until the Data-owned campaign-ready dataset is handed off.

## Durable Knowledge

- Existing 1m evidence covers too few sessions for reliable generalization.
- The current next-close prediction target is misaligned with next-open fills.
- Previously inspected holdouts may be non-forward or burned by repeated use.
- Overlapping walk-forward windows can inflate apparent sample independence.
- Zero slippage is the current default and is not adequate ranking evidence.
- Threshold variants and repeated market moments do not add independent breadth.
- Prior 1m results validate plumbing and diagnostics only, not candidate order.

## Recovery

- If no campaign-ready Data artifact exists, remain held and continue only
  bounded CPU baseline, public-model, or campaign preparation.
- On handoff, verify dataset identity, split boundaries, target/fill alignment,
  holdout isolation, and cost assumptions before any GPU command.
- Resume from the earliest incomplete campaign phase; do not infer state from
  scattered historical artifacts.
- Use Git commit `8f416f8` and external artifacts only when deeper history is
  needed.

## Recent Evidence

- Existing 1m feature, trace, replay, and attribution work showed that the
  research plumbing operates, but outcomes were mixed and often duplicated
  across thresholds or reused slices.
- The evidence is development-only because session breadth, forward isolation,
  target/fill alignment, and realistic slippage are unresolved.
- No current model has campaign-grade ranking or promotion evidence.

## Next Handoff

- Data Agent: provide one immutable campaign-ready dataset with manifest,
  symbols, sessions, quality notes, and explicit split recommendations.
- Engine Research: accept it through one campaign contract, run breadth CPU and
  public-model baselines, then authorize bounded GPU depth only if warranted.
- Return one concise campaign result covering forward validation, untouched
  holdout performance, slippage sensitivity, and PnL attribution.
