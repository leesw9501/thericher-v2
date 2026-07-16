# Data Agent

## Engine Loop

- data collection
- backtest and walk-forward validation

## Owns

- Market data provider interfaces and local/offline providers.
- Local cache layout, calendars, symbol metadata, and resampling.
- Data-quality warnings that help research without blocking iteration.
- Inventory and reuse of operator-provided data under `D:\market_data`.
- No-auth public data acquisition when it directly improves research or paper
  simulation.

## Must Not

- Call KIS APIs until a future goal explicitly allows it.
- Read credentials or `.env`.
- Scrape login-gated, paid, or license-unclear data sources.
- Create research-blocking gates for non-execution data warnings.
- Import v1 data modules wholesale.

## Held Resources

- Local repo data path is ignored by Git under `/data/`.
- Operator-provided market data root: `D:\market_data`.
- Known top-level folders: `pit_sources`, `us_equities`.
- Data Agent artifact root:
  `D:\thericher-v2\model-artifacts\data-agent`.

## Active Queue

1. Use the single-shot Data Agent runner for bounded inventory refreshes over
   existing `D:\market_data` before adding acquisition.
2. Keep reviewing new Docker `research` artifacts for compact source-slice
   context, but do not turn data warnings into research gates.
3. Acquire additional no-auth public data only when the source is lawful,
   license-compatible, and useful for the current engine loop.
4. Decide the first local cache shape only when real ingestion work starts.

## Running Jobs

- None.

## Operator Help Needed

- None now. If no-auth public acquisition is exhausted, list the exact symbols,
  date ranges, markets, and preferred formats needed here.

## Done Recently

- Added provider protocol, local CSV provider, sample provider, and deterministic
  timeframe resampling.
- Inventoried `D:\market_data` at the shallow level for this goal. Top-level
  folders include `pit_sources` and `us_equities`; no additional download was
  needed for the broker-free local paper simulator.
- Confirmed useful US equity Yahoo intraday snapshots under
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`,
  including the explicit FCX smoke input used by validation.
- Reused the FCX Yahoo intraday snapshot explicitly for the bounded experiment
  queue; no additional data was acquired.
- Reused the same explicit FCX snapshot for walk-forward smoke; no additional
  data was acquired.
- Bounded GPU candidate training used deterministic sample bars; no additional
  data was acquired.
- Bounded candidate evaluation used held-out deterministic sample bars; no
  additional data was acquired. Shallow inventory still shows Yahoo intraday
  snapshots under
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
- Bounded candidate replay reused the explicit CVS Yahoo intraday snapshot at
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0-8d-probe\ohlcv_1m.csv.gz`;
  no additional data was acquired.
- Bounded candidate replay comparison reused the same CVS Yahoo intraday
  snapshot; no additional data was acquired.
- Bounded threshold sweep reused the same CVS Yahoo intraday snapshot; no
  additional data was acquired.
- Bounded threshold robustness inventoried the local Yahoo intraday starter
  subset. Useful snapshots found:
  `snapshot=2026-06-18` with 250 symbols from 2026-06-09 to 2026-06-16, and
  `snapshot=2026-07-09-shadow-t0-8d-probe` with CVS, FCX, and KO from
  2026-06-29 to 2026-07-09. The robustness smoke reused CVS, FCX, and KO; no
  additional data was acquired.
- Bounded multi-slice training reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; no additional data was acquired.
- Bounded probability calibration reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; no additional data was acquired.
- Bounded calibration holdout confirmed CVS, FCX, and KO exist in
  `snapshot=2026-06-18` with about 2,339 to 2,340 bars each; no additional data
  was acquired.
- Bounded candidate breadth queue reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; no additional data was acquired.
- Bounded breadth holdout bridge reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for source calibration and
  `snapshot=2026-06-18` for disjoint holdout replay; no additional data was
  acquired.
- Bounded depth target reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for deeper training/evaluation and
  `snapshot=2026-06-18` for disjoint holdout replay; no additional data was
  acquired.
- Bounded depth-vs-breadth comparison consumed existing external artifacts only
  and did not require additional market-data reads or acquisition.
