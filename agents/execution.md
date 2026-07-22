# Execution Agent

## Working Memory

Own deterministic intents, paper fills, position/cash state, reconciliation,
PnL accounting, emergency controls, and future KIS Paper transport.

## Current State

- Local paper is available and all simulated fills use `source: local_paper`.
- The daily comparative CPU run uses local paper for both relative-strength and
  cash/fixed-quantity buy-and-hold references; each run remains replayable.
- The local dashboard is credential-free and may display sanitized holdings,
  price, open-order, and emergency state.
- The local console now persists `pause_buys` and `pause_sells` on a separate
  shared volume. They are operator-operational state, not paper approval gates:
  the buy pause is checked before the quote session/canary reads configuration
  or calls KIS; the sell pause is retained for the later sell executor. Missing
  state defaults to both directions ready. The web process cannot call KIS,
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
  `thericher-kis-paper-intraday-head` at 02:35 KST, Tuesday through Saturday.
  They invoke only their named local Docker profiles. Their first due outcomes
  are runtime evidence, not another permission step.
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

## Ready Queue

1. Preserve local-paper replay and PnL attribution for the daily baseline.
2. Keep scheduled independent KIS Paper canaries using the proven transient
   `AMS`/`AMEX` price-input mapping and category-only lifecycle facts. Connect a
   later research-originated decision receipt only through the deterministic
   intent boundary; keep every ambiguous intent's recovery separate from the
   next distinct Paper intent.
3. Add a sell path only when it has its own deterministic sizing, exit, and
   reconciliation contract; consume the existing sell pause then. Do not add a
   live route implicitly.
4. Keep account snapshots and dashboard state separate from credential-bearing
   execution processes.

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

Hand the sanitized lifecycle projection, current-canary evidence, and any
unresolved KIS Paper route fact to Codex. Only a live-money boundary, paid
commitment, unclear rights, public exposure, or an external KIS credential reset
needs operator input.
