# Execution Agent Stateboard (페이퍼 실행 담당)

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the current virtual-Paper execution projection, not an order log.

## Ownership And Hard Boundary

Execution owns deterministic sizing/risk, intent persistence, broker routes,
fills, positions, reconciliation, accounting, and emergency controls. It treats
model output as untrusted input. `local_paper`, `kis_paper`, and `kis_live` are
separate routes; local replay fills remain `source: local_paper`. Never read or
route `KIS_LIVE_*`.

## Current Objective: Virtual-Paper Lifecycle Canary Reattached

The existing `thericher-kis-paper-quote-session` task completed its 2026-08-05
23:35 KST owned invocation with Scheduler result `0`. Its exact scheduled
receipt `paper-session-20260805T143501171367Z` is `canary_completed` and binds
only the direct lifecycle `canary-20260805T143501171367Z`. The host projector
and independent offline validator both classify that lifecycle as `cancelled`
with `clean` reconciliation and attribution `not_eligible`. It is a
cancelled-and-clean virtual-Paper execution result only: no fill, PnL,
profitability, or model conclusion follows. Its latest 2026-08-06 23:35 KST
Scheduler result is `0`; reattaching that source-safe session outcome remains
outside this execution package. The same existing task owns the next
opportunity at 2026-08-07 23:35 KST; do not manually invoke or duplicate it.

The existing `thericher-kis-paper-quote-session` Windows task owned one current
virtual-Paper canary at 2026-08-04 23:35 KST and exited with Task Scheduler
result `0`. Its exact scheduled-session receipt
`paper-session-20260804T143501870818Z` is
`recovery_required/prior_submission_unresolved` for the preserved
`canary-20260722T184759527919Z` state; the independent offline lifecycle
validator agrees on `outcome_unknown/unresolved`. This is neither a new broker
or lifecycle result nor a fill, no-intent, or PnL result. Do not manually invoke
the task, infer an outcome, or create a second runner; the later 2026-08-05
receipt is the current exact canary evidence above.

The separate 2026-08-04 23:50 KST daily SPY receipt is exactly
`daily-spy-20260804T145002356832Z`: `no_intent/quote_unavailable`, no run ID,
and receipt observer plus terminal-field probe both `not_attempted`. It has no
canary lifecycle, broker, fill, or PnL interpretation. The 2026-08-05 06:20
KST intraday-head receipt is
`intraday-head-20260804T2120059626443Z`,
`recovery/prospective_session_id_unavailable`; its later 2026-08-06 06:20 KST
scoped recovery is recorded below.

The 2026-08-05 23:50 KST daily SPY receipt is exactly
`daily-spy-20260805T145001601078Z`: `no_intent/quote_unavailable`, no run ID,
and receipt observer plus terminal-field probe both `not_attempted`. It has no
canary lifecycle, broker, fill, or PnL interpretation. The 2026-08-07 04:24
KST intraday-head receipt remains
`recovery/prospective_validation_payload_unavailable`: collection `exit_zero`,
exact QQQ Paper-only `no_intent`, and no broker action, lifecycle, fill, or
PnL result. The rebuilt terminal contract requires a same-run source-safe
capture binding for future runs and turns a missing binding into local
recovery; historical evidence stays `legacy_unbound`. Its v3 offline
validation output omitted the scheduler-consumed top-level `status:
validated`; the credential-free, network-disabled v4 validator writes it in a
new immutable namespace without changing the v3 terminal or any execution
route. The installed task owns 06:20 KST. Its next exact receipt may establish
only a validation or recovery fact, never a KIS call, task, order path,
authority, fill, or PnL change.

The rebuilt single `thericher-kis-paper-daily-spy-session` image preserves
`quote_unavailable` for an exact fresh-quote fetch failure and uses
`receipt_preparation_unavailable` only when local receipt/limit preparation
fails or is not ready. The historical 08-04 receipt remains unchanged. The
split has no new route, call, intent, cancellation, or secret-bearing evidence
surface; 141 focused execution tests and the 2,573-pass, 23-skip authority
suite passed before the existing `IgnoreNew` 23:50 KST task was reinstalled.

Today's source-free Claude challenge is `uncertain`: it inspected no code or
state and therefore could not attest the claimed guard conjunction. An
independent static Review found the registered task/Compose surface uses the
shared canary state root, central guarded client, exact virtual host and route
allowlist, and dashboard isolation; no second installed task path was found.
The generic direct canary CLI still accepts a configurable state root for a
manual Paper-environment invocation, outside the registered-task contract.
That is a documented scope limit, not a new task, route, authority, or Paper
hold. The 170 focused offline canary/quote/receipt/dashboard/schedule tests
passed.

