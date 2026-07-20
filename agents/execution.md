# Execution Agent

## Status

- Broker-neutral lifecycle readiness is implemented with an offline fake
  transport and an explicit local persistence path.
- The Docker `kis-readonly` one-shot bridge completed one virtual-paper
  reconciliation at `2026-07-20T07:34:11.455838Z`. It writes a strict,
  five-minute sanitized snapshot to the Docker-local runtime for a
  credential-free web reader and records only counts, currencies, status, and
  a runtime-payload digest in
  `D:\thericher-v2\model-artifacts\execution\kis-paper-console-bridge\20260720T073411455838Z-complete.json`
  (SHA-256 `9b7b12848f28ced98d674ac224d2f576e02df279cf57a581ef5500e9159614fb`).
  No account number, amount, symbol, order reference, credential, or raw broker
  response is retained in that evidence. The initial artifact path check failed
  after the snapshot write because `/app/model_artifacts` is a mounted path
  below `/app`; the mount-aware fix and `--recover-evidence` recorded the
  existing fresh snapshot with no KIS I/O. Recovery is `complete`.
- A bounded 2026-07-19 KIS paper read-only probe now proved that token issuance
  and a `NASD` balance/position response work. Its sanitized account summary is
  `D:\thericher-v2\model-artifacts\execution\kis-paper-account-readonly-probe\20260719T053923268036Z\summary.json`.
  It retained no account values or symbols. `NYSE` balance, open orders, and
  orderable funds returned `EGW00201`, so they remain unresolved rather than
  inferred empty. A separate sanitized market-data probe observed raw unadjusted
  daily and `1m` continuation pages at
  `D:\thericher-v2\model-artifacts\execution\kis-paper-market-data-probe\20260719T054216611479Z\summary.json`.
- The raw-minute client is now isolated to token plus one KIS paper market-data
  endpoint and parses only observed raw fields; it cannot place, change, or
  cancel an order. A bounded client instance reuses one successful token for an
  explicit continuation instead of refreshing it per page. Its first
  implementation incorrectly required market `rt_cd` on the OAuth response;
  corrected HTTP/token-only handling passed a fake test and one bounded
  `QQQ`/`NAS` read of 120 descending raw-minute rows (`19:59` through `18:00`)
  with continuation metadata. Sanitized evidence:
  `D:\thericher-v2\model-artifacts\execution\kis-paper-raw-minute-client-probe\20260719T060205390Z\summary.json`
  (`sha256:81e80a4c7a55e90cfde73e1349e83aa504f5f86589c3c5ac8e0122e4128c6f72`).
  Do not infer qualified timestamp or completed-bar semantics from that one page
  or retry in a loop.
- The official KIS raw-minute sample requires `PINC=0` on a first page,
  `PINC=1` on continuation, and a `KEYB` one exchange-local minute before the
  preceding page's oldest bar. The isolated client now fixes that no-overlap
  request shape in fake-transport coverage before the next real probe.
- The offline raw-minute qualification harness v4 reserves a single external
  objective attempt before a possible token, records
  `reserved -> network_started -> summary_written`, pins artifact/Git roots,
  synchronizes each marker, performs initial reservation/configuration
  preflight then rechecks reservation before atomic reservation, checks fresh
  time before token issuance and at transport-adjacent request gates after OAuth,
  rejects redirects and oversized pages, and permits
  one first page plus at most one continuation in the fixed verified 2026-07-20
  Nasdaq window. It writes counts, timestamp bounds, exact-boundary facts, and
  booleans only outside Git from typed sanitized inputs. Its only result is
  `observed` or `rejected`; a self-consistent snapshot cannot promote a
  completed-bar contract. No credential or KIS network call occurred while
  preparing this harness.
- The active KST preflight slots map to New York `13:30` through `15:40` on the
  fixed date. The time gate compares the minute boundary separately from the
  required `10` through `45` safe seconds, so the final `15:40` safe interval
  is permitted without widening any other minute or date. Sanitizer tests also
  prove fake volume, cursor, account-identifier, and raw-row sentinels stay out
  of external summaries.
