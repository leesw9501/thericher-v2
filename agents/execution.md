# Execution Agent

## Working Memory

Own deterministic intents, paper fills, position/cash state, reconciliation,
PnL accounting, emergency controls, and future KIS Paper transport.

All virtual Paper data/account/order work and recurring schedules are
standing-authorized. Historical one-shot, raw-retention, quote, model, or
`safe_to_submit` values cannot create a manual Paper hold; only paper-host
isolation and reconciliation of an unknown exact durable intent can stop that
same request. Live routing remains unavailable.

## Current State

- Local paper is available and all simulated fills use `source: local_paper`.
- The daily comparative CPU run uses local paper for both relative-strength and
  cash/fixed-quantity buy-and-hold references; each run remains replayable.
- The local dashboard is credential-free and may display sanitized holdings,
  price, open-order, and emergency state.
- The local console now persists `pause_buys` and `pause_sells` on a separate
  shared volume. They are operator-operational state, not paper approval gates:
  the matching directional pause is checked before the daily session reads
  configuration or calls KIS. Missing state defaults to both directions ready.
  The web process cannot call KIS,
  read credentials, access private intent state, or mount `D:\\market_data`.
- A due session that stops before a canary intent exists, including a buy pause
  or quote failure, now refreshes the sanitized canary runtime as
  `unavailable`. This avoids a stale prior canary display while keeping the safe
  detailed reason in external session evidence only.
- KIS Paper account/data/order access, paper submit/modify/cancel, routine
  sizing, and schedules are standing-authorized.
- `kis_paper_canary` is the first executable narrow adapter: US buy-limit only,
  whole shares and explicit limit price, fixed virtual host/TR IDs, durable
  intent-before-submit, no duplicate retry after ambiguity, and cancellation
  after accepted submit. Private recovery state stays in a dedicated Docker
  volume; external evidence and dashboard projection are sanitized.
- The first real virtual-token attempt on 2026-07-21 returned `auth_rejected`
  before account data or submit. The bounded console bridge later returned
  `balance_rejected` with HTTP 500 and safe KIS code `EGW00201`; it made no
  order. KIS's official sample repository labels that code as a per-second
  request-limit exceedance. A rebuilt current read-only transport now applies
  one-second monotonic spacing only to valid external calls, and the next single
  bridge completed with sanitized facts: one position, zero open orders, and USD
  currency labels. No live variable was read and no order was sent. The
  canary's distinct virtual transport now reuses that tested pacing. Its first
  current-image run, `canary-20260721T225034Z`, completed initial
  reconciliation then became `outcome_unknown` with
  `submit_transport_unknown`. The safe evidence has no broker order reference,
  which does not prove that no submit side effect reached KIS. Its one exact-run
  recovery made no order-route request and found an available account with zero
  open-order/completion counts and no matching entry, but it remains
  `reconciliation_unresolved` because the missing reference cannot prove
  absence. Treat that run as preserved evidence, not a paper authority gate.
- The first independent paced run, `canary-20260721T232137Z`, reached clean
  initial reconciliation and then recorded `submit_kis_rejected`, with zero
  open orders/completion rows and no reference. It is preserved rather than
  retried. The current closed code does not retain KIS's rejection code, so the
  next small improvement is a strictly validated short code only, never raw
  response text.
- The next independent run, `canary-20260721T233837Z`, confirmed the code
  projection but returned no valid KIS-style code (`submit_upstream_code: null`)
  after another clean `submit_kis_rejected`. Official KIS samples match the
  existing order mapping. The ready execution improvement is a quote-derived
  private limit in a known US regular-session window, not another fixed `$1`
  submission or a mapping guess.
- Canary cancellation policy is durable with its private state. A state-root
  lock serializes different run IDs; a persisted acknowledged matching order
  resumes cancellation on restart. Non-200 or non-success submit results and
  any matching completion record after cancellation remain `outcome_unknown`,
  never a replacement-submit or falsely clean path.
- `kis-paper-session` now fetches one transient virtual SPY quote, derives a
  one-share 25 bps-below-last nonmarket limit at the reported decimal scale,
  and invokes the canary without exposing the quote or price. It accepts only a
  KIS-success quote and rechecks both the limit validity and the explicit 2026
  Nasdaq/NYSE session window immediately before submit. The Windows Scheduled
  Task `thericher-kis-paper-quote-session` invokes it on weekday KST 23:35; that time
  is inside the worker's time window in both daylight and standard time. Its
  2026-07-22 off-session Docker exercise produced only the safe `not_due` /
  `outside_regular_session` outcome. Holidays and out-of-scope dates now return
  `session_unavailable` before environment access, and early closes end at the
  declared close. This is a route/credential correctness property, never a
  Paper authority gate.
- The independent Windows task `thericher-kis-paper-intraday-head` is data-only:
  it uses only Paper market-data credentials, has no account or order route,
  and writes its cache outside Git. It may run beside the quote session because
  it owns a separate cache root and does not mutate execution state.
