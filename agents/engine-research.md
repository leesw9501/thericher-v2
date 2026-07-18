# Engine Research Agent

## Status

- The bounded RAW D1 development campaign is complete; no campaign or GPU job
  is running.
- Data marks the fixed `SPY`, `QQQ`, `IWM` r2 dataset development-training
  eligible and ranking/holdout ineligible.
- The CUDA evidence is structurally valid but the factor sensitivity verdict is
  `unsupported`; no candidate is selected or promoted.
- Data's Tiingo EOD snapshot is loader-attested for r2, and frozen replay
  `raw-d1-explicit-events-20260718-r3` completed its 36 cells on CPU with zero
  training. It preserves the parent `unsupported` verdict.
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

- The next Data goal has one development-only falsifiable question: whether the
  `d1-pressure-lb20` factor-sensitivity instability persists on an independent
  Tiingo raw D1 snapshot for the same fixed ETFs. Keep GPU idle; the first step
  is data construction and a no-retraining comparison plan.

## Explicit-Event Replay

- `scripts/run_frozen_explicit_event_replay.py` is the sole CLI bridge. Its
  default is preparation only; the explicit `--execute` path runs only the
  frozen 36 local-paper cells, reads no environment or network data, probes no
  CUDA device, and trains zero models.
- Authoritative completed evidence is
  `D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-explicit-events-20260718-r3\summary.json`
  with SHA-256
  `3cac5f0b14e602c6a0043bb141fa7d6add1ca02b8ab4e214145443a1d8711609`.
  It has 18 baseline and 18 candidate cells, 145 independently rechecked
  artifact hashes including the source summary, `source: local_paper` fills,
  flat final positions, `torch_cpu` inference, and zero training runs.
- The earlier r1 interruption and r2 summary-write failure are incomplete and
  non-authoritative external recovery evidence. Preserve them; do not reuse or
  overwrite either run id.

## Breadth Queue

- After the Tiingo raw D1 snapshot is loader-attested, prepare one frozen,
  no-retraining data-source robustness replay. It remains development-only and
  must preserve the sticky `unsupported` verdict.

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
- Explicit event masking excludes every signal start whose inclusive observed
  index window `[i-20, i+2]` touches a qualified event session. Preparation
  freezes 36 future replay cells, zero training, and the parent `unsupported`
  verdict; it cannot rank, promote, select, open a holdout, or claim profit.
- The fixed CUDA set is hidden 8, ReLU, standardization, learning rate 0.005,
  weight decay 0.0001, threshold 0.5, 12 epochs, seed 71. Torch remains lazy and
  own checkpoints load with `weights_only=True`.

## Recovery

- Before a production run, reject any dataset id/hash/path mismatch, unsafe
  campaign path component, derived path outside the artifact root, split
  mismatch, existing artifact target, or artifact path inside Git.
- The preparation runner fails before any plan is returned when the event
  loader is not replay eligible; source summary/checkpoint hash or structure,
  r2 lineage, or fold-local pre-fit standardization mismatch also fails closed.
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
- A read-only recheck matched all six current checkpoint byte hashes to that
  source summary; every summary standardization record remains `development`
  phase and matches its own fold. No model was loaded or trained.
- All fills remained `source: local_paper`, every replay ended flat, and all six
  checkpoints reloaded with `weights_only=True`.
- `d1-pressure-lb20` changed sign for IWM/fold-1 and QQQ/fold-1 under factor
  exclusion, and aggregate relative order changed. The final verdict is
  `unsupported`, so no profitability, ranking, or promotion claim is allowed.
- The interrupted `cpu-r1` attempt has no summary and is non-authoritative.
- The Tiingo snapshot has 46 qualified cash-distribution events and zero splits
  across the fixed ETFs. R3 completed from it with no retraining and did not
  alter the parent `unsupported` verdict.
- The completed descriptive attribution is
  `D:\thericher-v2\model-artifacts\attribution\raw-d1-explicit-events-20260718-r3-attribution-r1\summary.json`
  with SHA-256
  `3de06a073b50f4b3b548a14a2d6040ebcb713b78b9a69a08b4add5f129b86e70`.
  It verifies r3 plus 144 cell evidence files, records 36 fixed cells and 300
  `local_paper` fills, omits cross-cell PnL aggregation because cells overlap,
  and labels its scope arithmetic-consistency-only rather than independent
  execution-quality or profitability evidence.

## Next Handoff

- Data now owns the Tiingo raw D1 comparison snapshot. Once it is immutable and
  loader-attested, Research may prepare one frozen no-retraining replay to test
  data-source sensitivity only. Do not rank, promote, name a winner, claim
  profitability, or start GPU training.
