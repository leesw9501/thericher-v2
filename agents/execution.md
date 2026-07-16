# Execution Agent

## Engine Loop

- paper trading
- live-risk control
- PnL attribution

## Owns

- Local paper order lifecycle, simulated fills, positions, and cash accounting.
- Broker adapter boundaries, KIS paper/live adapters when explicitly allowed.
- Execution hard stops such as emergency stop, duplicate client order id, and
  risk limits.

## Must Not

- Introduce strategy logic beyond risk checks.
- Call KIS APIs until a future goal explicitly allows it.
- Place paper or live orders until explicitly allowed.
- Read credentials or `.env`.

## Held Resources

- Local emergency state only.

## Active Queue

1. Add source filtering to future replay/query views before real broker fills
   exist.
2. Keep future KIS adapter work separate from local paper simulator behavior.
3. Add more realistic order types only when paper-loop evidence needs them.

## Running Jobs

- None.

## Done Recently

- Local emergency store exists for stop-new-orders and cancel-open-orders
  requests.
- Broker-free local paper simulator now supports accepted/rejected/canceled
  order events, next-bar-open fills, duplicate id rejection, emergency-stop
  blocking, deterministic account replay, and local paper fill metadata.
- Bounded validation now consumes local paper only and keeps fills labeled with
  `source: local_paper`.
- Candidate replay now consumes local paper only and verified generated fills
  remain labeled with `source: local_paper`.
- Candidate replay comparison verified both candidate and momentum baseline
  fills remain labeled with `source: local_paper`.
- Threshold sweep replay verified every variant fill remains labeled with
  `source: local_paper`.
- Threshold robustness replay verified every CVS, FCX, and KO variant fill
  remains labeled with `source: local_paper`.
- Multi-slice candidate robustness replay produced zero fills under the existing
  grid; no non-local fill source was observed.
- Probability-derived calibration robustness replay produced `524` simulated
  fills across CVS, FCX, and KO; every fill source was verified as
  `local_paper`.
- Calibration holdout replay produced `511` simulated fills across CVS, FCX,
  and KO; every fill source was verified as `local_paper`.
- Breadth holdout bridge mini smoke produced `400` simulated fills across three
  candidates and CVS, FCX, and KO holdout slices; every fill source was
  verified as `local_paper`.
- Depth target mini smoke produced `347` simulated fills across CVS, FCX, and
  KO holdout slices; every fill source was verified as `local_paper`.
- Holdout verification now treats missing event files for zero-fill replay
  variants as empty evidence while still requiring readable event artifacts for
  variants that produce fills.
- Depth-vs-breadth comparison reran no execution, preserved existing
  local-paper source verification, and confirmed both compared artifacts report
  all simulated fills as `local_paper`.
- Fill-aware threshold rerun replayed stricter threshold variants through the
  local-paper path and produced zero fills, with no non-local fill source.

## Next Handoff

- Future replay must filter `source: local_paper` before broker fills are
  introduced.
