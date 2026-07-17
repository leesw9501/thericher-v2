# Engine Research Agent

## Status

- The bounded RAW D1 development campaign is complete; no campaign or GPU job
  is running.
- Data marks the fixed `SPY`, `QQQ`, `IWM` r2 dataset development-training
  eligible and ranking/holdout ineligible.
- The CUDA evidence is structurally valid but the factor sensitivity verdict is
  `unsupported`; no candidate is selected or promoted.
- Generated campaign evidence remains external under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.

## Engine Loop

- Feature/model research.
- Backtest and forward validation.
- Model-side PnL attribution.

## Owns

- Frozen research hypotheses, features, targets, costs, candidates, and seeds.
- CPU baselines, bounded CUDA training, local-paper replay, and sensitivity.
- One external campaign recovery summary; not a report or job family.

## Must Not

- Modify broker submission/risk code, call KIS, read credentials, or acquire data.
- Use adjusted diagnostics in features, targets, fills, thresholds, or metrics.
- Treat this development dataset as ranking, promotion, sealed holdout, model
  selection, a winner, or evidence of profitability.
- Add a scheduler, queue framework, artifact-specific job kind, or dependency.

## Resources

- GPU: NVIDIA GeForce RTX 4090, 24564 MiB; idle after the bounded CUDA run.
- Host artifact root: `D:\thericher-v2\model-artifacts`.
- Docker artifact root: `/app/model_artifacts`.

## Current Objective

- Wait for Data-owned explicit corporate-action and distribution evidence for
  `SPY`, `QQQ`, and `IWM`.
- Reuse the existing six checkpoints to compare the heuristic factor mask with
  an explicit event mask. Do not retrain, change candidates, or select a model.

## Breadth Queue

1. Receive hash-bound event dates, event types, and provenance from Data.
2. Map events to affected lookback, signal, entry, and exit sessions without
   changing raw fills or the frozen split.
3. Replay existing baselines and checkpoints under the explicit event mask.
4. Compare only sensitivity stability; do not use the result for ranking.

## Depth Queue

- None. This campaign cannot promote work into depth or open a sealed holdout.

## Running

- None.

## Durable Knowledge

- RAW D1 bars are loader/manifest/hash attested; factor dates come from the
  same hash-bound Data helper. Adjusted diagnostics are unavailable as `Bar`
  fields.
- The executable target is completed session `t`, raw `t+1` open entry, raw
  `t+2` open exit, 10 bps fee and 5 bps slippage per fill.
- Daily plan checks prove exact common-session `+1/+2` timing even across
  weekend/holiday gaps; generic intraday continuity remains strict.
- Every lane uses a shared max-lookback-20, two-observed-session cadence.
  Durable campaign replay must finish flat and have nondecreasing event times.
- Two observed purge sessions separate each development/validation pair; two
  observed embargo sessions separate the folds. Development labels finish
  before validation entry evidence starts.
- All six optional models train once on factor-safe development samples.
  Fold-local standardization is fit only there; primary versus sensitivity
  changes validation decision inclusion and never triggers a second fit.
- Candidate/baseline after-cost sign instability or any aggregate relative-order
  change across present baselines and candidates makes the sensitivity verdict
  `unsupported`; it does not select a model.
- The fixed CUDA set is hidden 8, ReLU, standardization, learning rate 0.005,
  weight decay 0.0001, threshold 0.5, 12 epochs, seed 71. Torch remains lazy and
  own checkpoints load with `weights_only=True`.

## Recovery

- Before a production run, reject any dataset id/hash/path mismatch, unsafe
  campaign path component, derived path outside the artifact root, split
  mismatch, existing artifact target, or artifact path inside Git.
- A completed run is recoverable from
  `daily-campaign/<campaign_id>/summary.json`; without it, treat scattered
  replay/checkpoint files as an incomplete run and restart with a new run id.
- Stop if fold-local preprocessing, observed-session adjacency, flat replay, or
  event-time monotonicity cannot be proven.

## Recent Evidence

- CPU preflight `raw-d1-development-20260718-cpu-r2` completed 36 replay cells
  and 108 replay-state hash checks; summary SHA-256 is
  `9ee93a8bf4ecfff92bd71d7c49c613dd8fe567e5ab7f70e23feffed4c4462c95`.
- Docker/PyTorch CUDA run `raw-d1-development-20260718-cuda-r1` completed six
  checkpoints, 72 replay cells, and 216 replay-state hash checks; summary
  SHA-256 is
  `5db680e1ba72a17b089a5c44372443289b2411c690f6372b6c6f2e3e35ac1d89`.
- All fills remained `source: local_paper`, every replay ended flat, and all six
  checkpoints reloaded with `weights_only=True`.
- `d1-pressure-lb20` changed sign for IWM/fold-1 and QQQ/fold-1 under factor
  exclusion, and aggregate relative order changed. The final verdict is
  `unsupported`, so no profitability, ranking, or promotion claim is allowed.
- The interrupted `cpu-r1` attempt has no summary and is non-authoritative.

## Next Handoff

- Data leads the next bounded objective. Once its explicit event manifest is
  independently validated, Research replays the existing checkpoints without
  retraining. Preserve the current summaries as development-only evidence and
  do not rank, promote, name a winner, or claim profitability.
