# TheRicher v2 Handoff

Use this file as the first read for a fresh Codex task.

## Current Repository

- Repo: `leesw9501/thericher-v2`
- Local path: `C:\Users\Public\Documents\thericher-v2`
- Default branch: `main`
- Visibility: private

This repo is a clean v2 start. Do not continue v1's report/gate/operator-console
architecture here. The v1 repository may be inspected only as a reference and
parts source.

## Product Direction

TheRicher v2 is an engine-first KIS trading workstation for a single
Korea-based operator.

The main loop is:

1. collect intraday data,
2. build features,
3. run chart/ML/DL models,
4. combine signals,
5. backtest and walk-forward validate,
6. paper trade through KIS,
7. attribute results,
8. promote only proven engines to small live capital.

## Non-Negotiable Boundaries

- No KIS API calls until an explicit future goal allows it.
- No paper or live orders until an explicit future goal allows it.
- No credential reads.
- No public dashboard.
- No v1 wholesale imports.
- No report sprawl.
- No safety gate that blocks research iteration unless it is a true execution
  hard stop.

## Current Foundation

Implemented and pushed:

- engine-first charter docs,
- Python package skeleton,
- immutable core contracts using `Decimal` and UTC-aware timestamps,
- append-only JSONL event log,
- rebuildable SQLite query views,
- deterministic synthetic OHLCV,
- market data provider protocol, local CSV/sample providers, and deterministic
  timeframe resampling for `1m`, `5m`, `10m`, `1h`, and `3h`,
- simple momentum model,
- simple ensemble decision,
- next-bar backtest harness with fees and slippage,
- local-only dashboard skeleton,
- local emergency state for stop-new-orders and cancel-open-orders,
- broker-free local paper execution simulator with next-bar-open fills,
  duplicate client order id protection, emergency-stop blocking, deterministic
  cash/position replay, and local paper event logging,
- bounded model-validation harness that connects `Bar` data, a momentum model,
  ensemble decisions, and broker-free local paper execution,
- validation smoke CLI with optional explicit Yahoo intraday snapshot input and
  artifact writing outside Git,
- bounded research experiment queue that sweeps small momentum/timeframe
  variants through the validation harness and writes metrics outside Git,
- walk-forward attribution layer for the experiment queue with chronological
  windows, per-window replay metrics, PnL, and drawdown,
- GPU candidate smoke preparation artifact for the first longer research
  candidate, selected from walk-forward metrics without training or storing
  artifacts in the repo,
- research-profile GPU runtime smoke CLI that records `nvidia-smi` readiness
  and selected candidate metadata outside Git,
- research-profile GPU compute smoke CLI that runs only inside the bounded
  research path, records selected candidate metadata, and writes either
  `compute_ran_only` or non-fatal `prepared_not_trained` artifacts outside Git,
- optional GPU training smoke CLI with a tiny optimizer/gradient-step seam; it
  imports no heavy framework at module load, writes artifacts outside Git, and
  remains `prepared_not_trained` until a research-only backend is approved and
  installed,
- research-only PyTorch CUDA backend in the Docker `research` target
  (`torch==2.7.0+cu128` from the PyTorch CUDA 12.8 wheel index), with a tiny GPU
  training smoke that completed on the RTX 4090 and writes outside Git,
- lightweight Engine Research job runner CLI that executes one bounded
  `gpu_training_smoke` job at a time inside Docker `research`, writes a wrapper
  job artifact outside Git, and keeps `agents/*.md` as stateboards rather than
  autonomous workers,
- bounded GPU candidate training job kind in the research job runner; it
  consumes selected candidate metadata plus deterministic/sample or explicit
  local bars, trains a tiny PyTorch model under strict caps in Docker
  `research`, and writes metrics/model artifacts outside Git,
- bounded candidate evaluation job kind in the research job runner; it consumes
  external training metrics/model artifacts, reuses the training feature shape,
  runs PyTorch inference lazily inside Docker `research`, records baseline
  classification metrics, and writes evaluation artifacts outside Git,
- bounded candidate local-paper replay job kind in the research job runner; it
  consumes external training/evaluation artifacts, maps candidate probabilities
  into descriptive buy/sell/hold thresholds, runs only the broker-free local
  paper simulator, keeps simulated fills labeled `source: local_paper`, and
  writes replay/PnL attribution artifacts outside Git,
- bounded candidate replay comparison job kind in the research job runner; it
  consumes or runs candidate local-paper replay, runs a gap-tolerant momentum
  baseline through the same broker-free local paper simulator on the same bars,
  compares trades, PnL, drawdown, final position, fill count, and event count,
  and writes descriptive comparison artifacts outside Git,
- bounded candidate probability trace and threshold sweep job kind in the
  research job runner; it runs candidate probability inference once, persists
  an aligned per-example trace outside Git, replays a small buy/sell threshold
  grid through local paper without rerunning inference, compares each variant
  to the existing momentum baseline metrics, and keeps output descriptive,
- bounded threshold robustness replay job kind in the research job runner; it
  reuses the threshold sweep trace and local-paper replay primitives across a
  capped set of local Yahoo slices, records per-slice PnL, drawdown, fill
  counts, and final positions, and keeps output descriptive rather than
  promotional,
- bounded multi-slice candidate training and evaluation input; candidate
  training/evaluation can now consume explicit local Yahoo `(snapshot, symbol)`
  slices, preserve the existing four-feature shape, record per-slice row counts
  and provenance, and write model/evaluation artifacts outside Git,
- bounded multi-slice probability calibration probe; it derives a small
  deterministic threshold grid from observed candidate probability quantiles,
  replays that grid through the existing threshold robustness/local-paper path,
  writes descriptive artifacts outside Git, and records no best threshold,
  promotion, or pass/fail gate,
- bounded calibration holdout replay; it consumes the calibration threshold
  grid unchanged, runs bounded holdout traces on the disjoint
  `snapshot=2026-06-18` CVS, FCX, and KO slices, replays through the existing
  threshold robustness/local-paper path, verifies fill sources, and keeps the
  result descriptive,
- bounded real-data candidate breadth queue; it defines three nearby
  `m1_lb*_b10_s10` candidate variants, writes candidate metadata outside Git,
  runs each variant through the existing bounded training/evaluation primitives
  in Docker `research` under strict caps, and records descriptive
  probability/evaluation summaries without a winner, recommendation, or
  promotion gate,
- bounded breadth holdout bridge; it consumes the external breadth queue
  artifact, reuses the existing threshold calibration, robustness replay, and
  threshold holdout primitives for each queued candidate, verifies disjoint
  holdout local-paper fills remain `source: local_paper`, and records
  candidate-by-candidate probability/PnL/drawdown evidence without a winner,
  recommendation, or promotion gate,
- bounded depth target; it consumes the external breadth holdout artifact,
  selects at most one completed candidate with a deterministic
  `research_scheduling_only` heuristic, retrains/evaluates/calibrates/holdout
  replays the chosen candidate in Docker `research` with PyTorch CUDA under
  deeper but still capped limits, and records probability/PnL/drawdown/fill
  source evidence without a winner, recommendation, or promotion gate,
- bounded depth-vs-breadth comparison; it consumes the external depth target
  and breadth holdout artifacts, compares only the selected candidate's
  pre-depth holdout evidence against the deeper training evidence, records
  probability/fill/PnL/drawdown/cap/data-slice deltas, and stays
  `research_comparison_only` with no winner, recommendation, pass/fail result,
  or promotion gate,
- bounded comparison-informed fill-aware threshold rerun; it consumes the
  external depth comparison and depth target artifacts, derives a capped
  stricter threshold grid for the selected candidate, replays existing holdout
  slices through the proven local-paper path, and stays
  `research_threshold_rerun_only` with no winner, recommendation, pass/fail
  result, scheduler, or promotion gate,
- bounded zero-fill threshold attribution; it consumes the external threshold
  rerun, robustness, calibration, and probability trace artifacts only, records
  per-slice/per-threshold opportunity counts and local-paper fill counts, and
  explains the strict grid as above the observed buy-probability range without
  rerunning training, selecting a winner, or adding a promotion gate,
- bounded attribution-informed threshold band rerun; it consumes the external
  attribution artifact, derives a capped source-calibration band inside the
  observed probability range, replays existing holdout traces through the
  proven local-paper path, records `247` local-paper fills across 12 variants,
  and closes the threshold-only loop as descriptive evidence rather than a
  model-quality decision,
- bounded feature-branch replay attribution; it consumes the external
  `core_plus_bar_position_v1` feature-branch artifacts, derives a capped
  replay band from feature-branch probability evidence, reuses the existing
  robustness/local-paper path, records PnL/drawdown/fill attribution, and
  verifies all generated fills remain `source: local_paper`,
- broker-safe local-paper source-filtered attribution helper; it centralizes
  fill-source counting from replay event artifacts, exposes local-paper-only
  evidence, flags mixed or unknown sources, tolerates missing zero-fill event
  files, and rejects unreadable nonzero-fill evidence,
- broker adapter boundary contracts and disabled KIS execution fuses; the KIS
  boundary exposes disabled capabilities, unavailable submit/cancel/status
  results, and a factory that fails closed without network or credential I/O,
- longer bounded GPU feature/model validation using existing Docker `research`
  job kinds; it reran `core_plus_bar_position_v1` with higher caps, wrote
  artifacts outside Git, then replayed through broker-free local paper with 30
  verified `source: local_paper` fills and no promotion decision,
- warning-only market-data quality helper; it reports duplicate bars,
  non-monotonic timestamps, missing 1m intervals, and incomplete resample
  buckets without mutating bars, gap-filling, reading credentials, or blocking
  research,
- compact market-data quality summaries in candidate training/evaluation
  source-slice artifacts; local Yahoo slices now record `bars_seen`,
  `warning_count`, `blocks_research`, and warning-code counts without changing
  dataset rows, thresholds, or replay behavior,
- data-quality-visible bounded GPU validation using existing Docker `research`
  job kinds; short and deeper multi-slice candidate training/evaluation runs on
  CVS, FCX, and KO wrote `source_slices[].data_quality` outside Git, then a
  broker-free CVS replay produced 37 verified `source: local_paper` fills,
- calibration job runtime control; the research job runner now exposes
  `--threshold-pair-cap` for `candidate_threshold_calibration`, defaults
  Docker job specs to three derived pairs, and the runbook calibration smoke
  uses cap 2 after a full-grid 80-bar, 3-slice attempt exceeded 3 minutes
  without a final artifact,
- cap-limited calibration holdout replay; the cap-2 source calibration
  produced 214 local-paper fills with negative PnL range, and the disjoint
  `snapshot=2026-06-18` CVS/FCX/KO holdout produced 228 verified
  `source: local_paper` fills with negative PnL range, so threshold-only
  iteration should pause in favor of feature/model work,
- bounded bar-pressure feature/model branch; it adds
  `core_plus_bar_pressure_v1` inside the existing candidate feature builder,
  passes explicit feature-set selection through the current research job
  runner, trains/evaluates CVS/FCX/KO in Docker `research`, and replays a
  cap-2 holdout band through local paper with all fills verified as
  `source: local_paper`,
- bounded hidden-units model-axis branch; it exposes `--hidden-units` for
  candidate training and feature-branch jobs only, keeps the existing default
  at 8, trains/evaluates `core_plus_bar_pressure_v1` with 16 hidden units in
  Docker `research`, and records a cap-2 holdout replay with zero fills and
  local-paper-only evidence,
- bounded hidden-units contrast branch; it reuses the existing selector with
  `hidden_units=4`, trains/evaluates the same `core_plus_bar_pressure_v1`
  branch in Docker `research`, and records another cap-limited holdout replay
  with zero fills plus local-paper-only evidence,