- The current-user Windows tasks are installed and `Ready`:
  `thericher-kis-paper-quote-session` at 23:35 KST and
  `thericher-kis-paper-intraday-head` at 06:20 KST with four pages per target,
  Tuesday through Saturday. The historical first 02:35 KST run remains evidence
  of the earlier mid-session configuration; current due runs invoke only their
  named local Docker profiles. Their outcomes are runtime evidence, not another
  permission step.
- The first due quote session on 2026-07-22 completed successfully as a task
  but ended before intent creation with `quote_unavailable` /
  `quote_response_incomplete`. Its safe evidence is external at
  `D:\\thericher-v2\\model-artifacts\\execution\\kis-paper-canary-session\\paper-session-20260722T143508395909Z\\evidence.json`.
  A one-time Paper-only shape probe found a successful HTTP/JSON response with
  a mapping output but blank `last` and `zdiv` fields. No order, account value,
  raw response, or credential was retained. This is a quote-field compatibility
  fact, not a Paper authority, scheduling, or retry latch. The current image
  classifies the same two blank required fields as `quote_response_blank` for
  future safe evidence; the historical result remains unchanged.
- The exact Paper-host-pinned SPY `price-detail` structural probe
  (`HHDFS76200200`) also returned a successful mapping on 2026-07-22, but its
  `last`, decimal-scale, and tick fields were all blank. The probe retains and
  emits categories only, creates no intent, and cannot submit an order. It
  rejects this candidate as a price conversion, not as a Paper permission,
  scheduling, or retry condition; a later correctly scoped candidate or
  virtual canary remains allowed.
- A later official KIS sample cross-check established the SPY AMEX mapping:
  `AMS` for the exact asking-price (`HHDFS76200100`) and price-detail
  (`HHDFS76200200`) endpoints, and `AMEX` for the virtual order. The current
  input adapter accepts only a fresh Korea-timestamped asking-price last, an
  equal decimal scale from price detail, and a positive `e_hogau` tick that is
  representable at that scale. The raw last need not itself be a tick multiple:
  the derived submit limit is rounded down and then validated against the tick.
  Values and bodies stay transient. Its first independent
  virtual canary reached `outcome_unknown` / `reconciliation_unresolved`; a
  same-run read-only recovery reported an available account and zero open
  orders in sanitized aggregates, with no buy or cancel request. This is that
  one run's evidence, never a Paper authority or scheduler hold.
- `reconcile_kis_paper_canary_unknown_run.py` reconstructs only an ambiguous
  persisted intent and permits only `submission_started`, `outcome_unknown`,
  or `cancel_started`. It rejects an `intent_recorded`, `submitted`, rejected,
  or terminal state before network access, so it cannot create a new order or
  turn a recovery into cancellation. If the private state disappears during
  recovery, it exits with `recovery_state_missing` instead of recreating it.
- The current-image `kis-readonly` bridge completed on 2026-07-22 and refreshed
  the credential-free console projection from sanitized KIS Paper account facts.
  It submitted no order. Its external evidence remains under
  `D:\\thericher-v2\\model-artifacts\\execution\\kis-paper-console-bridge`.
- On 2026-07-22 at 15:27 ET, an independent current-image quote session reached
  category-only `acknowledged_order_reference`, then its requested cancellation
  and reconciliation completed cleanly. The read-only lifecycle projector turns
  that external evidence into a replayable `kis_paper` / `paper_only` fact with
  `cancelled` lifecycle state and `not_eligible` attribution status. It makes no
  KIS call and reads no credential. This proves the virtual execution lifecycle,
  not a model edge, realized PnL, or a new approval condition.

The receipt bridge is now execution-owned at
`execution.paper_decision_bridge`. It maps an eligible immutable receipt to a
deterministic `local_paper` entry or exit intent whose `decision_id` is the full
receipt identity. Its KIS branch prepares, but does not submit, a matching
virtual buy or sell decision only after an execution binding and final
tick-valid price proof. It reads no environment, credential, KIS client, or
network path. A
new receipt-shaped canary decision carries an exact opaque receipt digest as
`attribution_ref` in sanitized lifecycle evidence; historical canaries retain
their existing short `decision_ref` only.

The daily SPY session now evaluates its cache and Research receipt before it
loads KIS Paper configuration or requests a quote. It prefers one complete
forward `SPY/AMS` head source over older history, never mixes their rows, and
reads one current complete KIS Paper snapshot before an eligible receipt can
obtain an independent fresh `AMS` quote. The pure target resolver permits only
`flat -> buy one share` or `one SPY/AMEX share -> sell one share`; any SPY open
order, stale account fact, or other inventory is a scoped no-intent result.
The stable receipt digest names the durable canary state file, and the durable
intent includes its side, so a changed quote cannot replace the first price and
the same receipt cannot become the opposite order. Sanitized lifecycle facts
may expose categorical order side and `pnl_status: not_observed`, never a fill,
account value, cost basis, or realized PnL. The scheduled daily service no
longer auto-cancels an accepted valid lifecycle order; the standalone canary
remains cancellation-oriented. The `thericher-kis-paper-daily-spy-session`
task runs at 23:50 KST Tuesday through Saturday.

