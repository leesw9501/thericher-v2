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

1. Add data-quality checks for missing bars, duplicate bars, and incomplete
   higher timeframe buckets.
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

## Next Handoff

- Keep data-quality checks as warnings until execution hard stops need them.
- Stop acquisition attempts when sources require credentials/payment/manual
  access, licensing is unclear, two consecutive automated attempts fail for the
  same source, or newly acquired data no longer improves the active goal. Record
  the blocker in `Operator Help Needed` and the task completion report.