- Bounded fill-aware threshold rerun reused existing CVS, FCX, and KO holdout
  Yahoo snapshots plus existing probability traces; no additional data was
  acquired.
- Bounded zero-fill threshold attribution consumed existing external rerun,
  robustness, calibration, and probability trace artifacts; no additional data
  was acquired.
- Bounded attribution-informed threshold band rerun reused existing CVS, FCX,
  and KO holdout Yahoo snapshots plus existing probability traces; no
  additional data was acquired.
- Bounded feature/model branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` plus existing external threshold
  band artifacts; no additional data was acquired.
- Bounded feature-branch replay reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` plus existing external feature
  branch artifacts; no additional data was acquired.
- Broker-boundary fuse work required no market data reads or acquisition.
- Longer bounded GPU feature/model validation reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; no additional data was acquired.
- Added warning-only `Bar` data-quality checks. A 240-bar CVS/FCX/KO smoke on
  `snapshot=2026-07-09-shadow-t0-8d-probe` found only incomplete resample
  bucket warnings and no duplicate, non-monotonic, or missing 1m interval
  warnings.
- Threaded compact, warning-only quality summaries into candidate
  training/evaluation local Yahoo source-slice artifacts. Deterministic sample
  runs still omit source slices, and unavailable config placeholders remain
  non-blocking.
- Confirmed new Docker `research` training/evaluation artifacts record compact
  `source_slices[].data_quality` for CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; no additional data was acquired.
- Calibration runtime probes reused the same CVS, FCX, and KO local Yahoo
  snapshot; no additional data was acquired.
- Cap-limited calibration holdout reused disjoint CVS, FCX, and KO data from
  `snapshot=2026-06-18`; no additional data was acquired.
- Bar-pressure feature branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training/evaluation and
  disjoint CVS, FCX, and KO from `snapshot=2026-06-18` for cap-2 holdout
  replay; no additional data was acquired.
- Hidden-units model-axis branch reused the same CVS, FCX, and KO source and
  disjoint holdout snapshots; no additional data was acquired.
- Hidden-units contrast branch reused the same CVS, FCX, and KO source and
  disjoint holdout snapshots; no additional data was acquired.
- Feature-branch replay derivation guard reused the hidden4
  `core_plus_bar_pressure_v1` artifact and disjoint CVS, FCX, and KO holdout
  snapshots from `snapshot=2026-06-18`; no additional data was acquired.
- Feature-branch replay opportunity attribution consumed existing guarded
  replay, threshold robustness, and probability trace artifacts for CVS, FCX,
  and KO holdout slices; no additional data was acquired.
- Regularization model-axis branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training/evaluation and
  disjoint CVS, FCX, and KO from `snapshot=2026-06-18` for cap-2 holdout
  replay and opportunity attribution; no additional data was acquired.
- Feature-normalization branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training/evaluation and
  disjoint CVS, FCX, and KO from `snapshot=2026-06-18` for cap-2 holdout
  replay and opportunity attribution; no additional data was acquired.
- Source-vs-holdout probability alignment consumed existing standardized
  feature-branch replay, robustness, probability trace, and attribution
  artifacts only; no additional data was acquired.
- Disjoint-evaluation feature branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training and CVS, FCX, and KO
  from `snapshot=2026-06-18` for evaluation/replay; no additional data was
  acquired.
- Out-of-symbol replay probe inventoried only the existing
  `snapshot=2026-06-18` Yahoo 1m file, found 250 symbols with 245 eligible
  after excluding CVS, FCX, and KO, selected AAPL, ABNB, ABT, ACN, and ABBV
  with at least 120 rows each, and acquired no additional data.
- Out-of-symbol loss attribution consumed existing external artifacts only and
  required no new market-data reads or acquisition.
- Out-of-symbol fill-lifecycle attribution read only selected AAPL, ABNB, ACN,
  and ABBV rows from the existing `snapshot=2026-06-18` Yahoo 1m file for
  fill-bearing variants; no additional data was acquired.
