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

## Next Handoff

- Local paper is ready as a validation target for the first bounded model
  experiment. Future replay must filter `source: local_paper` before broker
  fills are introduced.