- bounded feature-branch replay threshold derivation guard; saturated
  max-probability evidence now clamps the derived buy ceiling below `1.000`,
  records compact `saturation_guard` metadata only when applied, and replays
  the hidden-units contrast artifact with the requested cap restored to two
  threshold pairs while preserving local-paper-only evidence,
- bounded saturated feature-branch replay opportunity attribution; it consumes
  the guarded hidden4 replay artifact, reuses existing probability trace and
  robustness evidence, records per-slice/per-threshold opportunity counts, and
  attributes the zero fills to guarded buy thresholds above the observed
  holdout probability range without rerunning training or broker behavior,
- bounded regularization model-axis branch; it exposes one capped
  `weight_decay` selector for candidate training and feature-branch jobs only,
  keeps the default at `0.0`, records descriptive regularization metadata, ran
  `core_plus_bar_pressure_v1` with `hidden_units=4` and `weight_decay=0.01` in
  Docker `research`, then replayed cap-2 holdout thresholds with zero
  local-paper fills and zero buy opportunities,
- bounded feature-normalization branch; it exposes one artifact-driven
  `feature_standardization` selector for candidate training and
  feature-branch jobs only, persists normalization stats/signatures in
  external training/model artifacts, keeps evaluation/replay/trace paths
  artifact-driven, ran `core_plus_bar_pressure_v1` with `hidden_units=4` in
  Docker `research`, reduced source-side saturation to probability range
  `0.724726`, then replayed cap-2 holdout thresholds with zero local-paper
  fills and zero holdout buy opportunities,
- bounded source-vs-holdout probability alignment attribution; it extends the
  existing feature-branch replay opportunity attribution artifact with compact
  source and holdout probability summaries, threshold gaps, opportunity counts,
  and local-paper verification, showing the standardized branch source max
  probability `0.792910` versus holdout max `0.526492` and buy threshold min
  `0.791000`,
- bounded disjoint-evaluation feature-branch target; feature-branch jobs can
  now pass explicit evaluation slices separately from training slices while
  preserving default behavior, artifacts record both training and evaluation
  source-slice lineage, and the Docker `research` smoke trained on CVS/FCX/KO
  from `snapshot=2026-07-09-shadow-t0-8d-probe` while evaluating on disjoint
  CVS/FCX/KO from `snapshot=2026-06-18`; cap-2 replay then produced `4`
  verified `source: local_paper` fills with thresholds `0.525/0.431` and
  `0.526/0.431`,
- bounded out-of-symbol replay probe; it inventoried the existing
  `snapshot=2026-06-18` Yahoo 1m file, selected AAPL, ABNB, ABT, ACN, and ABBV
  after excluding CVS, FCX, and KO, reused the disjoint-evaluation
  feature-branch artifact through the existing Docker `research` replay path,
  produced `10` verified `source: local_paper` fills, PnL range
  `-0.95330549316406` to `0E-13`, max drawdown `0.95330549316406`, `7` buy
  opportunities, and `312` sell opportunities, with compact evidence written
  outside Git,
- bounded out-of-symbol loss attribution; it consumed the existing
  out-of-symbol replay, robustness, opportunity attribution, and compact
  summary artifacts without retraining or rerunning replay, found `5`
  fill-bearing variants and `5` zero-fill variants, observed that all
  fill-bearing variants had negative PnL while zero-fill variants were flat,
  confirmed `10` fill events with `source: local_paper`, and wrote one compact
  attribution artifact outside Git,
- bounded out-of-symbol fill-lifecycle attribution; it parsed only existing
  local-paper event files and selected `snapshot=2026-06-18` bars for the
  fill-bearing variants, found `10` local-paper fill events, `3` closed
  segments, `4` open segments, and `4` of `5` fill-bearing variants held an
  open long position to the bounded window end; ABNB and ACN open segments
  carried negative bounded-window-end gross deltas, ACN also had small positive
  closed segments, ABBV had a small negative closed segment, and compact
  evidence was written outside Git,
- bounded post-entry exit-signal attribution; it consumed existing probability
  traces and fill-lifecycle evidence only, found `7` post-entry segments,
  confirmed all `3` closed segments lined up with sell-threshold signals, and
  found all `4` open segments had no post-entry sell-threshold signal before
  the bounded window end, with all parsed fills still `source: local_paper`,
- bounded exit-horizon diagnostic overlay; it consumed existing
  fill-lifecycle and post-entry artifacts, compared open out-of-symbol
  segments against fixed 5-bar and 15-bar `diagnostic_overlay` marks without
  changing replay or local-paper fills, found only `2` of `8` diagnostic marks
  were available inside the 120-bar bounded window, and recorded that the
  available ABNB 5-bar marks still had negative gross deltas,
- bounded longer-window out-of-symbol replay; it reused the same
  disjoint-evaluation feature-branch artifact and AAPL, ABNB, ABT, ACN, and
  ABBV slices with `max-bars 240`, ran in Docker `research` with RTX 4090
  visible, produced `14` verified `source: local_paper` fills, PnL range
  `-0.8866000000000` to `0E-13`, `7` buy opportunities, `548` sell
  opportunities, and a compact post-entry summary showing all `7` segments
  closed with sell-threshold signals and no open segments remained,
- bounded longer-window trade-path attribution; it consumed the 240-bar replay,
  robustness, opportunity, post-entry, event, trace, and selected local-bar
  evidence only, attributed `7` closed trade segments, found `5` fee-aware
  negative segments and `2` non-negative segments, fee-aware delta sum
  `-2.5214`, and confirmed all `14` parsed fills were `source: local_paper`,
- bounded trade-path attribution helper; it adds a pure
  `attribute_trade_paths_from_local_paper_events` helper that consumes provided
  `Bar` data and local-paper event artifacts, reuses the shared fill-source
  evidence helper, pairs buy/sell fills with FIFO partial-fill handling,
  surfaces open segments and non-local sources, calculates holding duration,
  gross and fee-aware deltas, and simple adverse/favorable movement, with no
  new research job kind, broker path, data loader, report, gate, or dashboard,