- Out-of-symbol post-entry exit-signal attribution consumed existing trace and
  lifecycle artifacts only; no additional data was acquired.
- Out-of-symbol exit-horizon diagnostic overlay read selected ABNB and ACN rows
  from the existing `snapshot=2026-06-18` Yahoo 1m file for open segments; no
  additional data was acquired.
- Longer-window out-of-symbol replay reused AAPL, ABNB, ABT, ACN, and ABBV from
  `snapshot=2026-06-18` with `max-bars 240`; no additional data was acquired.
- Longer-window trade-path attribution read selected ABNB, ACN, and ABBV bars
  from the existing `snapshot=2026-06-18` Yahoo 1m file; no additional data was
  acquired.
- Trade-path attribution helper takes provided `Bar` inputs and does not load
  market data itself; focused tests use in-memory/local temp bars only.
- Out-of-symbol evaluation feature-branch training reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe`; evaluation, replay, opportunity
  attribution, and trade-path attribution reused AAPL, ABNB, ABT, ACN, and ABBV
  from `snapshot=2026-06-18` with `max-bars 240`. No additional data was
  acquired. Compact data-quality summaries remained warning-only; ABNB carried
  one missing 1m interval warning plus incomplete resample bucket warnings.
- Entry-quality diagnostic reused the same AAPL, ABNB, ABT, ACN, and ABBV
  `snapshot=2026-06-18` rows plus existing probability traces and event
  artifacts. No additional data was acquired.
- Entry-adverse feature branch reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training, and AAPL, ABNB, ABT,
  ACN, and ABBV from `snapshot=2026-06-18` for evaluation, replay, trade-path,
  and entry-quality attribution. No additional data was acquired.
- Feature-branch comparison consumed existing external artifacts only and
  acquired no additional market data.
- Entry-adverse segment contrast consumed existing external artifacts plus
  selected AAPL, ABNB, and ACN rows from `snapshot=2026-06-18`; no additional
  data was acquired.
- Wider entry-adverse replay inventoried the existing `snapshot=2026-06-18`
  Yahoo 1m file, found `250` total symbols and `240` eligible symbols after
  excluding source/prior replay symbols, selected ADBE, ADI, ADP, AEM, AGG,
  AMAT, AMD, AMGN, AMT, and AMZN, and acquired no additional data.
- Wider entry-adverse signal-quality diagnostic reused the same selected local
  Yahoo rows plus external trace and attribution artifacts; no additional data
  was acquired.
- Entry-adverse hidden-units contrast reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training, and ADBE, ADI, ADP,
  AEM, AGG, and AMAT from `snapshot=2026-06-18` for evaluation/replay; no
  additional data was acquired.
- Hidden8 loss attribution reused the hidden8 external artifacts and selected
  AMAT rows from `snapshot=2026-06-18`; no additional data was acquired.
- Entry-adverse weight-decay contrast reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training, and ADBE, ADI, ADP,
  AEM, AGG, and AMAT from `snapshot=2026-06-18` for evaluation/replay; no
  additional data was acquired.
- Weight-decay wider-sample completion reused AMD, AMGN, AMT, and AMZN from
  `snapshot=2026-06-18` for replay and zero-fill attribution; no additional
  data was acquired.
- Lighter weight-decay contrast reused CVS, FCX, and KO from
  `snapshot=2026-07-09-shadow-t0-8d-probe` for training, ADBE, ADI, ADP, AEM,
  AGG, and AMAT from `snapshot=2026-06-18` for first-six evaluation/replay,
  and AMD, AMGN, AMT, and AMZN from `snapshot=2026-06-18` for wider-sample
  replay; no additional data was acquired.
- Regularization trace-collapse diagnostic consumed existing external
  artifacts only and acquired no additional market data.
- Feature-input concentration diagnostic reused existing probability traces and
  selected `snapshot=2026-06-18` local Yahoo rows; no additional data was
  acquired.
- Source-breadth contrast reused ADBE, ADI, ADP, AEM, AGG, AMAT, AMD, AMGN,
  AMT, and AMZN rows from `snapshot=2026-06-18`; no additional data was
  acquired.
- Source-breadth AMGN loss attribution reused selected AMGN rows from
  `snapshot=2026-06-18` plus existing external artifacts; no additional data
  was acquired.
- Signal-hygiene diagnostic consumed existing external artifacts only and
  required no additional market-data reads or acquisition.
- Sell-latency attribution consumed existing external artifacts only and
  required no additional market-data reads or acquisition.
- Exit-timing diagnostic overlay reused selected rows from the existing
  `snapshot=2026-06-18` Yahoo data plus external artifacts; no additional data
  was acquired.
- Exit-policy sketch consumed existing external artifacts only and required no
  market-data reads or acquisition.
- Diagnostic exit-overlay helper added no market-data loader and consumes only
  provided `Bar` inputs in tests.
- Diagnostic exit-overlay helper smoke reused selected
  `snapshot=2026-06-18` Yahoo rows for ADBE, ADI, ADP, AMAT, and AMGN; no
  additional data was acquired.
- Conditional exit-overlay contrast consumed existing external artifacts and
  reused the same selected local Yahoo rows; no additional data was acquired.
- Exit-latency composite diagnostic consumed existing external artifacts and
  did not require additional market-data reads or acquisition.
- Diagnostic exit-composite helper added no market-data loader and consumes
  provided payloads only in focused tests.
- Diagnostic exit-composite helper smoke consumed existing external artifacts
  only and acquired no additional market data.
- Research-only exit-latency sandbox helper added no market-data loader and
  consumes provided `Bar` inputs only in focused tests.
- Exit-latency sandbox helper smoke reused selected ADBE, ADI, ADP, AEM, AMAT,
  and AMGN rows from `snapshot=2026-06-18`, loaded `1560` bars total, and
  acquired no additional data.
- Fixed entry-adverse GPU validation inventoried `snapshot=2026-06-18`, found
  `230` eligible symbols after prior exclusions, selected ANET, APH, APO, APP,
  ASML, and AVGO for evaluation, reused ADBE, ADI, ADP, AEM, AGG, and AMAT for
  source training, and acquired no additional data.
- Longer-depth entry-adverse contrast reused the same `snapshot=2026-06-18`
  source and evaluation split, loaded 240 bars each for ADBE, ADI, ADP, AEM,
  AGG, AMAT, ANET, APH, APO, APP, ASML, and AVGO through existing Docker
  research paths, and acquired no additional data.
- Short-vs-depth APH signal/path attribution reused existing APH probability
  traces, local-paper event artifacts, and 240 APH bars from
  `snapshot=2026-06-18`; no additional data was acquired.
- Second-holdout replay contrast inventoried only the existing
  `snapshot=2026-06-18` Yahoo 1m file, found `236` symbols with at least 240
  rows after excluding ADBE, ADI, ADP, AEM, AGG, AMAT, ANET, APH, APO, APP,
  ASML, and AVGO, selected AAPL, ABBV, ABNB, ABT, ACN, and AMD, and acquired
  no additional data.
- First-evaluation source-context contrast reused ANET, APH, APO, APP, ASML,
  AVGO, AAPL, ABBV, ABNB, ABT, ACN, and AMD from the existing
  `snapshot=2026-06-18` Yahoo file. The attempted 12-source context was not
  run because the existing research job caps training data slices at `6`; no
  additional data was acquired.
- AMD segment-quality diagnostic reused selected AMD rows from the existing
  `snapshot=2026-06-18` Yahoo file plus existing external trace/event
  artifacts; no additional data was acquired.
- AMD entry feature-input diagnostic reused the same selected AMD rows plus
  existing external trace and segment-quality artifacts; no additional data was
  acquired.
- AMD entry-filter diagnostic overlay reused selected AMD rows from the
  existing `snapshot=2026-06-18` Yahoo file, found all requested selected
  timestamps, and acquired no additional data.
- Cross-sample entry-filter overlay reused selected ADBE, ADI, ADP, AEM, AMAT,
  AMD, AMGN, AMT, and AMZN rows from the existing `snapshot=2026-06-18` Yahoo
  file, found all requested selected timestamps, and acquired no additional
  data.
- First-evaluation source-context depth contrast reused ANET, APH, APO, APP,
  ASML, AVGO, AAPL, ABBV, ABNB, ABT, ACN, and AMD rows from the existing
  `snapshot=2026-06-18` Yahoo file with `max-bars 240`; no additional data was
  acquired.
- First-evaluation wider-holdout contrast inventoried only the existing
  `snapshot=2026-06-18` Yahoo 1m file, found `236` eligible symbols after the
  fixed source/evaluation exclusions, selected ADBE, ADI, ADP, AEM, AGG, AMAT,
  AMGN, AMT, AMZN, AXP, AZN, and BA with at least `240` bars, and acquired no
  additional data.
- Wider-holdout depth behavior attribution reused selected ADBE, ADI, ADP,
  AEM, AGG, AMAT, AMGN, AMT, AMZN, AXP, AZN, and BA rows from the existing
  `snapshot=2026-06-18` Yahoo file to reconstruct feature inputs and
  near-threshold rows; no additional data was acquired.
- Engine Research Agent runner smoke used Docker `research`
  `gpu_training_smoke` only, read no market-data slices, and acquired no
  additional data.
- Engine Research Agent queued feature replay reused AXP, AZN, and BA rows from
  the existing
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`;
  no additional data was acquired.
