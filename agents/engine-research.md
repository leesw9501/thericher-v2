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
- The permitted Tiingo raw-D1 source-sensitivity replay is also complete with
  zero training, 36 local-paper cells, and the same sticky `unsupported`
  verdict. It is non-independent because r2 fixed the session calendar.
- Data has pinned a separate broad-Yahoo development-only ETF wrapper. It is
  not campaign-ready and now feeds one small, re-attested, in-memory feature
  and future-only outcome materializer. It cannot justify model training,
  ranking, promotion, or any profitability claim.
- Data also froze a separate Tiingo full-history raw-EOD evidence snapshot. Its
  bounded exact raw-source alignment check is `unsupported`; it does not open
  feature, model, campaign, or paper work for that source.
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

- GPU: NVIDIA GeForce RTX 4090, 24564 MiB; no active engine-owned job.
- Host artifact root: `D:\thericher-v2\model-artifacts`.
- Docker artifact root: `/app/model_artifacts`.

## Current Objective

- The fixed-ETF source-sensitivity question and the full-history exact
  raw-source alignment check are unsupported. The broad ETF wrapper supplies
  descriptive features plus explicit future-only outcomes, but neither opens
  CPU/GPU model work. The deterministic intraday multi-timeframe local-paper
  baseline is complete on short CVS/FCX/KO evidence; it is pipeline evidence
  only and cannot rank, promote, open a holdout, or claim profitability.
  Tiingo IEX r1 is a separate 5-minute descriptive snapshot and does not alter
  those boundaries. Norgate now has a host-only raw-D1 adapter, but it remains
  outside `CatalogedBars`, campaign, model, and GPU inputs. Its fixed-ETF
  source-alignment snapshot is `literal_raw_ohlcv_difference`, with only 483
  Norgate sessions per symbol against 896 pinned Tiingo sessions; it creates no
  GPU or breadth-queue eligibility. Tiingo raw-daily R1 has 29 available
  responses with only 18 common sessions, while disjoint R2 has 29 available
  responses with 501 common sessions. The hash-re-attested aggregate audit
  reports 56 existing groups covering R2's returned window, but the combined
  58-candidate set still has only 18 common sessions because R1 binds it. Both
  remain source evidence for Data only, not a point-in-time common panel or
  GPU/model input.
  The retained Norgate trial raw-D1 r2 snapshot is likewise development-source
  evidence only: requested `NONE` adjustment semantics and zero observed event
  markers remain unproven, so it does not reopen breadth, depth, ensemble, or
  CUDA work.

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

- No breadth batch is currently eligible. The fixed RAW D1 verdict is
  `unsupported`; broad Yahoo and Tiingo IEX remain descriptive-only; Norgate's
  host-only raw-D1 provider has no cataloged or campaign input. Tiingo raw-daily
  R2's 501-session descriptive panel and its 56-group descriptive coverage
  filter do not repair its date-less universe, while R1/R2 combined still has
  only 18 common sessions, so neither supplies breadth eligibility.
- Keep the breadth recipe prepared, not running: finite CPU baselines plus
  compact PyTorch MLP and TCN candidates at fixed seeds. A valid campaign
  contract, not idle GPU capacity, is the launch condition.
- When Data supplies one hash-bound development-training-eligible dataset and a
  frozen campaign contract, enumerate one finite breadth batch before launch:
  CPU naive/linear/tree baselines plus compact PyTorch MLP and TCN, each at two
  fixed seeds. Run the four GPU jobs serially on the one GPU.
- CPU may prepare only the already-enumerated next fold, lineage check,
  baseline, or replay while that finite GPU batch runs. Do not auto-refill a
  queue, create a scheduler, or launch a job merely to occupy the GPU.

## Depth Queue

- No depth work is currently eligible. A finite breadth result may promote at
  most two candidates to three fixed seeds only after temporal sensitivity and
  a Claude falsification verdict. A sealed holdout remains closed.

## Ensemble Queue

- No ensemble work is currently eligible. It requires two or more candidates
  with independent out-of-fold predictions; begin only with equal-weight
  probability averaging and disagreement abstention. Do not tune stacking on
  shared validation or holdout predictions.

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
- The broad Yahoo wrapper pins one 1,300-symbol snapshot but returns only the
  predeclared `SPY`/`QQQ`/`IWM` common window: 6,555 sessions from
  `2000-05-26` to `2026-06-22`. It is explicitly inception-truncated and
  survivor-selected; PIT membership, delistings, and raw corporate-action
  semantics are unproven. It returns a wrapper rather than a campaign-ready
  `CatalogedBars` tuple, so Research must not bypass that boundary.