- The `O_EXCL` reservation marker now precedes its `reserved` ledger append.
  A stale concurrent precheck can therefore lose at marker creation without
  adding a duplicate ledger record; a post-marker ledger failure remains a
  non-retryable fail-closed marker state.
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
- The target-position policy graph is now the upstream contract: models may
  propose timestamped target states and weights, while Execution alone turns a
  validated current-to-target delta into a persisted intent. It does not accept
  a model-emitted order or sizing override.
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
- Deterministic enforcement of target-weight, concentration, exposure, loss,
  and reconciliation constraints before any target delta can become an intent.
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
- A sequential restart after a local-paper fill event but before its derived
  portfolio snapshot can reconstruct the exact recorded fill only when the
  accepted order, signal/execution bar fingerprints, price, fee, and timestamp
  still match. It replays the authoritative event log and adds neither another
  fill nor a snapshot; changed bars or fee settings fail closed. Concurrent
  local-paper fill calls are not a supported recovery mode.
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
- The Docker-local paper console is a monitor only. It renders the same
  sanitized snapshot through HTML and `/state`, projects only
  `source: local_paper` fills, and keeps KIS facts `unknown` until a fresh
  read-only snapshot exists. Its two controls write only local emergency state;
  neither can call a broker or suppress a verified hard-risk exit. The default
  Docker `engine` command is a daily report and deliberately produces no
  local-paper events, so a fresh console correctly begins empty.

## Current Objective

- The local paper console and its KIS snapshot bridge are complete pending
  integration commit. The loopback-only HTML and JSON views share a strict
  local-paper projection, consume only a fresh generic paper snapshot, and keep
  the web process free of KIS clients, credentials, and broker calls.
- Next, turn a fresh reconciliation into an operator decision-ready paper
  capital-envelope proposal. Preserve the reconciled currency, distinguish the
  reference orderability request from general buying power, and do not persist
  account values to Git or external evidence.
- The 2026-07-20 authority permits isolated `KIS_PAPER_*` account, position,
  reference-orderability, open-order, and market-data reads. It does not permit
  `KIS_LIVE_*`, external order submission/cancellation, or a nonzero paper
  capital envelope before the operator approves one.
- Keep KIS submission and live behavior failed closed. The historical
  `QQQ`/`SPY` raw-minute observation is terminal, independently scheduled
  history and is not retried, widened, or used as console state.
- Local emergency state continues to use atomic replacement and an exclusive
  sidecar lock inside one runtime. Unreadable, malformed, or timezone-less
  state fails closed and blocks new local-paper orders.

## Recovery

- Read the explicit JSON state file and reload it with
  `InMemoryBrokerTransport.from_state(..., state_path=...)`; the in-memory
  payload must match the persisted bytes.
- Reconcile account, buying power, open orders, and fills before accepting a
  new intent after restart.
- Missing, contradictory, stale, or outcome-unknown evidence fails closed.
- Current recovery stops at the in-memory fake or `local_paper`, never KIS.
- A fresh complete KIS console snapshot may recover a missing minimal evidence
  file through `kis_paper_console_bridge --recover-evidence`; this path reads
  only the sanitized runtime file and makes no KIS request. Stale, unavailable,
  malformed, or duplicate evidence fails closed and requires a newly scoped
  objective, never an automatic bridge retry.
- For a local-paper post-fill interruption, retry only the same sequential
  call with the same complete bars and immutable fee/slippage settings. The
  recorded fill is authoritative; do not manufacture a replacement fill or a
  derived snapshot during recovery.
- Preserve both failure artifacts. HTTP `500` alone does not establish a TR,
  account-product, funding, or sandbox cause. The documented `tr_cont` header
  deviation is corrected but unproven as a cause. Any future probe requires a
  separately authorized verification path, never an automatic retry.

## Ready Queue

1. Produce a no-order, operator decision-ready paper capital-envelope proposal
   from a fresh reconciliation without treating reference orderability as
   general buying power.
2. Ask the operator to approve or change the specific envelope. Do not submit
   or cancel an external order before that distinct decision.
3. Keep pure risk integration, append-only execution events, and a future paper
   canary as later separately bounded steps.

## Operator Help

- The operator must approve or change the specific paper capital envelope once
  the next objective presents it. Virtual-paper read-only development access is
  already authorized.

## Must Not

- Read `KIS_LIVE_*`, expose paper secrets/account identifiers, or give the web
  process access to any KIS value. The isolated bridge reads exactly the four
  approved `KIS_PAPER_*` values; its read-only KIS calls are the only KIS access
  in this execution lane.
- Submit, modify, or cancel an external order; change `THERICHER_MODE`; allocate
  paper capital; or enable live behavior under current authority.
- Add strategy or model-selection logic to execution.
- Let a dashboard "sell pause" suppress a hard-risk exit, emergency action, or
  reconciliation requirement.
- Relabel fake broker fills as `local_paper`.
