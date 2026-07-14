# Data Agent

## Engine Loop

- data collection
- backtest and walk-forward validation

## Owns

- Market data provider interfaces and local/offline providers.
- Local cache layout, calendars, symbol metadata, and resampling.
- Data-quality warnings that help research without blocking iteration.

## Must Not

- Call KIS APIs until a future goal explicitly allows it.
- Read credentials or `.env`.
- Create research-blocking gates for non-execution data warnings.
- Import v1 data modules wholesale.

## Held Resources

- Local repo data path is ignored by Git under `/data/`.

## Active Queue

1. Add data-quality checks for missing bars, duplicate bars, and incomplete
   higher timeframe buckets.
2. Decide the first local cache shape only when real ingestion work starts.

## Running Jobs

- None.

## Done Recently

- Added provider protocol, local CSV provider, sample provider, and deterministic
  timeframe resampling.

## Next Handoff

- Keep data-quality checks as warnings until execution hard stops need them.