- bounded out-of-symbol-evaluation feature-branch target; it trained
  `core_plus_bar_pressure_v1` with `hidden_units=4` and
  `feature_standardization` on CVS/FCX/KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`, evaluated directly on
  AAPL/ABNB/ABT/ACN/ABBV from `snapshot=2026-06-18`, recorded evaluation
  probability range `0.414124`, replayed out-of-symbol threshold pairs
  `0.554/0.438` and `0.555/0.438` with `max-bars 240`, produced `4` verified
  `source: local_paper` fills, found `2` buy opportunities versus `832` sell
  opportunities, and trade-path attribution found `2` closed ABNB segments,
  both fee-aware negative with total fee-aware delta `-1.8532`,
- bounded entry-quality diagnostic helper; it consumes provided probability
  trace entries, `Bar` data, threshold variants, and local-paper verification
  evidence, emits descriptive buy opportunity, fixed 5/15/30-bar
  `diagnostic_overlay` marks, adverse/favorable excursion, and sell-threshold
  timing evidence without writing artifacts or doing network, credential,
  broker, or market-data I/O,
- bounded out-of-symbol entry-quality diagnostic; it consumed the completed
  out-of-symbol feature-branch replay, opportunity attribution, trade-path
  attribution, probability traces, and selected AAPL/ABNB/ABT/ACN/ABBV bars,
  found buy opportunities only on ABNB (`2` total, both entered through
  `source: local_paper`), found all 5/15/30-bar forward close marks negative,
  and recorded that sell-threshold signals appeared `7` bars after entry but
  before the later bounded-window adverse extreme,
- bounded entry-adverse feature branch; it adds `core_plus_entry_adverse_v1` as
  a superset of `core_plus_bar_pressure_v1` with exactly two extra features,
  `upper_wick_share` and `low_vs_prior_low_return`, then ran Docker `research`
  feature-branch training/evaluation with `hidden_units=4`,
  `feature_standardization`, `max-bars 240`, CVS/FCX/KO source slices, and
  direct AAPL/ABNB/ABT/ACN/ABBV evaluation slices,
- bounded entry-adverse out-of-symbol replay and attribution; the cap-2
  240-bar replay used thresholds `0.524/0.478` and `0.525/0.478`, produced `8`
  verified `source: local_paper` fills, PnL range `-0.5477000000000` to
  `0.2254000000000`, `4` buy opportunities, `682` sell opportunities, `4`
  closed trade-path segments with fee-aware delta sum `-1.0069`, and
  entry-quality marks showing `3` of `4` 5/15/30-bar forward close marks were
  negative,
- bounded feature-branch comparison; it consumed only the existing
  `core_plus_bar_pressure_v1` and `core_plus_entry_adverse_v1` external
  artifacts, wrote one descriptive comparison artifact outside Git, verified
  both branches kept fills `source: local_paper`, and recorded that
  entry-adverse added `4` fills and `2` buy opportunities, lifted PnL min by
  `0.3789`, added one non-negative closed segment, raised max drawdown by
  `0.41109572753904`, and still had negative fee-aware delta sum,
- bounded entry-adverse segment-contrast diagnostic; it consumed existing
  replay, trade-path, entry-quality, trace, and selected local-bar evidence,
  wrote one compact external artifact, contrasted three fee-aware negative
  segments against one non-negative segment, verified all fills remained
  `source: local_paper`, found all negative segments had negative 5/15/30-bar
  forward close marks while the non-negative ACN segment had non-negative
  forward marks, and recorded no branch ranking, pass/fail field, or threshold
  search,
- bounded wider entry-adverse replay sample; it inventoried the existing
  `snapshot=2026-06-18` Yahoo 1m file, found `240` eligible additional
  symbols after exclusions, replayed `10` deterministic symbols in two Docker
  `research` batches because the existing robustness config caps slices at
  `6`, verified all `18` generated fills as `source: local_paper`, recorded `9`
  buy opportunities, `1718` sell opportunities, `9` closed trade-path segments,
  `6` non-negative and `3` negative fee-aware segments, fee-aware delta sum
  `2.7739`, and no open segments,
- bounded wider entry-adverse signal-quality diagnostic; it consumed the
  wide-sample replay, opportunity, trade-path, summary, trace, and selected
  local-bar evidence without rerunning replay, wrote one compact external
  diagnostic artifact, found the non-negative segment group had larger average
  entry probability margin, faster first sell-threshold signal timing, larger
  favorable excursion, and less adverse excursion than the negative group, and
  attributed the second batch's zero fills to buy thresholds sitting above each
  slice's observed maximum probability,
- bounded entry-adverse hidden-units contrast; it reused the existing
  `core_plus_entry_adverse_v1` feature set with `feature_standardization`, ran
  hidden-units `8` training/evaluation in Docker `research` on the capped
  CVS/FCX/KO source slices and ADBE/ADI/ADP/AEM/AGG/AMAT evaluation slices,
  replayed cap-2 local-paper thresholds, verified all `4` generated fills as
  `source: local_paper`, and recorded that the hidden8 replay produced only
  two closed AMAT segments, both fee-aware negative with fee-aware delta sum
  `-8.4776`, fewer buy opportunities than hidden4, and higher max drawdown,
- bounded entry-adverse hidden8 loss attribution; it consumed existing hidden8
  feature-branch, replay, opportunity, trade-path, contrast, trace, and AMAT
  local-bar evidence only, wrote one compact external diagnostic artifact, and
  recorded that hidden8 AMAT entries had lower average entry probability margin
  than hidden4 AMAT reference entries, much smaller favorable excursion, much
  larger adverse excursion, and fee-aware delta sum lower by `-11.1294`,
- bounded entry-adverse weight-decay contrast; it kept
  `core_plus_entry_adverse_v1`, hidden-units `4`, and
  `feature_standardization`, ran `weight_decay=0.01` in Docker `research` on
  CVS/FCX/KO source slices with ADBE/ADI/ADP/AEM/AGG/AMAT evaluation slices,
  replayed cap-2 local-paper thresholds, verified all `4` fills as
  `source: local_paper`, attributed `2` closed AMAT segments with fee-aware
  delta sum `2.6518`, and wrote one descriptive contrast summary outside Git,
- bounded entry-adverse weight-decay wider-sample completion; it replayed the
  same `weight_decay=0.01` branch on AMD/AMGN/AMT/AMZN from
  `snapshot=2026-06-18`, produced zero additional fills and zero buy
  opportunities because buy thresholds sat above the batch2 holdout probability
  ceiling, then combined first-six plus remaining-symbol evidence into one
  descriptive 10-symbol summary with `4` local-paper fills, `2` buy
  opportunities, `18` zero-fill variants, and fee-aware delta sum `2.6518`,
- bounded entry-adverse lighter weight-decay contrast; it ran
  `weight_decay=0.001` with the same `core_plus_entry_adverse_v1`,
  hidden-units `4`, and `feature_standardization` in Docker `research`,
  replayed the 10-symbol wider sample, verified `4` local-paper fills,
  recorded the same two non-negative AMAT closed segments as `weight_decay=0.01`,
  found zero additional batch2 fills because buy thresholds still sat above the
  batch2 holdout probability ceiling, and wrote one descriptive summary outside
  Git with first-six probability range `0.531473`,
- bounded entry-adverse regularization trace-collapse diagnostic; it consumed
  existing hidden4, hidden8, `weight_decay=0.01`, and `weight_decay=0.001`
  artifacts only, reran no training or replay, verified referenced fills stayed
  local-paper-only, and wrote one external diagnostic showing regularization
  removed the hidden4 negative segments but reduced buy opportunities from `9`
  to `2`, replay fills from `18` to `4`, and widened the batch2 buy-threshold
  gap from `0.001121` to `0.004303` and `0.007378`,
- bounded entry-adverse feature-input concentration diagnostic; it consumed the
  trace-collapse diagnostic, existing probability traces, trade-path artifacts,
  and selected `snapshot=2026-06-18` Yahoo rows, reran no training or replay,
  reconstructed `core_plus_entry_adverse_v1` feature inputs, and found the
  regularized AMAT entries were the same unique signal row as the hidden4 AMAT
  non-negative entry while batch2 top-probability rows stayed below buy
  thresholds in all three traces,
- bounded entry-adverse source-breadth contrast; it kept
  `core_plus_entry_adverse_v1`, hidden-units `4`, `weight_decay=0.001`, and
  `feature_standardization`, trained in Docker `research` on ADBE, ADI, ADP,
  AEM, AGG, and AMAT from `snapshot=2026-06-18`, evaluated and replayed AMD,
  AMGN, AMT, and AMZN from the same snapshot, verified all `4` generated fills
  as `source: local_paper`, broke the previous batch2 zero-fill state through
  AMGN, and attributed both closed AMGN segments as fee-aware negative with
  fee-aware delta sum `-4.923`,
- bounded source-breadth AMGN loss attribution; it consumed existing
  source-breadth, trade-path, opportunity, and feature-input artifacts plus
  selected AMGN rows from `snapshot=2026-06-18`, reran no training or replay,
  found the AMGN buy opportunity was the same feature row as the previous
  `weight_decay=0.001` batch2 near-threshold AMGN row within `1e-9` tolerance,
  attributed the entry conversion to probability rising by about `0.0037505`
  while the minimum buy threshold moved down by `0.005000`, and identified a
  zero-range, low-volume AMGN signal shape rather than the prior high-upper-wick
  AMAT non-negative pattern,
- bounded entry-adverse signal-hygiene diagnostic; it consumed existing AMGN
  loss, feature-input concentration, wider-sample signal-quality, and
  source-breadth artifacts, reran no training or replay, found the
  zero-range/very-low-volume pattern concentrated in one AMGN signal row that
  recurred across prior regularized batch2 near-threshold rows and the
  source-breadth AMGN loss entry, and recorded that the pattern does not
  explain all first-six hidden4 loss-bearing rows,
- bounded entry-adverse sell-latency attribution; it consumed existing
  signal-hygiene, AMGN loss, and wider-sample signal-quality artifacts, reran no
  training or replay, compared `11` entry-adverse segments, found loss-bearing
  segments averaged `6.6` bars to first sell signal versus `1.333333333333` for
  non-negative segments, recorded `4` of `5` loss-bearing segments at or above
  `5` bars versus `0` of `6` non-negative segments, and showed loss-bearing
  segments had larger average adverse movement before sell,
- bounded entry-adverse exit-timing diagnostic overlay; it consumed existing
  sell-latency, signal-hygiene, AMGN loss, and wider-sample signal-quality
  artifacts plus selected local Yahoo rows, reran no training or replay, labeled
  all fixed 2/3/5-bar overlay outcomes as `source: diagnostic_overlay`, left
  `source: local_paper` fills unchanged, and found fixed 2-bar exits improved
  `5` of `5` loss-bearing segments on average while worsening `4` of `6`
  non-negative segments,
- bounded entry-adverse exit-policy sketch; it consumed existing exit-timing
  overlay, sell-latency, and signal-hygiene artifacts, reran no training or
  replay, recorded `5` research-only exit-policy family sketches, kept fixed
  2-bar exit as a stress overlay because it worsened most non-negative
  segments, and identified conditional latency-cap or adverse-then-latency
  overlays as the next replayable evidence shape without selecting a policy,
- bounded diagnostic exit-overlay helper; it adds a pure
  `compute_diagnostic_exit_overlays` helper that consumes provided trade
  segments and `Bar` inputs, enforces fixed 2/3/5-bar diagnostic overlays,
  records conditional latency/adverse metadata without selecting a policy,
  labels overlay outcomes as `source: diagnostic_overlay`, and performs no
  file, network, credential, broker, CLI, job, dashboard, scheduler, training,
  or replay work,
- bounded diagnostic exit-overlay helper smoke; it applied the pure helper to
  `11` existing entry-adverse trade segments and selected
  `snapshot=2026-06-18` Yahoo rows, produced `33` fixed 2/3/5-bar
  `diagnostic_overlay` outcomes, matched the previous one-off overlay
  timestamp/price evidence for all `33` marks, preserved referenced
  `source: local_paper` fills, and wrote one compact artifact outside Git,
- bounded conditional exit-overlay contrast; it consumed the helper smoke,
  exit-timing, sell-latency, and signal-hygiene artifacts, compared `3`
  conditional latency/adverse metadata probes across `5` loss-bearing and `6`
  non-negative segments, found `latency_ge_5_at_2_bar` matched `4` of `5`
  loss-bearing segments and `0` of `6` non-negative segments, kept all `66`
  overlay/metadata outcomes labeled `source: diagnostic_overlay`, preserved
  referenced local-paper fill sources, and wrote one compact artifact outside
  Git without replay or training,
- bounded exit-latency composite overlay diagnostic; it consumed the
  conditional contrast, helper smoke, and exit-timing artifacts, computed one
  descriptive composite scenario where `4` latency-matched loss-bearing
  segments used fixed 2-bar `diagnostic_overlay` outcomes while the remaining
  `7` segments kept `source: local_paper` exits, improved overall gross delta
  from `-1.4563` to `3.383729296875`, preserved source separation, and wrote
  one compact artifact outside Git without replay or training,
- bounded diagnostic exit-composite helper; it extends
  `exit_overlay_diagnostic` with a pure `compute_diagnostic_exit_composite`
  helper that consumes provided diagnostic overlay segment payloads, inspects
  one named conditional metadata id, substitutes a named fixed-horizon
  `diagnostic_overlay` only when the condition is met, retains
  `source: local_paper` exits otherwise, returns descriptive group/overall
  metrics, and performs no file, network, credential, broker, CLI, job,
  dashboard, scheduler, training, replay, or artifact-write work,
- bounded diagnostic exit-composite helper smoke; it applied the pure
  `compute_diagnostic_exit_composite` helper to existing composite context
  artifacts, reproduced the one-off source counts of `4`
  `diagnostic_overlay` outcomes and `7` `local_paper` outcomes, matched the
  one-off gross-delta sums including overall composite sum
  `3.383729296875`, existing local-paper sum `-1.4563`, and delta
  `4.840029296875`, and wrote one compact artifact outside Git without replay
  or training,
- bounded research-only exit-latency sandbox helper; it adds
  `ExitLatencySandboxSegment`, `ExitLatencySignalRecord`, and
  `compute_exit_latency_sandbox_marks` as pure research helpers that consume
  provided trace timing records and `Bar` inputs, emit source-labeled
  `diagnostic_overlay` marks only when latency and bounded horizon conditions
  are met, report missing signal, entry-bar, signal-bar, and horizon states
  without normal diagnostic failures, and perform no file, network,
  credential, broker, CLI, job, dashboard, scheduler, training, replay, or
  artifact-write work,
- bounded research-only exit-latency sandbox helper smoke; it applied the pure
  sandbox helper to `11` existing entry-adverse segments and selected
  `snapshot=2026-06-18` Yahoo rows, produced `4` available
  `diagnostic_overlay` marks for the `latency_ge_5_at_2_bar` condition,
  matched the composite helper smoke keys, timestamps, prices, and gross-delta
  sum `-2.486370703125`, and created zero local-paper fills or broker outcomes,
- bounded fixed entry-adverse PyTorch CUDA validation block; it kept
  `core_plus_entry_adverse_v1`, `hidden_units=4`, `weight_decay=0.001`, and
  `feature_standardization` fixed, trained on ADBE/ADI/ADP/AEM/AGG/AMAT from
  `snapshot=2026-06-18`, evaluated ANET/APH/APO/APP/ASML/AVGO, recorded
  evaluation probability range `0.493954`, replayed cap-2 thresholds through
  local paper with `4` verified `source: local_paper` fills, and attributed `2`
  closed APH trade paths with fee-aware delta sum `1.4194`,
- bounded longer-depth entry-adverse PyTorch CUDA contrast; it kept the same
  feature set, hidden units, weight decay, preprocessing, source symbols, and
  evaluation symbols as the short block, raised only bounded training caps to
  `max_epochs=16` and `max_steps=512`, recorded evaluation probability range
  `0.460215`, replayed cap-2 thresholds with `4` verified
  `source: local_paper` fills, attributed `2` closed APH trade paths with
  fee-aware delta sum `8.0192`, and wrote one depth-vs-short comparison
  artifact outside Git,
- bounded short-vs-depth APH signal/path attribution; it consumed existing
  feature-branch, replay, trade-path, trace, event, and selected APH bar
  artifacts only, found the deeper run entered APH one execution bar earlier at
  `150.25` versus `151.24`, exited seven execution bars later at `154.29`
  versus `151.98`, lifted representative fee-aware delta by `3.2999`, and
  attributed the larger max drawdown to staying long through a later
  close-marked peak and pullback before the `13:49` local-paper exit,
- bounded second-holdout short-vs-depth replay contrast; it reused the
  completed short and longer-depth entry-adverse artifacts, selected AAPL,
  ABBV, ABNB, ABT, ACN, and AMD from the existing `snapshot=2026-06-18` Yahoo
  file after excluding the source and first evaluation symbols, ran both
  replay paths in Docker `research` with RTX 4090 visible and cap-2 thresholds,
  produced zero local-paper fills for both runs, and attributed the zero-fill
  result to buy thresholds sitting above every selected slice's observed
  probability ceiling,
- bounded first-evaluation source-context contrast; the planned 12-symbol
  source context was blocked by the existing `candidate_feature_branch`
  `data_slices <= 6` cap, so no cap/code change was made and a cap-compliant
  ANET/APH/APO/APP/ASML/AVGO source context was trained/evaluated in Docker
  `research` with the same entry-adverse feature/model/preprocessing settings,
  replayed AAPL, ABBV, ABNB, ABT, ACN, and AMD with cap-2 thresholds, produced
  `6` verified `source: local_paper` fills on AMD only, and attributed `3`
  closed AMD trade segments with fee-aware delta sum `3.3752`,
- bounded AMD segment-quality diagnostic; it consumed the first-evaluation
  source-context replay, robustness, trace, event, and selected AMD bar
  artifacts only, compared the one fee-aware negative AMD segment against the
  two non-negative AMD segments, found the negative segment had a much smaller
  entry probability margin, larger adverse movement, and negative fixed 2/3/5
  bar `diagnostic_overlay` marks while the non-negative segments had positive
  fixed horizon marks,
- bounded AMD entry feature-input diagnostic; it reconstructed
  `core_plus_entry_adverse_v1` inputs for the AMD entry rows and top
  near-threshold rows from existing trace and bar evidence only, found the
  non-negative AMD entries had lower average `upper_wick_share`, nonzero
  `close_position_in_bar`, lower `low_vs_prior_low_return`, and higher
  `volume_change` than the fee-aware negative entry, and observed that `4` of
  `6` below-threshold near-miss rows were closer to the negative entry by
  feature distance,
- bounded AMD entry-filter diagnostic overlay; it consumed the completed AMD
  feature-input, segment-quality, and source-context attribution artifacts plus
  selected AMD Yahoo rows only, labeled retained/skipped overlay outcomes as
  `source: diagnostic_overlay`, left the original `6` local-paper fills
  unchanged as `source: local_paper`, and found the all-three overlay sketch
  skipped the one negative AMD segment while retaining both non-negative AMD
  segments, with all `6` near-miss rows still below the minimum buy threshold,
- bounded cross-sample entry-filter diagnostic overlay; it consumed the AMD
  overlay and existing wider entry-adverse artifacts, labeled `56` wider-sample
  overlay outcomes as `source: diagnostic_overlay`, left the original `18`
  wider-sample local-paper fills unchanged as `source: local_paper`, and found
  the AMD-derived all-three sketch did not recur in the wider hidden4 sample:
  it retained all `3` wider fee-aware negative segments, skipped all `6`
  wider fee-aware non-negative segments, and kept all `4` batch2 near-threshold
  rows below buy threshold,
- bounded first-evaluation source-context depth contrast; it reused the same
  `core_plus_entry_adverse_v1`, `hidden_units=4`, `weight_decay=0.001`,
  `feature_standardization`, ANET/APH/APO/APP/ASML/AVGO source context, and
  AAPL/ABBV/ABNB/ABT/ACN/AMD evaluation context, raised only training caps to
  `max_epochs=16` and `max_steps=512` in Docker `research`, replayed cap-2
  thresholds with `4` verified `source: local_paper` AMD fills, attributed `2`
  closed non-negative AMD segments with fee-aware delta sum `2.0354`, and
  wrote a depth-vs-short comparison artifact showing probability range
  increased by `0.079126`, local-paper fill count fell by `2`, max drawdown
  fell by `2.593618`, and the cross-sample overlay still argues against
  encoding the AMD-derived entry filter,
- local-paper holdout source verification now treats missing event files for
  zero-fill replay variants as empty evidence rather than a non-local fill
  failure, while still failing unreadable artifacts for variants with fills,
- agent lane stateboards under `agents/`,
- single-shot Engine Research Agent runner CLI with external queue, lock, and
  run-state artifacts,
- Engine Research Agent enqueue path for existing Docker `research` job kinds,
- single-shot Data Agent runner CLI with external queue/run-state artifacts and
  a bounded market-data inventory job,
- daily report bundle generator,
- Dockerfile and compose services: `engine`, `web`, `research`,
- tests and lint baseline.

## Verification Baseline

The latest completed baseline passed:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Expected result:

- `284 passed`
- `All checks passed!`
- Docker compose config exits zero

## Current Architecture Decisions

Read these files before changing architecture:

- `VISION.md`
- `ARCHITECTURE.md`
- `AGENTS.md`
- `DECISIONS.md`
- `RUNBOOK.md`
- `agents/README.md`
- `INTERIM_GOAL_SCRIPT.md`

Key decisions:

- JSONL is the source of truth.
- SQLite is a rebuildable query view.
- Dashboard actions are local-only until broker adapters exist.
- Base engine has no heavy runtime dependencies.
- GPU/ML work belongs in the research lane/profile.
- GPU compute and training must run through the Docker `research` target/profile
  unless an explicit future decision allows otherwise.
- PyTorch CUDA is approved only for the Docker `research` target/profile. Keep
  it out of the base engine and local dev/test dependency path.
- GPU model artifacts belong outside the repo at
  `D:\thericher-v2\model-artifacts` by default.
- Operator-provided market data lives outside the repo at `D:\market_data`.
- Additional market data acquisition must use no-auth, lawful,
  license-compatible sources and stop when those limits are hit.
- Local paper execution fills at next completed bar open and labels simulated
  fills with `source: local_paper`.
- Long Codex tasks refresh `NEXT_CODEX_GOAL.md` before ending.
- Engine Research Agent keeps bounded GPU experiments queued by default once GPU
  research starts.
- Data Agent has a separate non-GPU single-shot runner for descriptive
  inventory jobs under `D:\thericher-v2\model-artifacts\data-agent`.
- Agent stateboards are lane queues only; `NEXT_CODEX_GOAL.md` remains the
  single next objective.
- First paper execution target is US equities through KIS.
- Korean equities are research/data-parallel at first.

## Recommended Next Slice

The Engine Research Agent runner now supports both single-shot enqueue and
single-shot run flows. The first research-useful queued job beyond smoke was
`engine-agent-feature-replay-firsteval-depth-axp-azn-ba-20260717-r2`. It mounted
current `src` read-only into Docker `research`, replayed the first-evaluation
depth entry-adverse feature branch on AXP, AZN, and BA from
`snapshot=2026-06-18`, completed `9` variants, produced zero fills, and
verified local-paper-only evidence with no non-local, broker, or unknown fill
sources.

The follow-up attribution consumed only existing runner, replay, robustness,
and probability trace artifacts. It wrote one compact external artifact:

- `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-axp-azn-ba-zero-fill-attribution-20260717\metrics.json`

Attribution summary:

- source probability max was `0.596555`, which derived buy thresholds
  `0.594000`, `0.595000`, and `0.596000`,
- AXP/AZN/BA holdout max probabilities were `0.542807`, `0.518582`, and
  `0.561073`,
- combined holdout max was `0.561073`, leaving the minimum buy threshold
  `0.032927` above observed holdout probabilities,
- buy opportunity count was `0`, sell opportunity count was `333`, replay fill
  count was `0`, and all fill evidence remained local-paper-only,
- missing event artifacts were recorded only for zero-fill variants and treated
  as empty evidence, not as non-local fills.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used an existing attribution primitive and
updated only handoff/stateboard documents.

The Data Agent now has the smallest useful second executable worker:
`thericher-v2-data-agent`. It supports single-shot `enqueue-data-job` and
`run-once` flows for the closed first kind `market_data_inventory`. The first
smoke job, `data-agent-market-data-inventory-20260717`, read existing
`D:\market_data` metadata only, used no Docker/GPU/network/credentials/broker,
and wrote:

- `D:\thericher-v2\model-artifacts\data-agent\runs\data-agent-market-data-inventory-20260717\status.json`
- `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-20260717\metrics.json`

Inventory summary:

- known folders: `2`,
- snapshots inspected: `5`,
- useful files: `5`,
- folders found: Yahoo intraday starter canonical 1m and Yahoo daily universe
  canonical daily,
- warnings: none.

The first two-worker cadence completed without adding an orchestrator:

- Data Agent job `data-agent-market-data-inventory-cadence-20260717` claimed one
  queued `market_data_inventory` item, read existing `D:\market_data` metadata
  only, used no Docker/GPU/network/credentials/broker, and wrote:
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-cadence-20260717\metrics.json`.
- Engine Research Agent job
  `engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717` claimed one
  queued `candidate_feature_branch_replay` item, ran Docker `research` with RTX
  4090 visible, replayed AMAT/AMZN/BA from `snapshot=2026-06-18`, completed `9`
  variants, produced `12` verified `source: local_paper` fills, and wrote:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717\metrics.json`.

Lane separation evidence:

- both worker queues were empty after their single `run-once`,
- Engine Research Agent artifacts stayed under `engine-research-agent`,
  `candidate-feature-branch-replay`, and `candidate-threshold-robustness`,
- Data Agent artifacts stayed under `data-agent`,
- Data Agent did not use Docker/GPU, and Engine Research Agent remained the only
  Docker `research`/GPU worker.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing single-shot workers and updated
only handoff/stateboard documents.

The first runner-queued longer depth attempt also completed without adding an
orchestrator:

- Data Agent job `data-agent-market-data-inventory-depthjob-20260717-r1`
  claimed one queued `market_data_inventory` item, read existing
  `D:\market_data` metadata only, found `2` known folders, `5` snapshots, and
  `5` useful files, and acquired no data.
- Engine Research Agent job
  `engine-agent-depth-target-longer-mini-breadth-20260717-r1` claimed one
  queued `candidate_depth_target` item, ran Docker `research` with RTX 4090
  visible, selected the existing `m1_lb3_b10_s10` breadth-holdout variant for
  research scheduling, trained and evaluated with `max_bars=180`,
  `max_epochs=16`, and `max_steps=512`, and wrote:
  `D:\thericher-v2\model-artifacts\candidate-depth-target\engine-agent-depth-target-longer-mini-breadth-20260717-r1\metrics.json`.

Important result: the depth attempt ended as `prepared_not_depth_targeted`, not
`candidate_depth_target_ran_only`, because the queued command omitted explicit
`--data-slice` and `--robustness-slice` arguments. Training and evaluation ran
on PyTorch CUDA (`torch`, NVIDIA GeForce RTX 4090), but calibration and holdout
slice counts were both `0`; local-paper verification remained empty and
local-only with no non-local fill sources.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing single-shot workers and updated
only handoff/stateboard documents.

Next, rerun the same `candidate_depth_target` lane through the Engine Research
Agent runner with explicit existing Yahoo 1m slices, for example
`src_adbe=/app/market_data/.../snapshot=2026-06-18/ohlcv_1m.csv.gz:ADBE` as a
`--data-slice` and `hold_aem=/app/market_data/.../snapshot=2026-06-18/ohlcv_1m.csv.gz:AEM`
as a `--robustness-slice`. Keep artifacts outside Git, avoid new orchestration,
and keep Execution Agent non-executable until an explicit KIS paper goal allows
credentials/API calls.

The explicit-slice depth target then completed through the runner:

- Data Agent job `data-agent-market-data-inventory-explicit-depth-20260717-r1`
  claimed one queued inventory item, read existing `D:\market_data` metadata
  only, again found `2` known folders, `5` snapshots, and `5` useful files, and
  acquired no data.
- Engine Research Agent job `engine-agent-depth-target-explicit-slices-20260717-r1`
  claimed one queued `candidate_depth_target` item and ran exactly one Docker
  `research` `run-once` with current `src` mounted read-only. It used
  `src_adbe`, `src_adi`, and `src_adp` as source slices and `hold_aem`,
  `hold_agg`, and `hold_amat` as holdout slices from the existing
  `snapshot=2026-06-18` Yahoo 1m file.
- Status reached `candidate_depth_target_ran_only` with PyTorch CUDA
  (`torch`, NVIDIA GeForce RTX 4090), `max_bars=180`, `max_epochs=16`,
  `max_steps=512`, `540` bars, and `528` examples.
- Training loss moved from `0.690765` to `0.689105`; evaluation accuracy was
  `0.543561`, equal to the majority baseline, with probability range
  `0.023383`.
- Calibration completed `3` slices and `18` variants with `631` local-paper
  fills. Holdout completed `3` slices and `18` variants with `531` verified
  `source: local_paper` fills, no non-local sources, PnL range `-27.9099865722656`
  to `-0.0580`, and max drawdown max `38.0201341796875`.
- Main artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target\engine-agent-depth-target-explicit-slices-20260717-r1\metrics.json`.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing single-shot workers and updated
only handoff/stateboard documents.

