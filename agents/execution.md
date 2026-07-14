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

1. Build broker-free local paper execution foundation from existing `Bar` data.
2. Persist order, fill, and position events through the existing event log.
3. Enforce duplicate client order id and emergency stop hard stops.
4. Keep the overnight goal focused on local-only paper execution, not KIS.

## Running Jobs

- None.

## Done Recently

- Local emergency store exists for stop-new-orders and cancel-open-orders
  requests.

## Next Handoff

- Next long task should complete local paper order lifecycle, deterministic
  fills, event persistence, and hard-stop tests.