At 03:16 KST on 2026-08-05, one exact historical terminal-field probe used
only the virtual token and history GET path for the preserved legacy state. It
returned `history_observed_derived_date` with a derived ET-day anchor and an
absent identity row. That is not a no-order, cancellation, terminal, fill, or
PnL conclusion, so the legacy state remains `outcome_unknown`. The probe's
legacy identity/date checks and the positive/negative local controls are now
explicit; Claude's review of that narrow observer change was
`supported-with-limits`.

At 21:38 KST, the task's `IgnoreNew` concurrency and local Docker action were
reattested. Its `kis-paper-session` image was rebuilt from current source and
passed a network-disabled module-import check. The source-safe preflight also
passed 135 focused canary, quote, intent, lifecycle-projector, and dashboard
tests. These are local-contract facts, not a broker result or a reason to run
the task early.

At 08:04 KST on 2026-08-05, the registered task reattached as one Docker
Compose `kis-paper-session` profile `run --no-deps` action with `IgnoreNew`
and zero restarts. Its static Compose command contains only the existing
session module with `--execute --cancel-after-submit`, not a live route. A
fresh source-free Claude check returned `supported-with-limits`; 161 offline
canary, quote, intent, lifecycle-projector, dashboard, and schedule tests
passed. It changed no task, image, route, credential, or broker state.

The schedule installer now explicitly retains `RestartCount = 0` alongside
`IgnoreNew`. The current registered task already has that setting; this removes
reinstallation drift without restarting or changing tonight's task.

The host lifecycle projector and the independent
`validate_kis_paper_canary_lifecycle_evidence.py` validator now share a direct,
non-link receipt-path check and require the recorded `run_id` to match the
requested run. They emit only a sanitized lifecycle fact or categorical
`unavailable`; they never call KIS or load credentials. The focused reattestation
passed 82 tests. The accompanying Claude design challenge ended without a
verdict (`review_unavailable`), so source/test evidence preserves the existing
one-attempt contract rather than changing execution authority.

The same host projector can now receive one explicit `--session-id` for a
pre-canary scheduled-session receipt. It refuses links, `.`/`..`, ID mismatch,
and extra or malformed writer fields; it never chooses a newest artifact and
emits `kis_paper_canary_session_fact`, not a lifecycle fact. If a session finds
`prior_submission_unresolved`, its existing prior-canary runtime remains
`outcome_unknown`/`unresolved` instead of being replaced with a generic current
session state. That preserved run still uses the direct lifecycle validator.

The latest safe private-state inventory has no `submitted` or `cancel_started`
phase. A replay of the same session ID reuses only its own durable state and
cannot submit a replacement intent. A distinct current session does not scan
or mutate other historical state files: while holding the shared lock, its own
durable intent and fresh account/open-order snapshot determine whether a
matching current open order blocks submission. The preserved legacy unknown is
therefore neither resolved nor a cross-run Paper hold. At 03:50 KST, the new
source-free Claude drift review returned `supported-with-limits`: it supports
the current kill tests but explicitly does not establish that a distinct prior
unknown absent from the current broker view is clean, nor that a runner failure
between submit and reconciliation has already recovered. Those limits do not
authorize a historic-state scan or a global pause. Temporary Validation agrees
that this is a documented scope limitation rather than a pre-23:35 contract
violation; delayed visibility after a distinct unknown is its strongest missing
evidence. Focused fake-route tests prove same-run recovery,
current-open-order rejection, and no mutation of the old state.

At 06:39 KST, a renewed source-safe Claude falsification check again returned
`supported-with-limits`. It restated that an open-order view can lag and that
the shared lock must cover check through submit; it read no project files and
granted no authority. The existing exact-intent, fresh-view, virtual-host-only
contract therefore remains the evidence boundary for tonight's task-owned run.

At 04:03 KST, a network-disabled, read-only volume inspection reattached the
same fact without exposing any run, order, account, or price values: 13 private
state files classified only as `cancelled`, `intent_recorded`, or
`outcome_unknown`, with no `submitted` or `cancel_started` state. The sanitized
runtime projection was unavailable. This is a preflight inventory, not a
broker outcome or a reason to invoke the task early.

The canary contract is fixed:

- virtual host only: `openapivts.koreainvestment.com:29443`, HTTPS, no
  redirects, approved quote/account/order/cancel routes only;
- one fresh quote-derived SPY limit and one share, with quote age bounded and
  rechecked immediately before broker I/O;
- durable `intent_recorded` state before side effects and a shared lock across
  sibling runs;