Next, attribute the explicit-slice depth target before spending more GPU time.
Consume existing depth target, robustness, probability trace, and local-paper
event artifacts only. Find whether the poor holdout result is concentrated by
slice, threshold pair, fill frequency, exit latency, or outlier probability
rows. Keep the result artifact-only and outside Git unless a small helper is
clearly needed.

The explicit-slice depth target attribution then completed artifact-only:

- It consumed the existing depth-target, holdout robustness, probability trace,
  and local-paper event artifacts for
  `engine-agent-depth-target-explicit-slices-20260717-r1`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-attribution\engine-agent-depth-target-explicit-slices-20260717-r1-attribution\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, or new market
  data acquisition.
- Parsed holdout fills remained `531` verified `source: local_paper` fills
  with no non-local fill evidence.
- Variant-grid PnL sum was `-120.63570061035150`; max drawdown max remained
  `38.0201341796875`.
- Loss concentration was mainly AMAT, not the AGG max-probability outlier.
  AGG contained the single `0.957193` probability row, but AGG losses were
  small compared with AMAT.
- The first threshold bands overlapped the dense middle of the holdout
  probability distribution, causing many entries. AMAT still showed sharply
  negative variants at higher thresholds with fewer fills, so both over-entry
  and path quality need diagnosis before more GPU training.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts only and updated
