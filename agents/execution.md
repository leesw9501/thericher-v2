# Execution Agent

## Working Memory

Own deterministic intents, paper fills, position/cash state, reconciliation,
PnL accounting, emergency controls, and future KIS Paper transport.

## Current State

- Local paper is available and all simulated fills use `source: local_paper`.
- The local dashboard is credential-free and may display sanitized holdings,
  price, open-order, and emergency state.
- KIS Paper account/data/order access, paper submit/modify/cancel, routine
  sizing, and schedules are standing-authorized.
- No KIS Paper order transport is complete yet. Existing KIS clients are
  virtual-paper-host-only; a future transport must preserve that fail-closed
  route property.

## Ready Queue

1. Preserve local-paper replay and PnL attribution for the daily baseline.
2. Turn the verified KIS Paper order contract into a minimal paper-only adapter
   once route/header behavior is established through authorized KIS Paper work.
3. Persist an idempotent intent before every paper side effect and reconcile an
   unknown broker outcome before replacement.
4. Keep account snapshots and dashboard state separate from credential-bearing
   execution processes.

## Authority And Boundaries

Paper submission is authorized; no capital envelope, profitability report,
dashboard state, trade count, or per-call approval is required. Do not read
`KIS_LIVE_*`, create a live host/configuration path, or emit secrets. Model
output remains untrusted input to deterministic execution logic.

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
does not wait for review.

## Next Handoff

Hand the adapter's paper-host enforcement test, intent/reconciliation coverage,
and any unresolved KIS Paper route fact to Codex. Only a live-money boundary,
paid commitment, unclear rights, or public exposure needs operator input.