- Runner-queued zero-fill attribution reused existing AXP, AZN, and BA
  probability trace artifacts plus the same `snapshot=2026-06-18` Yahoo rows
  indirectly through those traces; no additional data was acquired.
- Data Agent worker `data-agent-market-data-inventory-20260717` claimed one
  external queued `market_data_inventory` job, read existing `D:\market_data`
  metadata only, used bounded head samples for known files, found `2` known
  folders, `5` snapshots, and `5` useful files, and wrote artifacts under
  `D:\thericher-v2\model-artifacts\data-agent`. No data was acquired.
- Data Agent cadence refresh `data-agent-market-data-inventory-cadence-20260717`
  claimed one external queued inventory job, again found `2` known folders,
  `5` snapshots, and `5` useful files under existing `D:\market_data`, wrote
  under `D:\thericher-v2\model-artifacts\data-agent`, and acquired no data.
- Data Agent companion refresh
  `data-agent-market-data-inventory-depthjob-20260717-r1` claimed one external
  queued inventory job before the runner-queued depth attempt, again found `2`
  known folders, `5` snapshots, and `5` useful files under existing
  `D:\market_data`, wrote under
  `D:\thericher-v2\model-artifacts\data-agent`, and acquired no data.
- Data Agent companion refresh
  `data-agent-market-data-inventory-explicit-depth-20260717-r1` claimed one
  external queued inventory job before the explicit-slice depth target, again
  found `2` known folders, `5` snapshots, and `5` useful files under existing
  `D:\market_data`, wrote under
  `D:\thericher-v2\model-artifacts\data-agent`, and acquired no data. The
  Engine job reused ADBE, ADI, ADP, AEM, AGG, and AMAT from the existing
  `snapshot=2026-06-18` Yahoo 1m file.