handoff/stateboard documents.

Next, inspect AMAT and AEM trade paths from the explicit-slice depth target.
Use temporary Codex sub-agents as sidecar reviewers where useful, but keep the
repo-owned durable workers unchanged: Engine Research and Data are executable
single-shot workers; Execution, Infra, and Review remain stateboards unless a
future explicit goal makes a durable worker necessary.

The AMAT/AEM trade-path diagnostic then completed artifact-only:

- It consumed the existing attribution, holdout robustness, AMAT/AEM
  probability traces, AMAT/AEM event artifacts, and selected local Yahoo rows
  from `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-trade-path-diagnostic\engine-agent-depth-target-explicit-slices-20260717-r1-amat-aem-trade-paths\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market
  data acquisition, or durable worker creation.
- AMAT/AEM covered `12` variants, `403` local-paper fills, `198` closed
  segments, and `7` open segments; all parsed fill evidence remained
  `source: local_paper`.
- AMAT carried the larger closed-path loss concentration: `190` fills,
  reported PnL sum `-91.3836731445312`, closed fee-aware delta sum
  `-91.6983`, `94` closed segments, `58` negative fee-aware closed segments,
  and `2` open segments.
- AEM showed more entry-frequency plus open-exposure behavior: `213` fills,
  reported PnL sum `-28.4819274658203`, closed fee-aware delta sum
  `-31.6787`, `104` closed segments, `68` negative fee-aware closed segments,
  and `5` open segments without post-entry sell signals before the bounded
  window end.
- Engine Research sidecar agreed AMAT high-threshold losers look more like
  path-quality failures than only delayed exits, while AEM shows more
  over-entry and delayed/open-exposure behavior.
- Execution sidecar inspected the 12 AMAT/AEM event files and found `403`
  fills, all `payload.source: local_paper`, with zero broker-disabled,
  unknown, diagnostic-overlay, or non-local fill sources.
- Review sidecar found no blocking sprawl or durable-worker drift, but flagged
  growing stateboard length as the next simplification watch item.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

Next, run a bounded AMAT/AEM replay-shape diagnostic overlay from existing
traces and bars. Keep original local-paper fills unchanged, label overlay
outcomes as `source: diagnostic_overlay`, and compare only a small
entry-cadence/max-hold shape before any further GPU training.

The AMAT/AEM replay-shape diagnostic overlay then completed artifact-only:

- It consumed the AMAT/AEM trade-path diagnostic, AMAT/AEM probability traces,
  existing event artifacts, and selected local Yahoo rows from
  `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-overlay\engine-agent-depth-target-explicit-slices-20260717-r1-amat-aem-replay-shape-overlay\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market
  data acquisition, replay mutation, or durable worker creation.
- Original AMAT/AEM fills stayed `403` verified `source: local_paper` fills.
  The overlay produced `1,479` source-separated outcomes labeled
  `source: diagnostic_overlay`.
- The overlay grid covered `108` summaries from `12` AMAT/AEM threshold
  variants across max-hold `3`, `5`, and `8` bars and cooldown `0`, `5`, and
  `10` bars.
- Cooldown mainly suppressed churn: combined closed diagnostic segments fell
  from `276/242/230` at cooldown `0` to `104/99/95` at cooldown `10` across
  max-hold `3/5/8`, but diagnostic losses stayed negative.
- AEM showed more cadence/open-exposure sensitivity, including more first-3-bar
  no-lift marks. AMAT stayed path-quality heavy: fewer diagnostic closed
  segments than AEM (`656` versus `805`) but much larger closed diagnostic loss
  (`-448.48063889770692837` versus `-132.289600891113956329`).
- Execution sidecar verified original fills remained `local_paper`, overlay
  outcomes remained `diagnostic_overlay`, and no broker, non-local, or unknown
  source evidence appeared.
- Review sidecar found no blocking sprawl, durable-worker drift, promotion
  language, or gate creep.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

Next, check whether the same replay-shape evidence repeats on a small held-out
slice set from existing artifacts. Keep it artifact-only, add one entry-cluster
cap mark and one pre-entry path-quality bucket, preserve `local_paper` source
evidence, and keep all overlay outcomes as `diagnostic_overlay`.

The held-out/context replay-shape overlay then completed artifact-only:

- It consumed the AMAT/AEM overlay, existing holdout/source-context robustness
  artifacts, AGG/ADBE/ADI probability traces, existing event artifacts, and
  selected local Yahoo rows from `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-overlay\engine-agent-depth-target-explicit-slices-20260717-r1-heldout-context-replay-shape-overlay\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market data
  acquisition, replay mutation, or durable worker creation.
- Original AGG/ADBE/ADI fills stayed `565` verified `source: local_paper`
  fills. The overlay produced `2,494` outcomes labeled
  `source: diagnostic_overlay`.
- Cadence and entry-cluster evidence repeated across the held-out/context set:
  AGG had `1,361` cooldown-suppressed and `1,917` cluster-cap-suppressed
  opportunities; ADBE had `724` and `675`; ADI had `699` and `414`.
- AMAT-style path damage did not repeat uniformly. AGG stayed mostly churn
  with small diagnostic damage (`-16.077863854216983183` closed fee-aware
  delta), ADBE looked more AEM-like (`-135.898423535157675082`), and ADI
  partly repeated heavier path damage (`-348.41501501769951972`) but below
  AMAT's prior overlay magnitude.
- Execution sidecar verified source separation: original fills remained
  `local_paper`, overlay outcomes remained `diagnostic_overlay`, and no broker,
  non-local, or unknown source evidence appeared.
- Review sidecar found no policy-doc update, blocking sprawl, durable-worker
  drift, report/gate creep, or model-promotion language.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

Next, separate entry-cluster churn from early adverse path quality on ADI versus
AGG using one artifact-only diagnostic. Keep it source-separated and avoid any
local-paper replay rule change before another GPU training block.

The ADI/AGG replay-shape driver attribution then completed artifact-only:

- It consumed the held-out/context overlay, existing AGG/ADI probability traces,
  existing event artifacts, and selected local Yahoo rows from
  `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-replay-shape-driver-attribution\engine-agent-depth-target-explicit-slices-20260717-r1-adi-agg-entry-cluster-path-quality\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market data
  acquisition, replay mutation, or durable worker creation.
- Original AGG/ADI fills stayed `376` verified `source: local_paper` fills. The
  diagnostic produced `1,738` outcomes labeled `source: diagnostic_overlay`.
- ADI had fewer churn markers than AGG (`414` cluster-cap suppressions versus
  `1,917`, and `699` cooldown suppressions versus `1,361`) but much larger
  closed diagnostic damage (`-348.41501501769951972` versus
  `-16.077863854216983183`).
- ADI loss per closed diagnostic segment was about `-0.4438407834620376047`
  versus AGG `-0.0173627039462386427`, so raw entry-cluster churn does not
  explain the ADI/AGG contrast.
- Engine Research sidecar found ADI's dominant driver is early adverse path
  quality, with open exposure secondary. ADI early-adverse bucket carried the
  core damage, while later-in-cluster entries were harmful per segment but too
  few to explain the aggregate.
- Execution sidecar verified original fills remained `local_paper`, diagnostic
  outcomes remained `diagnostic_overlay`, and no broker, non-local, or unknown
  source evidence appeared.
- Review sidecar found no policy-doc update, blocking sprawl, durable-worker
  drift, report/gate creep, or model-promotion language.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

The ADI/AGG feature-input diagnostic then completed artifact-only:

- It consumed the ADI/AGG driver attribution, AGG/ADI probability traces,
  existing event artifacts, and selected local Yahoo rows from
  `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-diagnostic\engine-agent-depth-target-explicit-slices-20260717-r1-adi-agg-feature-input-diagnostic\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market data
  acquisition, replay mutation, or durable worker creation.
- Original ADI/AGG fills stayed `376` verified `source: local_paper` fills. The
  diagnostic produced `660` candidate-entry rows labeled
  `source: diagnostic_overlay`.
- ADI adverse/no-lift rows leaned toward weaker pre-entry close return and
  lower close position inside the prior 3-bar range, but the strongest
  univariate separation stayed modest. AGG showed price-shape separation, while
  probability-margin and volume mean deltas looked outlier-sensitive once
  checked with row-level AUC and medians.
- Engine Research sidecar found the signal exists but is not stable enough
  across ADI and AGG to justify spending the next block on GPU/model-input
  training.
- Execution sidecar verified original fills remained `local_paper`, diagnostic
  rows remained `diagnostic_overlay`, and no broker, KIS, credential, non-local,
  or unknown source evidence appeared.
- Review sidecar found no blocking sprawl, durable-worker drift, scheduler,
  dashboard, broker creep, or model-promotion language.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

The cross-slice feature-input stability check then completed artifact-only:

- It consumed the ADI/AGG feature-input diagnostic, ADBE/AEM/AMAT explicit-slice
  probability traces, existing event artifacts, and selected local Yahoo rows
  from `snapshot=2026-06-18`.
- It wrote one compact external artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`.
- It used no Docker, GPU, broker, credential, network, KIS API, new market data
  acquisition, replay mutation, or durable worker creation.
- Original ADBE/AEM/AMAT fills stayed `592` verified `source: local_paper`
  fills. The diagnostic produced `659` candidate-entry rows labeled
  `source: diagnostic_overlay`.
- Stable-direction evidence remained modest: probability rank, probability
  margin, and last-volume-vs-prior-average repeated direction in `5/5` slices
  with average directional AUC around `0.526` to `0.534`.
- Pre-entry close position and prior range repeated direction in `4/5` slices,
  but flipped on one symbol each. Other entry-shape and cluster features stayed
  mixed across the five slices.
- Engine Research sidecar found enough evidence for one narrow Docker
  `research` feature-branch ablation, but not for a broad GPU training sweep.