- a replay of the exact same run recovers only that durable state and cannot
  create a replacement order; a distinct run checks current open orders at its
  own call time;
- fresh account/open-order reconciliation before submit; a matching open order
  blocks a new submission, including partial fills or a different limit price;
- accepted flow uses `cancel_after_submit`; an exact unknown may resume only
  its acknowledged cancellation after proven-open reconciliation; and
- the generic offline lifecycle validator accepts only a direct, non-link
  `paper_only` receipt whose recorded `run_id` matches the requested run and
  emits a sanitized categorical fact; terminally cancelled, cleanly reconciled,
  freshness-valid evidence remains the stricter downstream completion case.

The at-most-one-**concurrent-submission** statement is scoped to the existing
single host-owned state root and its shared `.canary_execution` lock. The 23:35
KST `quote-session` canary and the distinct 23:50 KST daily-SPY receipt session
both use that root: they may be scheduled separately, but cannot submit at the
same time, and a matching open order blocks a fresh canary. The quote-session
uses `cancel_after_submit`; the daily-SPY route owns its separate receipt-backed
Paper lifecycle. A copied/restored private state directory, second state root,
second machine, or out-of-band runner is outside this canary contract; none is
installed. This is a scope fact for this task, not a general Paper hold.

The 2026-08-05 source-safe Claude drift-check returned
`supported-with-limits`. It confirmed the virtual-host, durable-intent,
same-intent recovery, shared-lock, and fresh account/open-order controls, while
correcting the prior single-runner shorthand. A process interruption after a
submitted quote-session intent still requires its exact durable recovery path;
that is a scoped recovery limit, not evidence of a broker outcome or a hold on
another correctly scoped Paper action.

## Current Supporting Surfaces

- The exact 2026-08-07 06:20 KST intraday-head task has Scheduler result `1`
  and an immutable terminal `recovery/collection_exit_nonzero`. Its same-run
  capture binding is verified but `incomplete`; QQQ session and v4 validation
  are `not_applicable` because the success-only downstream branch was skipped.
  This is Data recovery evidence, not a Paper lifecycle, broker, fill, PnL, or
  model outcome. The completed read-only recovery projection now reports only
  the exact bound chain's `rejected_duplicate_conflict` category and otherwise
  `evidence_unavailable`. Future receipts now seal only collector-time conflict
  provenance; the next Engine-owned EMA mechanics replay remains local-paper
  only and cannot create a KIS or Paper side effect.
- The credential-free loopback dashboard cannot call a broker or submit an
  order. Authenticated local emergency and pause controls may change only their
  local control state; its schema-v3 account projection omits prices and order
  identifiers.
- The local replay now derives FIFO realized-after-fee PnL only from closed
  `source: local_paper` lots. It deliberately excludes open-lot valuation and
  all KIS account/broker facts, so it is descriptive simulator accounting, not
  a fill-quality, profitability, model, or execution-risk input. The associated
  Claude request returned unrelated stale task text rather than its requested
  verdict; record `review_unavailable` and rely only on the local contract tests.
- The completed `source-local-ema-local-paper-pnl-attribution-v1` reattests
  the fixed EMA mechanics receipt before rebuilding its same session-local
  in-memory replay. It verifies foreign fills before FIFO accounting, checks
  each terminal account cash delta against realized-after-cost PnL, and retains
  only aggregate 20-session facts: 152 local-paper fills, zero open quantity,
  gross delta `-26.299200`, fees `10.8932`, and net delta `-37.192400`.
  This negative local replay is not a KIS fill, broker account result,
  profitability claim, model decision, or Paper input. Evidence remains under
  `D:\thericher-v2\model-artifacts\research\source-local-ema-local-paper-pnl-attribution-v1\20260807-ema-pnl-attribution-r1\summary.json`.
- Local Paper retains an accepted event's durable timestamp when it replays a
  pending or filled order. It rejects submission before intent creation and
  raises instead of recreating a fill when the later of intent creation and
  acceptance would follow an intraday execution bar. For D1, the known US
  market and venue aliases use a session-date label rather than an actual open
  timestamp, so they permit only the same or an earlier availability date and
  other markets fail closed. That D1 exception cannot attest sub-session
  availability.
  This blocks a retrospective next-bar-open fill without changing KIS routes,
  credentials, Paper authority, pricing sources, or model policy; contradictory
  legacy logs remain readable but fail that exact replay.
- The QQQ observed/provisional runtime route keeps the worker observation time
  as its proposal decision time. If its retained candidate replay bar already
  started before that decision, its local path returns
  `decision_after_replay_bar` with no runtime state or fill rather than
  backdating an order. This exact no-intent does not inhibit a distinct fresh
  Paper session with its own receipt, account, quote, and availability evidence.
