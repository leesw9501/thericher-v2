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

## Active Queue

1. Keep reviewing new Docker `research` artifacts for compact source-slice
   quality summaries.
2. Acquire additional no-auth public data only when the source is lawful,
   license-compatible, and useful for the current engine loop.
3. Decide the first local cache shape only when real ingestion work starts.

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

## Next Handoff

- Keep data-quality checks as warnings until execution hard stops need them.
- The next data task is not acquisition; the conditional overlay contrast
  should consume the helper smoke artifact and existing context artifacts.
- Stop acquisition attempts when sources require credentials/payment/manual
  access, licensing is unclear, two consecutive automated attempts fail for the
  same source, or newly acquired data no longer improves the active goal. Record
  the blocker in `Operator Help Needed` and the task completion report.