- Execution sidecar verified original fills remained `local_paper`, diagnostic
  rows remained `diagnostic_overlay`, and no broker, KIS, credential, non-local,
  or unknown source evidence appeared.
- Review sidecar found no artifact sprawl, durable-worker drift, scheduler,
  dashboard, broker creep, or model-promotion language. It also flagged the
  temporary generator as a cleanup item; it was removed before commit.

Claude drift-check was not needed for this slice because it made no code,
architecture, or policy edits; it used existing artifacts, temporary Codex
sidecars, and a compact external diagnostic only.

Next, run one bounded Docker `research` feature-input ablation that separates
raw pre-entry features from probability-derived meta features. Keep replay
unchanged, artifacts outside Git, and local-paper source evidence separate from
diagnostic overlays.

The bounded feature-input ablation then completed:

- It added one small research-only helper/job kind,
  `candidate_feature_input_ablation`, for repeated feature-group checks over
  diagnostic candidate-entry rows.
- It consumes the cross-slice stability artifact, filters selected rows to
  `source: diagnostic_overlay`, separates raw pre-entry market features from
  probability-derived meta features, and writes metrics/model artifacts outside
  Git.
- Claude drift-check was attempted twice before code edits, but both CLI calls
  timed out without output. The implementation stayed within `HANDOFF.md`,
  `ARCHITECTURE.md`, and `DECISIONS.md` boundaries.
- Local dry-run wrote a prepared artifact because local dev has no torch
  backend:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-local-dryrun-20260717\metrics.json`.
- Docker `research` PyTorch CUDA run completed on NVIDIA GeForce RTX 4090 and
  wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-cross-slice-20260717-r1\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-cross-slice-20260717-r1\feature_input_ablation.pt`.
- The ablation used `24` selected diagnostic rows from ADBE/AEM/AMAT, balanced
  `12/12` adverse-or-no-lift versus non-adverse. It preserved the source
  evidence from the upstream artifact: `592` verified `source: local_paper`
  fills and `659` diagnostic rows labeled `source: diagnostic_overlay`.
- In this tiny in-sample run, the combined raw pre-entry plus probability-meta
  group reached accuracy `0.541667` and final loss `0.687648`, while the
  probability-meta-only and raw-pre-entry-only groups both recorded accuracy
  `0.500000`. Treat this as descriptive reconnaissance only.
- Engine Research sidecar found the implementation matches the bounded goal,
  but warned the result is too small to treat as validation.
- Infra sidecar verified PyTorch remains Docker `research` only, no dependency
  or Docker file changed, and artifacts stayed outside Git.
- Execution sidecar verified no local-paper replay, broker, KIS, credential,
  live, or paper-submit path changed. Its source-guard suggestion was added:
  non-`diagnostic_overlay` selected rows are excluded.
- Review sidecar found no scheduler, dashboard, coordinator, durable-worker, or
  promotion-language creep, while noting the new job kind should remain a
  reusable research primitive rather than a growing family.

The full-row feature-input ablation then completed:

- It extended the existing `candidate_feature_input_ablation` helper/job with
  explicit row modes: existing `selected` behavior and `all_diagnostic`
  lineage reconstruction.
- Full-row mode reconstructs diagnostic candidate-entry rows from existing
  stability lineage, probability traces, and local Yahoo rows only. It does not
  call local-paper replay, broker, KIS, credential, network, scheduler, or
  durable worker paths.
- Claude drift-check was attempted before code edits and timed out after about
  `184` seconds without output. The change stayed bounded by `HANDOFF.md`,
  `ARCHITECTURE.md`, and `DECISIONS.md`.
- Focused tests prove selected behavior remains unchanged, full-row lineage
  rows are `source: diagnostic_overlay`, local-paper fills remain evidence
  only, row mode is limited to the ablation job, and unknown lineage paths are
  not read.
- Local no-backend dry-run wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-local-dryrun-20260717-r2\metrics.json`.
- Docker `research` PyTorch CUDA run completed on NVIDIA GeForce RTX 4090 and
  wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-cross-slice-20260717-r2\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-cross-slice-20260717-r2\feature_input_ablation.pt`.
- The full-row run used `659` reconstructed diagnostic rows with zero drops:
  `src_adbe=242`, `hold_aem=235`, `hold_amat=182`. Labels were imbalanced:
  `382` adverse-or-no-lift and `277` non-adverse.
- Source evidence remained separated: upstream reference fills stayed `592`
  verified `source: local_paper`; all reconstructed candidate-entry rows were
  `source: diagnostic_overlay`.
- Compared with the selected `24`-row run, the full-row pattern did not repeat
  cleanly. Selected rows were balanced and the combined group had lower final
  loss (`0.687648`), while the full-row run had raw pre-entry final loss
  `0.671724`, probability-meta final loss `0.686541`, combined final loss
  `0.679072`, and accuracy mostly reflected the adverse/no-lift majority rate.
  Treat this as descriptive research evidence only.
- Engine Research sidecar advised a slice/variant-aware follow-up using
  balanced accuracy, AUC, log loss, and per-slice metrics to control for label
  imbalance and duplicated threshold variants.
- Infra/Execution/Review sidecars found no broker/KIS/credential boundary
  breach, no replay mutation, no local/base PyTorch dependency, no scheduler,
  dashboard, coordinator, durable-worker expansion, or model-promotion
  language. A path-resolver watch item was tightened before final verification.

The slice-aware feature-input evaluation pass then completed:

- It extended the existing `candidate_feature_input_ablation` runner with
  in-sample descriptive evaluation metrics inside the existing artifact:
  majority-rate context, balanced accuracy, class recalls, average-rank AUC,
  log loss, per-slice metrics, and per-variant metrics.
- It also threads aligned row metadata for `source`, `slice_id`, `symbol`,
  `variant_id`, `offset`, and `execution_bar_start`, and rejects lineage paths
  that use `..` to escape the configured external artifact or market-data
  roots.
- Focused tests cover diagnostic-only row metadata, majority-rate traps, tied
  AUC behavior, single-class slice/variant cells, source separation, and
  lineage traversal rejection.
- Docker `research` PyTorch CUDA ran once on NVIDIA GeForce RTX 4090 and wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-slice-aware-cross-slice-20260717-r1\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-slice-aware-cross-slice-20260717-r1\feature_input_ablation.pt`.
- The run used the same `659` diagnostic rows with zero drops and `592`
  upstream reference fills preserved as `source: local_paper` evidence only.
  All metric rows were `source: diagnostic_overlay`.
- The descriptive context showed `382/277` labels, adverse/no-lift majority
  rate `0.579666`, `256` unique signal keys, and a `2.574219` row-to-unique
  ratio caused by threshold-variant duplication.
- Overall metrics:
  probability-meta baseline accuracy `0.579666`, balanced accuracy `0.500000`,
  AUC `0.487899`, log loss `0.686541`;
  raw pre-entry accuracy `0.579666`, balanced accuracy `0.500000`, AUC
  `0.600998`, log loss `0.671724`;
  raw plus probability accuracy `0.566009`, balanced accuracy `0.490205`, AUC
  `0.530828`, log loss `0.679072`.
- Read this as descriptive evidence only: raw pre-entry has some ranking signal
  in the duplicated-row view, but the default decision threshold still mostly
  predicts the majority class. A unique-signal follow-up should come before
  another deeper GPU training block.

Next, add a bounded unique-signal feature-input evaluation so threshold-variant
duplication is visible in the metric payload before any deeper GPU training.
Keep it artifact-driven, source-separated, and descriptive.

The unique-signal feature-input evaluation then completed:

- It extended the existing `candidate_feature_input_ablation` payload with
  `unique_signal_descriptive_evaluation` beside the existing row-level metrics.
  Unique signals are keyed by `slice_id`, `symbol`, `execution_bar_start`, and
  `offset`; repeated threshold variants use mean probability, not max variant.
- Incomplete signal keys are counted and skipped from scored unique metrics.
  Mixed-label signals are counted and skipped from primary unique metrics.
- Focused tests cover selected-mode missing keys, deterministic duplicate
  collapse, no max-variant selection, mixed-label signal handling, single-class
  behavior, source separation, and existing lineage/artifact guards.
- Claude drift-check was attempted before code edits and timed out after about
  `184` seconds without output. The implementation stayed inside the existing
  helper/job payload.
- Docker `research` PyTorch CUDA ran once on NVIDIA GeForce RTX 4090 and wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-unique-signal-cross-slice-20260717-r1\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-unique-signal-cross-slice-20260717-r1\feature_input_ablation.pt`.
- The run used `659` diagnostic rows, zero drops, `256` complete unique
  signals, `183` duplicate signals, max `6` variants per signal, zero missing
  signal keys, and zero mixed-label signals. All metric rows remained
  `source: diagnostic_overlay`; `592` upstream fills remained
  `source: local_paper` evidence only.
- Unique-signal overall metrics:
  probability-meta baseline AUC `0.473905`, balanced accuracy `0.500000`, log
  loss `0.687833`;
  raw pre-entry AUC `0.598074`, balanced accuracy `0.500000`, log loss
  `0.679958`;
  raw plus probability AUC `0.529295`, balanced accuracy `0.480087`, log loss
  `0.684430`.
- Raw pre-entry ranking evidence survived duplicate collapse, but default
  threshold behavior still mostly predicts the adverse/no-lift majority class.
  Slice-level raw pre-entry unique AUC was `0.598034` on `src_adbe`,
  `0.517943` on `hold_aem`, and `0.678744` on `hold_amat`.

Next, add a bounded unique-signal probability-band diagnostic for the existing
feature-input ablation payload. The goal is to see whether raw pre-entry scores
show monotonic or slice-stable label separation across deterministic bands
before any deeper model training or threshold experiment.

The unique-signal probability-band diagnostic then completed:

- It extended each feature group's `unique_signal_descriptive_evaluation` with
  `probability_band_diagnostics`.
- Band policy is global rank tertiles only. Bands are assigned by deterministic
  `(probability, signal_key)` ordering over scored unique signals, then reused
  for per-slice summaries. There is no band choice, threshold search, replay
  mutation, broker/KIS path, credential read, report family, scheduler,
  dashboard, durable worker, or promotion semantic.
- Claude drift-check completed and advised tertiles only, global edges, and
  descriptive naming. Engine Research, Execution/Review, and Data/Infra
  sidecars agreed to keep this inside the existing helper/job payload.
- Focused tests cover incomplete signal-key skips, deterministic reversed-order
  band assignment, degenerate tied-probability skips, source separation, and
  existing artifact/path guards.
