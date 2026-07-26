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
- The new Data session-capture receipt uses only the KIS Paper market-data
  route and has no Execution account, position, intent, order, or live effect.
- The completed QQQ/SPY daily sequence screen used the existing offline
  `local_paper` replay path only. Its six replay cells did not read a KIS
  credential, call a broker/account endpoint, create an intent, or widen an
  Execution route.
- The completed six-symbol CPU control likewise used broker-free `local_paper`
  replay only. Its twelve fixed replay cells were independently reconstructible
  and flat after replay; no KIS credential, account/order endpoint, intent, or
  Paper action was involved.
- The completed daily catch-up emitted an external source-safe `drained`
  receipt with `client_constructed: false`; it had no account, position, intent,
  order, cancellation, modification, or live effect. Its next offline event
  window remains an input contract only, not an Execution route change.
- The active v2 joint event-window contract fresh-imports without Data or
  Execution modules and its metadata-only script path is equally pure. Its
  artifact is candidate-only with `review_unavailable`; it has no credential,
  account, order, intent, local-paper replay, or live effect.
- Its reattested `expanding-1` fold input is equally offline and non-executable.
  It exposes only catalog lineage, segment bounds, and exact sparse indices
  after the parent hash/rebuild comparison; it cannot be selected from an
  unverified artifact object and has no KIS, Tiingo, account, intent, replay,
  or live path.

## Ready Queue

1. Keep the completed decision-to-target-weight-to-local-paper-intent contract
   stable while Data and Research build the D1 materializer for the reattested
   offline fold input. Its replay and route-isolation tests are the current
   integration evidence.
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
binding and route boundaries intact. The next fold-local materializer is
offline; do not let it acquire an account, order, KIS, Tiingo, or replay path.