## Ready Queue

1. Reconcile observed daily Paper orders/positions without attributing a fill or
   PnL until an authoritative KIS completion fact exists.
2. Keep scheduled KIS Paper sessions on the proven `AMS`/`AMEX` price mapping,
   receipt-linked identities, and one-share target resolver. An ambiguous exact
   intent remains separate from every later distinct Paper intent.
3. Add bounded automatic stale-order reconciliation only when it preserves the
   same exact order identity and does not become a new approval or quota system.
4. Keep account snapshots and dashboard state separate from credential-bearing
   execution processes; do not add a live route implicitly.

The new `kis_paper_receipt_observer` is the first exact-intent read-only path.
It can establish `open` only through a matching redacted current open-order
reference. Its same-day history ID sighting and aggregate position categories
remain `outcome_unknown`, and its artifact always carries
`pnl_status: not_observed`. The observer module contains no submit, modify, or
cancel capability; its Docker profile mounts private state read-only.

`kis_paper_terminal_field_probe` now exercises the same fixed `VTTS3035R`
history source for one existing SPY/AMEX state without using a writer lock on
the read-only volume. It binds the requested run to its internal state and
derives the query only from a durable acknowledged submission time, requires
completed bounded pagination, compares direct/original order lineage only in
memory, and writes categorical field support outside Git. Existing legacy
states without that time return `submission_time_missing` before configuration
or network access. New acknowledged states preserve the time through later
cancellation/reconciliation. It retains `terminal_state_support: unqualified`
and `pnl_status: not_observed`; no terminal transition, PnL, retry, or Paper
halt was created.
The scheduled daily SPY service automatically invokes the receipt observer and,
after the same exact receipt-derived `run_id` check, this terminal-field probe.
The session retains only the probe's categorical safe payload and a
content-hash artifact reference. There is no latest-run scan, second scheduler,
or second order path. A read-only observer or terminal-probe error records only
its respective scoped unavailable result without changing the canary outcome,
retrying an order, or blocking a later distinct session.

## Authority And Boundaries

Paper submission is authorized; no capital envelope, profitability report,
dashboard state, trade count, per-call approval, or `safe_to_submit` proxy is
required. The read-only bridge reports only scope and account-snapshot
completeness; the executor enforces technical route/intent/reconciliation facts
at the actual request. Do not read `KIS_LIVE_*`, create a live
host/configuration path, or emit secrets. Model output remains untrusted input
to deterministic execution logic. Historical one-shot or retention markers
cannot disable later correctly scoped paper work; they only describe the
recovery state of their own run. There is no per-goal or one-shot quota on
distinct virtual-paper intents or goal-owned Paper schedules.

The operator's default-progress direction also forbids a new Paper permission
proxy based on a report, input quality, model result, historical run, or
schedule state. A failed price/input contract produces a no-intent fact for
that exact attempt; it does not halt a distinct correctly scoped action. Keep
only the exact-intent reconciliation rule and the paper-only technical route.

The directional console controls are reversible local operating instructions,
not policy latches. `pause_buys` stops a newly created buy intent before KIS
configuration or network access. `pause_sells` will never suppress a hard-risk
exit. A malformed control file preserves the requested-pause posture until the
operator clears it locally; it is not a request for approval or a global stop.

## Durable Knowledge

- Technical recovery rules prevent duplicate paper submissions; they are not
  operator gates.
- Data/model limitations should be recorded in evidence and attribution rather
  than silently changing execution state.
- A scheduler may run paper work repeatedly when it retains paper-only routing,
  idempotent intents, bounded concurrency, and reconciliation behavior. Those
  technical properties do not create a manual or numerical Paper-work gate.

## Recovery

Use local events for local reconstruction and KIS as the authority for external
paper state. Unknown broker state is `reconcile`; an emergency stop or cancel
does not wait for review. The read-only unknown-run helper reloads its durable
intent and checks its stable identity before recovery, so it cannot regenerate
a new decision timestamp into a replacement order. It only accepts ambiguous
pre-cancel phases and never becomes a fresh submit, modify, or cancel action.

## Next Handoff

Continue the observer only for exact durable receipt identities and retain
ambiguous observations as evidence, never as a Paper halt. The next execution
handoff is to consume the next scheduled daily outcome, including the automatic
terminal-field fact when a new acknowledged state exists, without interpreting
field presence as a terminal/PnL result. Retain Paper-only routing, secret
redaction, state replay, and no fabricated PnL. Only a live-money boundary,
paid commitment, unclear rights, public exposure, or an external KIS credential
reset needs operator input.
