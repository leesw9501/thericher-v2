# Engine Research Agent

## Status

- Generic catalog-backed campaign contract and deterministic CPU naive baseline
  are review-hardened; no research job is running.
- GPU training remains held until Data publishes a development-training-
  eligible fixed-instrument daily entry.
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

- Prepare the refreshed daily campaign for the predeclared `SPY`, `QQQ`, and
  `IWM` set without selecting instruments from performance.
- Run all frozen naive baselines first. Use one bounded Docker PyTorch CUDA
  breadth set only after Data eligibility and the Claude contract challenge.
- Keep all results development-only; do not enter depth or promotion.

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

- Campaign runs reject raw bar lists, derive dataset identity from Data-owned
  `CatalogedBars`, verify its id/hash, and reject timeframe mismatch before
  prediction.
- Phase filtering, forward disjoint windows, label-horizon purge/embargo, and
  sealed-holdout isolation remain enforced.
- Ranking contracts reject zero slippage and catalog-ineligible or late-built
  sealed holdouts. Naive baselines use the same local-paper timing and costs.
- CPU baseline replay evidence now requires an external work directory and
  preserves event JSONL, SQLite, and emergency state with paths and hashes in
  the existing validation artifact. Artifacts are exclusive-create only.
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

- Focused campaign plus legacy validation tests pass (`10 passed`): real gzip
  hash binding, byte tamper, raw-list/id/hash/timeframe rejection, durable
  replay, costs, deterministic payload, offline behavior, and smoke compatibility.
- Claude verdict: `supported-with-limits`; hash pinning, pre-prediction phase
  filtering, horizon gaps, and baseline timing parity were incorporated.
- Production development smoke
  `catalog-r2-aapl-bound-r1-development-fold-1-always_long` preserved 56
  `local_paper` fills and replay hashes outside Git. It finished flat with
  after-cost PnL `-7.8754`; this validates plumbing, not signal quality.
- Existing 1m feature, trace, replay, and attribution work showed that the
  research plumbing operates, but outcomes were mixed and often duplicated
  across thresholds or reused slices.
- The evidence is development-only because session breadth, forward isolation,
  target/fill alignment, and realistic slippage are unresolved.
- No current model has campaign-grade ranking or promotion evidence.

## Next Handoff

- Data Agent: provide the fixed-instrument daily manifest and eligibility facts.
- Engine Research: run daily CPU baselines and at most one bounded GPU breadth
  set if development training is supported.
- Return one concise development result with forward folds, costs, replay
  hashes, and PnL attribution; do not claim an untouched holdout.
