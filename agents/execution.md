# Execution Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Execution projection, not a broker-event ledger.

## Ownership

Own deterministic orders, fills, positions, cash, reconciliation, accounting
PnL, risk controls, emergency controls, and later KIS adapters. Treat model
output as untrusted input.

## Current Objective

Keep the deterministic decision-to-target-weight-to-intent path ready while
Data and Research advance independently. KIS Paper is authorized; KIS Live
remains unavailable.

## Current Facts

- local_paper, kis_paper, and kis_live remain separate routes. Local simulated
  fills retain source: local_paper.
- KIS Paper scheduled tasks and the credential-free local operations console
  already exist. Existing categorical results do not prove a selected model,
  external fill, or realized PnL.
- The current KIS Paper price/account route is private and virtual-only. No
  KIS_LIVE_* value is readable or callable.
- A missing or ambiguous exact broker outcome constrains replacement of that
  exact intent until reconciliation, never a distinct authorized Paper action
  or an independent lane.
- The target-position binding is now test-backed: it derives only the delta
  local-paper intent, rejects a pre-decision `as_of`, and emits scoped
  no-intent for an already-satisfied or mismatched target. It does not widen a
  KIS route or make a network call.

## Ready Queue

1. Keep the completed decision-to-target-weight-to-local-paper-intent contract
   stable while Data implements the next capture worker. Its replay and route
   isolation tests are the current integration evidence.
2. Use existing authorized KIS Paper scheduled/read-only evidence only when it
   improves a named integration. Preserve exact intent identity and do not infer
   a fill, cancellation, or PnL from incomplete evidence.
3. Keep the local console and local-paper replay aligned with the same
   deterministic intent/fill vocabulary.
4. Do not create an intent solely to manufacture activity. A goal-owned Paper
   action remains valid when its call-time technical invariants hold; it does
   not require a profitability, capital-envelope, or manual approval gate.

## Durable Constraints

- Persist intent before a KIS Paper side effect and reconcile an unknown
  outcome before replacing that exact intent.
- Never route a request to live or read KIS_LIVE_*.
- Keep credentials, account identifiers, private intents, broker payloads, and
  raw prices out of Git, logs, and public surfaces.

## Recovery

Current class: resume. Preserve exact ambiguous Paper evidence and reconcile it
through the owned route. Scope a failure to that intent and continue all
independent Data, Research, and authorized Paper work.

## Next Handoff

Return any future Data/Research integration request with the existing target
binding and route boundaries intact. Do not wait for prospective data or model
promotion to prepare deterministic execution.
