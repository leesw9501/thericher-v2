# Vision

## Mission

TheRicher v2 helps one Korea-based operator build, validate, and operate
short-term automated trading engines for US and Korean equities through KIS.

The center of the product is a repeatable loop:

1. Collect intraday market data.
2. Build features and candidate models.
3. Backtest and walk-forward validate with realistic costs.
4. Run KIS paper trading.
5. Attribute wins, losses, slippage, and model decisions.
6. Promote only robust engines to small live capital.

KIS paper trading is an early source of live-like execution evidence, not a
prize reserved for a profitable model. A deterministic baseline may enter a
bounded paper loop once execution hard stops work, while model research
continues independently.

## Why v2 Exists

v1 became too focused on readiness packets, gates, handoffs, and operator
reports. It created safety evidence faster than it advanced the actual trading
engine. v2 keeps the useful lessons but cuts the process layer down to the
minimum needed for research velocity and live-risk control.

## North Star

The engine must improve faster than the documents grow.

The operating north star is independent live-like evidence produced per hour of
operator attention.

Success is measured by:

- number of valid strategy experiments completed,
- quality of walk-forward and paper trading evidence,
- speed from idea to backtest to paper loop,
- clarity of PnL attribution,
- ability to stop trading immediately,
- absence of accidental live orders.

Model count, commit count, artifact count, and GPU utilization are not success
metrics by themselves.

## Market Scope

- Phase 1 paper target: US equities through KIS paper trading.
- Parallel research: Korean equities data and backtests.
- Long-term: one market-neutral engine interface with market-specific adapters
  for currency, calendar, fees, taxes, order rules, and tick size.

## Capital Philosophy

Live trading starts small even if paper trading performs well.

The initial live capital planning target is KRW 5,000,000, but the first live
deployment should use a staged ramp below that cap until real slippage, spread,
latency, and operational behavior are measured.
