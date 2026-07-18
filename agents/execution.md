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
- The one approved post-diagnosis retry also failed closed, this time as
  `balance_rejected` at `balance` / `VTTS3012R` with HTTP `500`. Its external
  evidence is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-readonly\20260718T095422248003Z-failed_closed.json`
  (SHA-256 `9ee43196ee53305cb62eee5ba582d8f56bce17b2c9f297094abe5f482b4738d8`)
  and contains no snapshot, response text, or response-derived code. This does
  not prove a cause or resolve the earlier open-order issue.
- Existing broker-free fills remain labeled `source: local_paper`; fake broker
  fills use `source: in_memory_broker`.
- The completed offline intraday baseline used isolated local-paper event stores
  for CVS, FCX, and KO across `1m`/`5m`/`10m`/`1h`/`3h`. Each of its 15 cells
  had exactly two `source: local_paper` fills and a flat replayed position. It
  made no KIS call, read no credential, changed no mode, and retained no
  persistent smoke artifact.

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
- The current official `inquire-balance` sample confirms the virtual host, GET
  path, `VTTS3012R`, 8-2 account split, mock `NASD`/`NYSE`/`AMEX` coverage,
  query fields, and continuation shape. Its shared helper always sends
  `tr_cont`, including `""` initially. The reader now does that for every
  allowlisted GET; fake-transport tests prove header emission only. This closes
  a documented deviation, not the balance HTTP `500` cause, and no post-change
  probe was made.
- Data and Review found no market-data, credential, artifact, or process-sprawl
  change in this diagnosis. Claude's `supported-with-limits` review agrees that
  no causal or recovery-success claim is justified.

## Current Objective

- Keep KIS failed closed while the Data lane advances. Do not read `.env`, call
  KIS, submit, modify, cancel, or retry. A later verification requires both the
  non-secret pairing confirmation below and separate one-time authority.

## Recovery

- Read the explicit JSON state file and reload it with
  `InMemoryBrokerTransport.from_state(..., state_path=...)`; the in-memory
  payload must match the persisted bytes.
- Reconcile account, buying power, open orders, and fills before accepting a
  new intent after restart.
- Missing, contradictory, stale, or outcome-unknown evidence fails closed.
- Current recovery stops at the in-memory fake or `local_paper`, never KIS.
- Preserve both failure artifacts. HTTP `500` alone does not establish a TR,
  account-product, funding, or sandbox cause. The documented `tr_cont` header
  deviation is corrected but unproven as a cause. Any future probe requires a
  separately authorized verification path, never an automatic retry.

## Ready Queue

1. Obtain only yes/no confirmation that the app is a distinct virtual-paper
   app, the virtual securities account and Open API service are active, and the
   configured 8-2 pair belongs to that virtual account. Do not request values.
2. If all three are confirmed, draft a separate one-time read-only verification
   request; do not schedule or make a probe.
3. After a complete typed snapshot exists, reconcile it without submit/cancel
   behavior and then propose a paper capital envelope for operator approval.
4. Keep pure risk integration and append-only execution events as later bounded
   steps after capital and submit authority exist.

## Operator Help

- No capital decision is ready. Reply only yes/no, without sharing values: is
  the app a dedicated virtual-paper app; are the virtual securities account and
  Open API service active; and does the configured 8-2 account/product pair
  belong to that virtual account rather than a real account? The paper capital
  envelope remains a later decision after successful reconciliation.

## Must Not

- Read `KIS_LIVE_*`, any unrelated `.env` key, or expose paper secrets/account
  identifiers. Read-only KIS paper network calls are the only allowed KIS use.
- Submit, modify, or cancel an external order; change `THERICHER_MODE`; allocate
  paper capital; or enable live behavior under current authority.
- Add strategy or model-selection logic to execution.
- Relabel fake broker fills as `local_paper`.
