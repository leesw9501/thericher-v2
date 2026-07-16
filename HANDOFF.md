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
- local-paper holdout source verification now treats missing event files for
  zero-fill replay variants as empty evidence rather than a non-local fill
  failure, while still failing unreadable artifacts for variants with fills,
- agent lane stateboards under `agents/`,
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

- `244 passed`
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
- Agent stateboards are lane queues only; `NEXT_CODEX_GOAL.md` remains the
  single next objective.
- First paper execution target is US equities through KIS.
- Korean equities are research/data-parallel at first.

## Recommended Next Slice

Start one bounded entry-adverse hidden8 loss-attribution diagnostic:

1. consume the completed hidden8 feature-branch, replay, opportunity,
   trade-path, contrast summary, trace, and selected local-bar evidence,
2. explain why hidden8 produced only AMAT entries and why both closed segments
   were fee-aware negative,
3. compare hidden8 AMAT signal/path evidence against the hidden4 wide-sample
   AMAT evidence without rerunning replay,
4. write one compact external diagnostic artifact with no hidden-unit ranking,
   branch selection, threshold search, retraining, replay rerun, dashboards,
   schedulers, broker behavior, or report/gate expansion.

Do not start with a dashboard expansion, KIS credentials, or broker submit.

## Daily Operator Review

The operator wants daily review at 08:00 KST. Keep reports to one bundle:

- `reports/daily/YYYY-MM-DD-summary.md`
- `reports/daily/YYYY-MM-DD-metrics.json`
- `reports/daily/YYYY-MM-DD-next-goal.md`

Do not create many status reports.
