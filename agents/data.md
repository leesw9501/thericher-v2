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

## Next Handoff

- Keep data-quality checks as warnings until execution hard stops need them.
- The next data task is not more acquisition; it is keeping quality summaries
  visible while the next model-axis branch reuses existing local snapshots.
- Stop acquisition attempts when sources require credentials/payment/manual
  access, licensing is unclear, two consecutive automated attempts fail for the
  same source, or newly acquired data no longer improves the active goal. Record
  the blocker in `Operator Help Needed` and the task completion report.