- The completed Engine-owned session-reset Donchian mechanics preflight uses
  the existing receipt-to-local-paper bridge only. Its predeclared
  penultimate-bar terminal exit fills at the final-bar open, every retained
  fill remains `source: local_paper`, and replay reproduces each terminal-flat
  account. Its source-local `2026-08-06-r1` artifact marks the fixed rule
  activated and classifies an all-flat no-action rule as `no_rule_activation`.
  It made no KIS call, credential read, external broker call, or
  virtual-Paper intent; it is not an execution result, model promotion, or
  Paper input.
- The current source-free Claude falsification check returned
  `supported-with-limits`: virtual-host pinning, pre-submit durable intent,
  fresh account/quote reconciliation, exact-intent unknown-outcome recovery,
  and dashboard route isolation remain intact. A single canary may retain
  sanitized filled/remaining quantity or position state, but maps no price,
  cost, valuation, or model outcome. It is execution evidence only, never a
  fill-quality, PnL, profitability, or model result.
- The resumed 2026-08-04 offline reattestation passed 137 canary, intent,
  quote, receipt, lifecycle-projection, dashboard, and schedule tests. This
  verifies deterministic local contracts only; it is not a current broker
  outcome or a substitute for the task-owned lifecycle receipt.
- The host lifecycle projector additionally has explicit valid-evidence and
  missing-evidence CLI contracts; 97 focused canary/quote/lifecycle tests pass
  without broker or credential access.
- A cancellation-transport regression now proves that an exact prior
  `cancel_transport_unknown` canary re-enters only its recovery path: the next
  matching quote session records `recovery_required` without a fresh asking
  price or buy-limit request. This is a local contract test, not a broker
  outcome.
- The Compose isolation test now scopes `kis-paper-session` to its immediate
  `kis-paper-daily-backfill` boundary and requires exactly one `--execute`.
  Later profile services can no longer mask a canary preview-path regression.
- Fresh `ResearchDecisionReceipt` objects now carry opaque commitments to the
  proposal's normalized instrument, market, and decision class; local Paper
  also commits its exact target exposure. Each route recomputes the commitment
  it needs before preparation, so a matching lineage reference alone cannot
  redirect a receipt to another symbol or target. Old receipts remain readable
  for replay evidence but return a scoped no-intent on both Paper routes.
- `daily-spy-head` and `daily-spy-session` use explicit Monday--Friday KST
  schedules. This aligns same-date Eastern sessions without changing route,
  sizing, cancellation, or service behavior.
- The prospective SPY cycle remains a data-dependent no-intent path until its
  own fresh completed-bar receipt exists. Timing observations are not Paper
  permissions.
- The same task-owned intraday-head dispatcher now invokes the pre-existing
  QQQ observed/provisional receipt route immediately after successful
  collection, before slower observers consume its two-minute input-freshness
  budget. The route creates no new adapter, task, or authority: it reuses the
  local replay, fresh account/open-order and quote checks, virtual-host-pinned
  canary, exact-intent recovery, cancellation, and network-disabled validator.
  Before it constructs or reaches a KIS client, the named route also binds its
  ready 90-bar input window to local-retention metadata at the receipt's
  `decided_at`. Missing metadata or retention after that timestamp produces a
  scoped no-intent before account, quote, preparation, or order work. This is
  local-cache evidence only, not provider availability/finality or a model
  promotion claim; it does not alter the separately task-owned canary.
  Claude's integration challenge was `supported-with-limits` on exactly that
  scope.
  Its source-safe outcome remains execution evidence only, never a model,
  fill-quality, PnL, or profitability claim.

## Recovery

An absent result before the worker runs is expected. A stale/missing account or
quote, live-host mismatch, duplicate order, or unresolved exact-intent outcome
rejects only that canary attempt. Preserve the source-safe categorical state;
do not submit a replacement for that same run based on missing evidence. A
distinct current run retains the shared lock and its fresh matching-open-order
check; unrelated historical state remains preserved but cannot create a global
Paper hold.

## Handoff

After the task runs, reattach its source-safe runtime projection and matching
offline validator before interpreting the lifecycle. The 2026-08-05 result is
`cancelled/clean` and attribution-ineligible; its next recovery action is the
existing task's next due run, not a foreground retry. Record only result
category, reconciliation class, route isolation, evidence pointer, and next
recovery action. Historic execution evidence remains in Git and
`D:\thericher-v2\model-artifacts\execution`; the latest pre-current canary
session receipt is
`kis-paper-canary-session\paper-session-20260801T143501387961Z\evidence.json`.
