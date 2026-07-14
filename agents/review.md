# Review Agent

## Engine Loop

- backtest and walk-forward validation
- paper trading
- live-risk control

## Owns

- Simplicity review and v1-sprawl detection.
- Checks for unnecessary docs, gates, reports, scripts, and workflows.
- Boundary review for credentials, broker calls, live mode, and dashboard
  exposure.

## Must Not

- Own implementation.
- Add review artifacts unless they directly reduce engine risk.
- Block research iteration for warnings that are not execution hard stops.

## Held Resources

- None.

## Active Queue

1. Review local paper execution for hidden broker authority or strategy leakage.
2. Keep agent stateboards short and retire stale ones.

## Running Jobs

- None.

## Done Recently

- Drift checks kept market-data and handoff changes small.

## Next Handoff

- Challenge any new document or workflow that does not improve a named engine
  loop.
