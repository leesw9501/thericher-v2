# Execution Agent

## Status

- Broker-free execution readiness is active.
- The KIS adapter is disabled.
- No KIS, credential, account, order, or capital authority exists.
- External paper and live execution remain unavailable.

## Engine Loop

- Paper trading.
- Live-risk control.
- PnL attribution through deterministic fill and account reconciliation.

## Owns

- Deterministic order lifecycle, fills, positions, cash, buying power, open
  orders, cancellation, and account reconciliation.
- Execution risk limits, idempotency, emergency stops, and fail-closed behavior.
- Broker-neutral contracts and broker adapters when separately authorized.
- Local broker-free simulation with fills labeled `source: local_paper`.

## Must Not

- Call KIS or any external broker, read credentials, or discover account data
  without explicit operator authority.
- Submit, cancel, replace, or query real external paper or live orders under the
  current authority.
- Load public model code into execution paths.
- Add strategy, feature, threshold, model-promotion, or profitability logic
  beyond deterministic execution risk checks.
- Treat research diagnostics, model profitability, or replay output as broker
  authority.

## Resources

- Existing broker-free simulator and `source: local_paper` event evidence.
- Existing local emergency-stop state and deterministic account replay.
- Existing disabled broker boundary with unavailable KIS capabilities.
- No held credentials, KIS sessions, account identifiers, or approved capital.

## Current Objective

- Define typed broker-neutral account, buying-power, order, partial-fill,
  cancel, open-order, and reconciliation contracts for the disabled boundary.
- Prove those contracts with deterministic fake-transport tests only.
- Keep all production KIS transport and credential paths disabled.

## Ready Queue

1. Define typed account and buying-power snapshots with timestamps, currency,
   settled cash, available cash, exposure, and explicit unavailable states.
2. Define order request, acknowledgement, rejection, partial-fill, fill,
   cancel, and terminal-state contracts with stable client and broker ids.
3. Define typed open-order and reconciliation results for positions, cash,
   fills, duplicate events, stale snapshots, and mismatches.
4. Add fake-transport tests for partial fills, repeated events, cancel races,
   unknown orders, restart recovery, and reconciliation failure.
5. Verify local simulation continues to emit `source: local_paper` and cannot
   select a KIS transport.

## Running

- None.

## Durable Knowledge

- Execution correctness is deterministic: identical ordered inputs must produce
  identical order, account, risk, and reconciliation state.
- Reconciliation is an execution responsibility and must fail closed on stale,
  incomplete, contradictory, or unrecognized broker state.
- Broker-facing types must represent partial success and unavailable data; they
  must not collapse uncertainty into a successful result.
- Model and strategy code remain outside execution. Execution may consume only
  explicit typed intents after independent risk validation.
- `local_paper` is the source label for broker-free simulated fills; diagnostics
  are not fills and must not be relabeled as local paper.
- KIS paper is an early execution milestone measured independently of strategy
  profitability. Profitability neither grants nor blocks broker authority.

## Recovery

- Rebuild state from typed account, position, open-order, fill, and cancel
  snapshots before accepting any new intent.
- Reconcile by stable ids and event ordering; repeated events must be
  idempotent and missing or conflicting state must stop new orders.
- Preserve emergency-stop state across restart and surface unresolved orders or
  account mismatches for operator review.
- Current recovery stops at fake transport or `local_paper`, never KIS.

## Recent Evidence

- The local simulator deterministically covers accept, reject, cancel,
  duplicate-id, and next-bar-fill behavior.
- Fill-source checks preserve simulated fills as `source: local_paper` and
  separate diagnostic evidence from execution events.
- The disabled broker boundary returns typed unavailable outcomes, and tests
  demonstrate no network, credential, broker-submit, or broker-event writes.

## Next Handoff

- Implement only the typed readiness contracts and fake-transport tests in the
  ready queue; do not add a working KIS transport or credential access.
- Keep the KIS adapter disabled and preserve `source: local_paper` in local
  simulation.
- A later read-only KIS authority decision and a later KIS paper-capital
  approval are separate operator decisions.
- KIS paper remains an early milestone independent of model profitability;
  deterministic risk and reconciliation are its acceptance criteria.