- Its first feature materializer emits only in-memory rows after completed
  session close: five-session and one-session raw-close returns, same-session
  high/low range, and one-session volume change. Data re-attests the fixed gzip
  and manifest for each call, its raw parser is restricted to Data-module
  callers, and no feature can read a later bar.
- Its paired outcome materializer re-attests the same source, recomputes the
  canonical feature result before use, and derives only
  `raw_close(next observed session) / raw_close(t) - 1`. It records the future
  outcome session and calendar-day gap, skips the terminal feature rows, and
  remains in-memory, non-campaign, and non-decisional.
- The new Tiingo snapshot records 21,862 raw-field rows through `2026-07-10`
  and enforces a confirmed final session plus shared listed-session coverage.
  It is a retrieval-time data record, not point-in-time universe evidence or an
  independent validation set.
- The intraday baseline accepts only Data-owned 1-minute `CatalogedBars`. It
  resamples one completed bar per target timeframe, then uses exactly the next
  two contiguous 1-minute bars for local-paper entry and flattening. Each
  timeframe has an isolated event store, exactly two `local_paper` fills, and a
  flat replayed position. It emits no PnL, candidate, campaign, or model result.
- Tiingo IEX r1 is not a `CatalogedBars` stream. It has 10,000 5-minute bars
  and 129 shared sessions per SPY/QQQ/IWM from 2026-01-13 through 2026-07-10,
  with a hash-attested manifest. It is IEX-only and does not establish
  consolidated volume, timestamp-boundary semantics, adjustments, corporate
  actions, PIT membership, independence, model suitability, or a 1-minute
  execution path.
- The nonpersistent SPY 2024 probe returned a different 10,000-bar window,
  from `2024-01-02T19:40:00Z` through `2024-06-28T19:55:00Z`. It establishes
  only date-window reachability. It has no stored bytes, source hash, dataset
  identity, training use, campaign use, or research result.

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
- The source-sensitivity replay is
  `D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-tiingo-source-sensitivity-20260718-r1\summary.json`
  with SHA-256
  `2e91c133fd12e0e28a7011eb0c1d3f661fe0fffab094ab00b679d3a566a14ff3`.
  It reused all six source checkpoints on CPU, trained zero models, completed
  18 baseline plus 18 candidate cells with `local_paper` fills and flat final
  positions, and recomputed neither standardization nor price adjustments.
  Across the 36 corresponding r2 explicit-event cells, decision count, trade
  count, and after-cost-PnL sign did not change. This is descriptive only: the
  shared r2 session calendar makes it non-independent and it cannot select,
  promote, or claim profitability.
- The completed descriptive attribution is
  `D:\thericher-v2\model-artifacts\attribution\raw-d1-explicit-events-20260718-r3-attribution-r1\summary.json`
  with SHA-256
  `3de06a073b50f4b3b548a14a2d6040ebcb713b78b9a69a08b4add5f129b86e70`.
  It verifies r3 plus 144 cell evidence files, records 36 fixed cells and 300
  `local_paper` fills, omits cross-cell PnL aggregation because cells overlap,
  and labels its scope arithmetic-consistency-only rather than independent
  execution-quality or profitability evidence.

## Next Handoff

- The frozen fixed-ETF work is exhausted for model promotion: r2 factor
  sensitivity remains unsupported, and the full-history Tiingo exact raw-D1
  comparison is also unsupported. The broad-Yahoo feature/outcome substrate is
  complete and remains descriptive. The intraday multi-timeframe local-paper
  baseline is also complete but remains a short-data pipeline smoke. Tiingo
  IEX r1 adds only a hash-attested 5-minute descriptive window. The bounded
2024 probe confirms date-window access but not completeness. The pre-r1 archive
plan is now closed after two strict source-validation failures with no snapshot.
Data next prepares a minimum PIT-capable source decision before any historical
intraday research decision. Do not rank, promote, name a winner, claim
profitability, or start GPU training. The newly retained Norgate raw-D1 r2
source does not change that conclusion; its next field-level probe may improve
event exclusions only.
