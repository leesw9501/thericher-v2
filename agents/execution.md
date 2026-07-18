# Execution Agent

## Status

- Broker-neutral lifecycle readiness is implemented with an offline fake
  transport and an explicit local persistence path.
- KIS submit/live remains disabled. The operator approved `KIS_PAPER_*` for one
  read-only virtual-account discovery while `THERICHER_MODE=off`. The initial
  balance probe failed closed, then the corrected open-order-first discovery
  wrote only
  `D:\thericher-v2\model-artifacts\execution\kis-paper-readonly\20260718T075158554844Z-failed_closed.json`
  with reason `open_orders_rejected`. Neither artifact retains an account
  snapshot, position, cash, orderable-funds, or open-order record.
- Existing broker-free fills remain labeled `source: local_paper`; fake broker
  fills use `source: in_memory_broker`.

## Owns

- Deterministic intent, submit, fill, cancel, open-order, restart, and
  reconciliation behavior.
- Cash, positions, accounting PnL, risk limits, emergency controls, and future
  broker adapters when separately authorized.
- Fail-closed treatment of duplicate, stale, mismatched, or unknown outcomes.

## Current Evidence

- Immutable account, buying-power, order, fill, cancel, open-order, and
  reconciliation contracts use `Decimal` and UTC timestamps.
- `InMemoryBrokerTransport` permits submit only after `record_intent` has been
  atomically persisted as JSON at an explicitly supplied `state_path`.
- Exported state is JSON-safe; persisted bytes reload into a fresh transport
  before a submit retry.
- Open orders can be cancelled. `outcome_unknown` blocks retry even when an ack
  exists. Unchanged outcomes require monotonic status evidence; newly observed
  partial or full fills additionally require unique immutable fill evidence
  whose exact quantity and weighted price match the authoritative status.
- Reconciliation sets `safe_to_submit=False` for duplicate ids, mismatched
  local/external state, stale snapshots, incomplete snapshots, or unknown
  outcomes.
- Authoritative status and fill evidence are persisted atomically and survive a
  fresh restart before clean reconciliation.
- A single immutable pre-submit risk decision now evaluates only the exact
  durably recorded request. It consumes fresh account, buying-power,
  open-order, reconciliation, emergency, count, PnL, position, price, and
  `RiskLimits` evidence without submitting the order.
- Risk decisions use stable fail-closed reason codes and fresh, matching typed
  position evidence. Buys use the conservative reference/limit/market price,
  while long-only sells prove reductions by quantity and never project a
  negative position.
- A proven long reduction may bypass entry-only stops and capacity limits, but
  never durable-intent, account, evidence, open-order, or reconciliation
  integrity checks.
- Local paper keeps exact next-bar continuity for intraday data. Generic D1
  validation accepts a later complete caller-supplied observed bar; exact +1/+2
  dataset-index adjacency is proven by the active campaign, not a calendar
  service. Fill time, open price, and `local_paper` source are unchanged.
- Focused evidence: `tests/test_broker_lifecycle.py` and
  `tests/test_broker_boundary.py` pass together without network or credentials.
- `execution.kis_readonly` is a separate, typed virtual-paper discovery
  boundary. It accepts only the four approved paper `.env` keys, pins the exact
  virtual host, uses injected transport, permits only fixed balance,
  orderable-funds, and open-order reads, and emits redacted external evidence.
  A collected snapshot requires complete paginated open-order evidence; an
  unavailable or partial response fails closed without a synthetic empty view.
  It has no order action path and does not alter the disabled broker adapter or
  `local_paper`.
- `tests/test_kis_readonly.py` proves host/config rejection, fixed request
  allowlisting, no order actions, complete typed open-order parsing, redaction,
  external-only evidence, and fail-closed reconciliation. The focused suite
  passed before the one corrected real discovery attempt.
- Public official samples now confirm the virtual `VTTS3018R` mapping, GET
  query shape, `M`/`F` to `N` continuation, and the US-wide `NASD` behavior of
  `inquire-nccs`. The reader now makes one `NASD` open-order query, accepts
  mixed US venue rows, and emits only fixed endpoint/TR ID plus HTTP status on
  a rejection; it never persists response text or response-derived codes.
- The existing `open_orders_rejected` evidence has no response status or server
  detail, so this is a spec alignment rather than a proven root-cause fix.

## Current Objective

- Run one already approved virtual-paper read-only discovery after the public
  spec alignment. The existing loader may read only its four paper keys; do not
  inspect `.env` manually, read live keys, submit, modify, cancel, or retry.

## Recovery

- Read the explicit JSON state file and reload it with
  `InMemoryBrokerTransport.from_state(..., state_path=...)`; the in-memory
  payload must match the persisted bytes.
- Reconcile account, buying power, open orders, and fills before accepting a
  new intent after restart.
- Missing, contradictory, stale, or outcome-unknown evidence fails closed.
- Current recovery stops at the in-memory fake or `local_paper`, never KIS.
- The next one-time retry must preserve the prior failure artifact and use the
  fixed reader only. If it fails, do not retry; inspect only its redacted
  endpoint/TR ID/HTTP-status metadata before choosing the next action.

## Ready Queue

1. Run one approved, non-secret read-only retry of the corrected virtual-paper
   open-order discovery, then stop regardless of outcome.
2. After a complete typed snapshot exists, reconcile it without submit/cancel
   behavior and then propose a paper capital envelope for operator approval.
3. Keep pure risk integration and append-only execution events as later bounded
   steps after capital and submit authority exist.

## Operator Help

- No capital decision is ready. If the one corrected retry still fails, the
  next non-secret check is whether the virtual Open API app is paired with the
  intended overseas-stock paper account and its product suffix. The paper
  capital envelope remains a later decision after successful reconciliation.

## Must Not

- Read `KIS_LIVE_*`, any unrelated `.env` key, or expose paper secrets/account
  identifiers. Read-only KIS paper network calls are the only allowed KIS use.
- Submit, modify, or cancel an external order; change `THERICHER_MODE`; allocate
  paper capital; or enable live behavior under current authority.
- Add strategy or model-selection logic to execution.
- Relabel fake broker fills as `local_paper`.