- Docker `research` PyTorch CUDA ran once on NVIDIA GeForce RTX 4090 and wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-probability-bands-cross-slice-20260717-r1\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-probability-bands-cross-slice-20260717-r1\feature_input_ablation.pt`.
- The run used `659` diagnostic rows, `256` scored unique signals, zero missing
  signal keys, zero mixed-label signals, and preserved `592` upstream
  `source: local_paper` fills as evidence only.
- Raw pre-entry unique-signal adverse/no-lift rates by global tertile were
  `0.488372`, `0.517647`, and `0.694118`, with high-tertile lift `1.225477`
  versus the overall unique rate `0.566406`.
- Raw pre-entry high-tertile rates by slice were `0.676471` on `src_adbe`,
  `0.625000` on `hold_aem`, and `0.777778` on `hold_amat`. Baseline
  probability-meta tertiles were flat, and combined raw-plus-probability
  tertiles were not monotonic.
- Read this as descriptive in-sample ranking evidence only. It does not select
  a trading band or threshold.

Next, add a bounded raw pre-entry band feature-attribution diagnostic. The goal
is to explain which raw pre-entry features characterize the high adverse/no-lift
tertile across slices before any deeper training, threshold experiment, or
replay change.

The raw pre-entry band feature-attribution diagnostic then completed:

- It extended the existing `candidate_feature_input_ablation` payload with
  `raw_pre_entry_band_attribution` under raw-feature groups'
  `unique_signal_descriptive_evaluation`.
- Attribution reuses the same unique-signal collapse and global probability
  tertile assignment as `probability_band_diagnostics`, excludes incomplete
  signal keys, skips mixed-label signals, summarizes only the fixed raw
  pre-entry feature names, and excludes missing raw feature values from summary
  statistics instead of treating imputed zeros as observations.
- Claude drift-check returned "no drift" and warned to keep this descriptive,
  bounded to fixed raw features, and away from threshold/rule language.
  Engine Research, Infra/Data, and Execution/Review sidecars agreed to keep it
  inside the existing helper/job payload and to run one Docker `research` CUDA
  refresh because the prior artifacts did not persist per-row probabilities
  joined to raw feature values.
- Focused tests cover deterministic reversed-row attribution, incomplete
  signal-key skips, mixed-label signal skips, missing raw feature exclusion,
  source separation, existing selected/full-row behavior, and artifact/path
  guards.
- Docker `research` PyTorch CUDA ran once on NVIDIA GeForce RTX 4090 and wrote:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-raw-band-attribution-cross-slice-20260717-r1\metrics.json`
  and
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-raw-band-attribution-cross-slice-20260717-r1\feature_input_ablation.pt`.
- The run used `659` diagnostic rows, `256` scored unique signals, zero missing
  signal keys, zero mixed-label signals, and preserved `592` upstream
  `source: local_paper` fills as evidence only. All metric rows remained
  `source: diagnostic_overlay`.
- Raw pre-entry adverse/no-lift rates by probability tertile remained
  `0.488372`, `0.517647`, and `0.694118`.
- The high probability tertile had lower pre-entry close-position context than
  the full unique-signal population and the low probability tertile:
  `pre_last_close_position_in_range` high mean `0.118829`, overall mean
  `0.433735`, low mean `0.819891`; high-vs-overall mean delta `-0.314906` and
  high-vs-low mean delta `-0.701062`.
- Other high-vs-low descriptive deltas were `pre_close_return` mean
  `-0.005105`, `pre_high_low_range_pct` mean `-0.000165`, and
  `pre_last_volume_vs_prior_avg` mean `0.422191` with median delta
  `-0.028514`.
- By-slice high-tertile close-position means stayed low:
  `src_adbe=0.164050`, `hold_aem=0.085261`, and `hold_amat=0.091722`.
- Read this as in-sample descriptive input attribution only. It does not choose
  a trading band, feature rule, threshold, replay change, model promotion, or
  order filter.

Next, add a bounded local-paper outcome attribution by raw pre-entry feature
context. The goal is to see how the descriptive high-risk raw feature context
relates to existing broker-free local-paper fills and trade paths before any
new model training, threshold experiment, or replay behavior change.

The raw pre-entry local-paper outcome attribution then completed:

- It added one pure artifact-only helper,
  `raw_pre_entry_outcome_attribution`, without adding a research job kind,
  replay path, scheduler, dashboard, gate, durable worker, broker/KIS path, or
  credential path.
- The helper reconstructs `source: diagnostic_overlay` candidate rows through
  the existing feature-input stability lineage, reads existing event artifacts
  referenced by that lineage, and reuses trade-path attribution for existing
  `source: local_paper` fills and paths.
- Claude drift-check said the scope was not gate drift, but warned this was the
  marginal unit of report sprawl. The implementation kept one compact helper,
  one compact external artifact, explicit missing-evidence counts, raw N beside
  every rate-like view, and no threshold/rule/promotion language.
- Engine Research and Execution/Review sidecars advised exact-key joins,
  timezone normalization, diagnostic/local-paper source separation, and no
  inference from compact selected examples. The implementation joins on exact
  `slice_id`, `variant_id`, `symbol`, and UTC-normalized entry timestamp.
- CPU/artifact-only smoke wrote:
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution\bounded-raw-pre-entry-outcome-attribution-cross-slice-20260717-r1\metrics.json`.
  No Docker or GPU was used for this task.
- The smoke consumed the existing raw-band attribution artifact and the
  cross-slice stability artifact only. It reused existing local Yahoo rows and
  event artifacts, acquired no additional data, and reran no local-paper replay.
- Overall join results: `659` diagnostic observations, `256` unique signals,
  `302` local-paper entry fills, `290` closed local-paper paths, `12` open
  local-paper paths, `0` non-local fill sources, `0` missing local-paper entry
  evidence, and `0` missing trade-path evidence. Closed fee-aware delta sum was
  `-147.8043`; open window gross delta sum was `140.3549658203124`.
- By `pre_last_close_position_in_range` raw-value tertile, closed fee-aware
  deltas were `-48.6654` for low, `-60.4253` for mid, and `-38.7136` for high.
  This does not support turning the earlier low close-position context into an
  execution rule.
- By `pre_last_volume_vs_prior_avg` raw-value tertile, closed fee-aware deltas
  were `-76.1515` for low, `-39.8009` for mid, and `-31.8519` for high. Treat
  this as descriptive and in-sample only because it is still tied to the same
  bounded artifact lineage.
- By pre-entry bucket, `pre_entry_down` had `370` observations, `156`
  local-paper entry fills, `151` closed paths, and closed fee-aware delta
  `-81.1599`; `pre_entry_up` had `288` observations, `146` entry fills, `139`
  closed paths, and closed fee-aware delta `-66.6444`.
- Focused tests cover exact-key joins, source separation, non-local source
  surfacing, missing local-paper entry evidence, deterministic raw-feature
  tertiles, non-diagnostic row exclusion, artifact-root rejection, and import
  guards against broker submit/order-intent/network/credential paths.

The raw pre-entry contract pass then completed:

- It kept the pass to existing helpers and tests. No new research job kind,
  durable worker, scheduler, dashboard, report family, replay path, broker/KIS
  path, credential path, model promotion path, Docker job, or GPU training was
  added.
- `raw_pre_entry_outcome_attribution` now reuses the feature-input
  `UNIQUE_SIGNAL_KEY_FIELDS` contract, imports `LOCAL_PAPER_SOURCE` directly
  from local-paper instead of the execution barrel, and counts unique matched
  local-paper entry keys separately from local-paper fill event rows.
- `trade_path_attribution` also avoids the execution barrel for fill-source
  helpers and local-paper source constants, so importing attribution helpers
  does not load broker modules.
- Raw-band attribution policy now explicitly records `feature_rule: false`.
- Focused tests now cover exact scope/policy contracts, raw outcome not being a
  research job kind, signal-key sharing, exact variant/symbol/UTC entry joins,
  missing local-paper trade-path evidence, missing raw feature exclusion,
  missing top-level artifact reporting, external artifact roots, and import
  guards against broker submit/order-intent/network/credential paths.
- CPU artifact smoke wrote:
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution\bounded-raw-pre-entry-outcome-attribution-contract-smoke-20260717-r1\metrics.json`.
  It consumed only existing raw-band and stability artifacts, used no Docker or
  GPU, acquired no data, and observed `659` diagnostic rows, `302`
  local-paper entry fills, `302` local-paper fill events, `0` missing trade
  paths, and `0` non-local fill sources.
- Runtime Codex sidecars assisted as temporary reviewers: Review checked
  sprawl/naming, Engine Research checked raw feature and key contracts, and
  Infra/Data checked artifact-root, import, Docker, and no-credential
  boundaries. They are not repo-owned workers.

Next, run a bounded parallel-agent research cadence that keeps the single GPU
useful again: use the existing Engine Research Agent and Data Agent single-shot
workers, prefer existing data/artifacts, and avoid adding new workers or job
kinds unless the evidence clearly shows an engine-loop need.

The first bounded parallel-agent research cadence then completed:

- Data Agent ran one metadata-only inventory job:
  `data-agent-market-data-inventory-cadence-20260717-r2`.
  It read existing `D:\market_data` metadata only, acquired no data, wrote
  outside Git under
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-cadence-20260717-r2\metrics.json`,
  and again found `2` known folders, `5` snapshots, and `5` useful files.
- Engine Research Agent ran one queued Docker `research` job:
  `engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1`.
  It used the existing `candidate_feature_branch_replay` job kind, mounted
  current `src` read-only, saw NVIDIA GeForce RTX 4090 in the Docker research
  path, reused the existing entry-adverse depth feature-branch artifact, and
  replayed ADBE/ADI/ADP from the existing `snapshot=2026-06-18` Yahoo 1m data.
- Engine artifacts were written outside Git under
  `D:\thericher-v2\model-artifacts\engine-research-agent`,
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1\metrics.json`,
  and
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-robustness\metrics.json`.
- The short replay completed all `3` slices and `3` threshold pairs, preserved
  local-paper-only evidence, produced `0` fills, `0` non-local fill sources,
  `0` unknown fills, and `0` unreadable event artifacts. Source probability
  evidence was accuracy `0.531780`, loss `0.689288`, max probability
  `0.596555`, and first buy threshold `0.594000`.
- Because this short replay produced no fills and sat at the threshold edge, no
  longer candidate training was queued in this block. Next work should inspect
  the probability/threshold opportunity gap or choose a different bounded
  short GPU experiment before another depth run.
- Runtime Codex sidecars assisted as temporary read-only reviewers: Engine
  Research recommended the short replay shape and a conditional longer idea,
  Data/Infra checked queues, Docker, GPU, roots, and locks, and
  Review/Execution checked no scheduler/broker/order-intent drift. They are
  not repo-owned workers.

Next, diagnose the zero-fill replay opportunity gap from the bounded parallel
cadence before queueing another longer GPU training block. Keep it
artifact-only unless a small existing-job replay is needed to compare a
bounded alternative.

The ADBE/ADI/ADP zero-fill opportunity-gap diagnostic then completed:

- It consumed only existing Engine Research Agent replay, robustness,
  probability trace, status, and Data Agent inventory artifacts. It did not
  rerun local paper, train a model, queue another GPU job, call KIS, read
  credentials, acquire data, or add code.
- The compact artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-opportunity-gap-20260717-r1\metrics.json`.
- The diagnostic counted `708` holdout probability trace rows across ADBE,
  ADI, and ADP. Holdout max probability was `0.562264` versus the minimum
  buy threshold `0.594000`, leaving a `0.031736` gap. There were `0` rows at
  or above any derived buy threshold, `0` near misses within `0.025` below the
  buy thresholds, and `3` rows within `0.050` below them.
- Sell-side context existed (`246` rows at or below sell threshold `0.476`),
  but no buy threshold was reached from a flat position, so the replay emitted
  `0` order intents, `0` events, `0` trades, and `0` local-paper fills.
- Local-paper source evidence stayed clean: `0` non-local fill sources, `0`
  unknown fills, `0` unreadable event artifacts, and `9` missing zero-fill
  event artifacts treated as empty evidence for zero-fill variants.
- Runtime Codex sidecars assisted as temporary read-only reviewers: Engine
  Research independently checked probability/threshold counts, Data/Infra
  checked external roots and path mapping, and Review/Execution checked
  broker, source-label, and multi-agent drift. They are not repo-owned workers.

Next, run a bounded short fill-bearing contrast before another longer GPU
training block: compare the ADBE/ADI/ADP zero-buy evidence against an existing
or newly queued small replay that produces local-paper fills, using only
existing Engine Research/Data single-shot workers and existing job kinds.

The fill-bearing replay contrast then completed:

- It found enough existing evidence and did not queue a new replay, Docker
  job, GPU job, Data Agent job, or longer training block.
- The contrast consumed the ADBE/ADI/ADP zero-buy opportunity-gap artifact and
  the existing AMAT/AMZN/BA fill-bearing replay:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-cadence-depth-amat-amzn-ba-20260717\metrics.json`.