- Explicit-slice depth attribution consumed existing external research
  artifacts only and did not read additional market-data rows or acquire new
  data. Its next data need is selected AMAT/AEM local Yahoo rows only if
  trade-path reconstruction requires bar context.
- AMAT/AEM trade-path diagnostic reused selected AEM and AMAT rows from the
  existing `snapshot=2026-06-18` Yahoo 1m file and acquired no additional data.
- AMAT/AEM replay-shape overlay reused the same selected AEM and AMAT local
  Yahoo rows plus existing external artifacts and acquired no additional data.
- Held-out/context overlay reused selected AGG, ADBE, and ADI rows from the
  existing `snapshot=2026-06-18` Yahoo 1m file and acquired no additional data.
- ADI/AGG driver attribution reused selected ADI and AGG rows from the existing
  `snapshot=2026-06-18` Yahoo 1m file and acquired no additional data.
- ADI/AGG feature-input diagnostic reused selected ADI and AGG rows from the
  existing `snapshot=2026-06-18` Yahoo 1m file and acquired no additional data.
- Cross-slice feature-input stability check reused selected ADBE, AEM, and AMAT
  rows from the existing `snapshot=2026-06-18` Yahoo 1m file plus existing
  external trace/event artifacts and acquired no additional data.
- Bounded feature-input ablation consumed only the existing external
  cross-slice stability artifact and acquired no additional data.
