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
  currency labels. No live variable was read and no order was sent. The existing
  canary remains `intent_recorded` with no broker order reference. Its distinct
  virtual transport needs the same tested pacing before the first
  submit/cancel/reconcile invocation. Treat it as integration recovery, not a
  paper authority gate.
- Canary cancellation policy is durable with its private state. A state-root
  lock serializes different run IDs; a persisted acknowledged matching order
  resumes cancellation on restart. Non-200 or non-success submit results and
  any matching completion record after cancellation remain `outcome_unknown`,
  never a replacement-submit or falsely clean path.

## Ready Queue

1. Preserve local-paper replay and PnL attribution for the daily baseline.
2. Reuse external-request pacing in the virtual canary transport, then
   reconcile the persisted canary run and run one first acknowledged/cancelled
   bounded paper canary. A failed canary records its technical recovery state
   while Data and Research continue; it does not reopen an approval question.
3. Keep the generic broker adapter disabled while this canary remains the only
   bounded KIS order surface; do not add sell or live routes implicitly.
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
recovery state of their own run.

## Durable Knowledge

- Technical recovery rules prevent duplicate paper submissions; they are not
  operator gates.
- Data/model limitations should be recorded in evidence and attribution rather
  than silently changing execution state.
- A scheduler may run paper work when it retains paper-only routing, idempotent
  intents, bounded concurrency, and reconciliation behavior.

## Recovery

Use local events for local reconstruction and KIS as the authority for external
paper state. Unknown broker state is `reconcile`; an emergency stop or cancel
does not wait for review. A stored canary run ID reloads its durable intent and
checks its stable identity before recovery, so a restart cannot regenerate a
new decision timestamp into a replacement order.

## Next Handoff

Hand the virtual-token recovery result, canary reconciliation evidence, and any
unresolved KIS Paper route fact to Codex. Only a live-money boundary, paid
commitment, unclear rights, public exposure, or an external KIS credential
reset needs operator input.