- Both groups used the same `core_plus_entry_adverse_v1` source feature-branch
  artifact, the same `snapshot=2026-06-18` Yahoo 1m data source, and the same
  threshold grid: `0.594/0.476`, `0.595/0.476`, and `0.596/0.476`.
- The compact artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-zero-vs-fill-bearing-contrast-20260717-r1\metrics.json`.
- ADBE/ADI/ADP remained the zero-buy group: `708` trace rows, probability max
  `0.562264`, `0` buy-threshold hits, `0` order intents, `0` events, and
  `0` fills.
- AMAT/AMZN/BA was the fill-bearing group: `348` trace rows, probability max
  `0.935692`, `2` trace rows at or above each buy threshold, `12` order
  intents, `36` events, `12` trades, and `12` fills. AMAT and AMZN carried the
  fills; BA remained zero-fill inside the same replay.
- Fill-source evidence stayed local-paper-only: `fill_source_counts` was
  `{local_paper: 12}`, with `0` non-local fill sources, `0` unknown fills, and
  `0` unreadable event artifacts.
- Important caveat: the fill-bearing replay used `120` bars per slice while
  the zero-buy replay used `240` bars per slice. Treat this as a bounded
  short contrast, not a same-window comparison.
- Runtime Codex sidecars assisted as temporary read-only reviewers: Engine
  Research confirmed the existing fill-bearing candidate, Data/Infra checked
  external roots and local-data lineage, and Review/Execution checked
  local-paper-only and no-coordinator boundaries.

The AMAT/AMZN fill-bearing path-quality attribution then completed:

- It consumed only existing AMAT/AMZN event artifacts, probability traces,
  robustness/replay metrics, and local `snapshot=2026-06-18` Yahoo 1m rows.
  It did not rerun replay, train a model, queue a Docker/GPU job, acquire
  data, call KIS, read credentials, or add code.
- The compact artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-cadence-depth-amat-amzn-path-quality-20260717-r1\metrics.json`.
- The attribution found `6` fill-bearing variants, `12` local-paper fills,
  `6` closed paths, `0` open paths, `0` negative fee-aware paths, and `6`
  non-negative fee-aware paths. Gross delta sum was `40.74`; fee-aware delta
  sum was `40.2807`.
- AMAT contributed `3` closed paths, gross delta `39.405`, fee-aware delta
  `39.0939`, entry probability margins `0.04491384` to `0.04691384`, max
  adverse movement `-4.1200061035156`, and max favorable movement
  `13.7099194335938`.
- AMZN contributed `3` closed paths, gross delta `1.335`, fee-aware delta
  `1.1868`, entry probability margins `0.33969201` to `0.34169201`, max
  adverse movement `-0.16499755859375`, and max favorable movement
  `0.4800067138672`.
- Every sell-threshold signal after entry matched the local-paper sell fill
  timestamp. All original fills stayed `source: local_paper`; diagnostic path
  context stayed `source: diagnostic_overlay`; there were `0` non-local,
  unknown, unreadable, or missing nonzero-fill event artifacts.
- Runtime Codex sidecars assisted as temporary reviewers: Engine Research
  checked path-quality evidence, Data/Infra checked local data and artifact
  lineage, and Review/Execution checked broker/source-label boundaries. They
  are not repo-owned workers.
- Important caveat remains: this AMAT/AMZN/BA replay used `120` bars per slice,
  while the prior ADBE/ADI/ADP zero-buy contrast used `240` bars per slice.

The same-window AMAT/AMZN path-quality consolidation then completed:

- It consumed existing `120`-bar AMAT/AMZN path-quality evidence and existing
  `240`-bar wider-holdout behavior/trade-path/replay artifacts only. It did
  not rerun replay, train a model, queue Docker/GPU work, acquire data, call
  KIS, read credentials, or add code.
- The compact consolidation artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\same-window-amat-amzn-path-quality-consolidation-20260717-r1\metrics.json`.
- Existing `D:\market_data` evidence was sufficient: AMAT had `2340` rows,
  AMZN had `2340` rows, and BA had `2338` rows in
  `snapshot=2026-06-18`.
- The `120`-bar evidence had `6` closed AMAT/AMZN paths, `12` local-paper fill
  events, `0` open paths, `0` negative fee-aware paths, gross delta `40.740`,
  and fee-aware delta `40.2807`.
- The reused `240`-bar evidence had `8` closed AMAT/AMZN paths, `16`
  local-paper fill events, `0` open paths, `2` negative fee-aware AMAT paths,
  gross delta `34.130`, and fee-aware delta `33.4440`.
- The `240` minus `120` descriptive delta was `+2` closed paths, `+4`
  local-paper fill events, `+2` unique entries, `+2` negative fee-aware paths,
  `-6.610` gross delta, and `-6.8367` fee-aware delta.
- AMAT carried the `240`-bar path expansion: `6` closed paths, `12`
  local-paper fill events, `2` negative fee-aware paths, gross delta
  `33.240`, and fee-aware delta `32.6528`. AMZN had `2` closed paths, `4`
  local-paper fill events, `0` negative fee-aware paths, gross delta `0.890`,
  and fee-aware delta `0.7912`.
- Source evidence stayed clean: all `120`-bar and `240`-bar fills were
  `source: local_paper`, non-local source counts were `{}`, unknown fill counts
  were `0`, unreadable event artifacts were `0`, and diagnostic path context
  stayed `source: diagnostic_overlay`.
- No exact files were missing for AMAT/AMZN consolidation. The replay artifacts
  still list `20` missing zero-fill event files for zero-fill symbols/variants;
  those are empty evidence and did not block AMAT/AMZN path attribution.
- Runtime Codex sidecars assisted as read-only reviewers: Engine Research
  verified `240`-bar path evidence, Data/Infra verified local rows and external
  artifact roots, and Review/Execution checked source-label and sprawl
  boundaries. They are not repo-owned workers.
- Remaining caveat: exact threshold-pair parity is not present in the reused
  artifacts. The `120`-bar cadence used `0.594/0.476`, `0.595/0.476`, and
  `0.596/0.476`; the existing `240`-bar wider-holdout artifacts used only
  `0.595/0.476` and `0.596/0.476`.

The AMAT/AMZN/BA `240`-bar threshold-pair parity check then completed:

- No exact three-pair `240`-bar replay existed before this task, so one
  existing Engine Research Agent `candidate_feature_branch_replay` job was
  queued and run once:
  `engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1`.
- The runner used Docker `research` only, mounted current `src` read-only, saw
  NVIDIA GeForce RTX 4090 with `24564` MiB, reused the existing depth
  feature-branch artifact, and replayed AMAT, AMZN, and BA from
  `snapshot=2026-06-18` with `max-bars 240`.
- Replay artifacts were written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1\metrics.json`,
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-robustness\metrics.json`,
  and the Engine Research Agent status artifact under
  `D:\thericher-v2\model-artifacts\engine-research-agent\runs\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1\status.json`.
- The replay used the exact three threshold pairs from the `120`-bar cadence:
  `0.594/0.476`, `0.595/0.476`, and `0.596/0.476`.
- The follow-up path attribution artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-amzn-ba-240bars-20260717-r1-path-attribution\metrics.json`.
- AMAT/AMZN/BA replay produced `24` verified `source: local_paper` fill
  events, `12` closed paths, `0` open paths, gross delta `51.195`, and
  fee-aware delta `50.1660`. Non-local source counts were `{}`, unknown fills
  were `0`, and unreadable event artifacts were `0`.
- AMAT carried `18` local-paper fill events, `9` closed paths, `3` negative
  fee-aware paths, `6` non-negative fee-aware paths, gross delta `49.860`, and
  fee-aware delta `48.9792`.
- AMZN carried `6` local-paper fill events, `3` closed paths, `0` negative
  fee-aware paths, gross delta `1.335`, and fee-aware delta `1.1868`.
- BA remained zero-fill across all three variants. Its three missing event
  files are zero-fill empty evidence, not unreadable nonzero evidence.
- Compared with the prior `120`-bar three-pair evidence, the exact `240`-bar
  replay added `6` closed paths, `12` local-paper fill events, `2` unique
  entries, `3` negative fee-aware paths, gross delta `10.455`, and fee-aware
  delta `9.8853`.
- Compared with the reused `240`-bar two-pair evidence, the exact three-pair
  replay added `4` closed paths, `8` local-paper fill events, `1` negative
  fee-aware path, gross delta `17.065`, and fee-aware delta `16.7220`.
- Diagnostic path and comparison context stayed `source: diagnostic_overlay`
  and created no fills, broker outcomes, execution filters, replay rules,
  feature rules, or model-promotion rules.
- Runtime Codex sidecars assisted as read-only reviewers: Engine Research
  verified the exact replay artifacts and Review/Execution checked broker,
  source-label, and sprawl boundaries. They are not repo-owned workers.

The AMAT negative-path attribution then completed:

- It consumed existing parity replay, robustness, trace, event, path
  attribution, wider-holdout feature-input context, and local AMAT/AMZN Yahoo
  rows only. It did not rerun replay, train a model, queue Docker/GPU work,
  acquire data, call KIS, read credentials, add code, or create a new worker.
- The compact artifact was written outside Git:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-parity-depth-amat-negative-path-attribution-20260717-r1\metrics.json`.
- The `3` negative AMAT paths were one repeated market moment across three
  threshold variants: entry `2026-06-09T16:46:00+00:00`, entry probability
  `1.00000000`, margins `0.404` to `0.406`, two-bar sell-threshold latency,
  gross delta `-3.87`, and fee-aware delta `-4.1532`.
- AMAT non-negative paths were `6` variant rows over `2` unique entries, gross
  delta `53.730`, fee-aware delta `53.1324`, and longer sell-threshold latency
  of `8` to `16` bars. AMZN non-negative paths were `3` rows over one unique
  entry, gross delta `1.335`, and fee-aware delta `1.1868`.
- Existing feature-input context showed one repeated AMAT negative feature
  signature, two AMAT non-negative signatures, and one AMZN non-negative
  signature. The parity probability traces themselves did not retain feature
  payload fields, so this context is explicitly sourced from existing
  wider-holdout behavior attribution by symbol and timestamp.
- Source evidence stayed clean: all `24` parsed fills were
  `source: local_paper`; non-local fills, unknown fills, unreadable event
  artifacts, missing exact source files, missing feature context, and missing
  nonzero event/trace evidence were all `0`. BA still has `3` missing
  zero-fill event artifacts, treated as empty zero-fill evidence.
- Diagnostic context stayed `source: diagnostic_overlay` and created `0`
  local-paper fills, broker outcomes, order intents, execution filters, replay
  rules, feature rules, or model-promotion rules.
- Runtime Codex sidecars assisted as read-only reviewers: Engine Research
  independently checked path, trace, and feature-payload availability, while
  Review/Execution checked broker/source-label/sprawl boundaries. They are not
  repo-owned workers.

Next, run a bounded multi-agent research cadence using the existing Engine
Research and Data single-shot workers plus temporary Codex sidecars. Keep the
single GPU useful through one bounded Docker `research` job if the evidence
supports it, and clarify the remaining role-agent gap without creating a
durable scheduler, daemon, coordinator, or broker-capable worker.

## Daily Operator Review

The operator wants daily review at 08:00 KST. Keep reports to one bundle:

- `reports/daily/YYYY-MM-DD-summary.md`
- `reports/daily/YYYY-MM-DD-metrics.json`
- `reports/daily/YYYY-MM-DD-next-goal.md`

Do not create many status reports.