- Full-row feature-input ablation reused the same existing
  `snapshot=2026-06-18` Yahoo 1m rows through stability lineage and acquired no
  additional data.
- Slice-aware feature-input evaluation reused the existing full-row stability
  lineage and `D:\market_data` Yahoo rows indirectly through reconstructed
  diagnostic rows. It acquired no additional data.
- Unique-signal feature-input evaluation reused the same existing stability
  lineage and local Yahoo evidence. It acquired no additional data.
- Unique-signal probability-band diagnostic reused the same existing stability
  lineage and local Yahoo evidence. It acquired no additional data.
- Raw pre-entry band attribution reused the same stability lineage and local
  Yahoo evidence through the existing feature-input ablation reconstruction. It
  acquired no additional data and wrote only external artifacts under
  `D:\thericher-v2\model-artifacts\feature-input-ablation`.
- Raw pre-entry local-paper outcome attribution reused existing raw-band,
  stability, local Yahoo, and local-paper event artifacts only. It acquired no
  additional data and wrote one external artifact under
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution`.
- Raw pre-entry contract tightening consumed existing external raw-band,
  raw-outcome, stability, event, and local Yahoo lineage only. It acquired no
  additional data and wrote one CPU smoke artifact outside Git under
  `D:\thericher-v2\model-artifacts\raw-pre-entry-outcome-attribution\bounded-raw-pre-entry-outcome-attribution-contract-smoke-20260717-r1`.
- Data Agent cadence refresh `data-agent-market-data-inventory-cadence-20260717-r2`
  claimed one external queued inventory job beside the Engine Research Agent
  replay, read existing `D:\market_data` metadata only, again found `2` known
  folders, `5` snapshots, and `5` useful files, wrote under
  `D:\thericher-v2\model-artifacts\data-agent`, and acquired no data.
- Engine Research cadence replay reused ADBE, ADI, and ADP rows from the
  existing
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`;
  no additional data was acquired.
- ADBE/ADI/ADP opportunity-gap diagnostic consumed existing replay and trace
  artifacts only. It did not read additional market-data rows or acquire data;
  the existing `snapshot=2026-06-18` Yahoo 1m evidence was sufficient.
- Fill-bearing contrast reused the existing AMAT, AMZN, and BA replay artifact
  from the same `snapshot=2026-06-18` Yahoo 1m file. No additional data was
  acquired and no new Data Agent inventory was needed.
- AMAT/AMZN path-quality attribution reused the same
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
  file, loaded AMAT and AMZN local rows, consumed existing event/trace
  artifacts, and acquired no additional data. No operator data help is needed
  for this attribution.
- Same-window AMAT/AMZN path-quality consolidation reused the same
  `snapshot=2026-06-18` Yahoo 1m file and existing wider-holdout artifacts.
  It observed AMAT `2340` rows, AMZN `2340` rows, and BA `2338` rows, acquired
  no data, and found no missing exact files for the consolidation.

## Next Handoff

- Keep data-quality checks as warnings until execution hard stops need them.
- The next data task is still not acquisition. Prefer existing `D:\market_data`
  rows for the threshold-pair parity replay/attribution; record exact missing
  artifact names only if existing AMAT/AMZN/BA rows or produced event/trace
  evidence is insufficient.
- Stop acquisition attempts when sources require credentials/payment/manual
  access, licensing is unclear, two consecutive automated attempts fail for the
  same source, or newly acquired data no longer improves the active goal. Record
  the blocker in `Operator Help Needed` and the task completion report.
