# Data Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Data projection, not a ledger.

## Ownership

Own provider behavior, acquisition, provenance, calendars, symbols, canonical
storage, resampling, manifests, temporal splits, and data-quality evidence.
Do not select strategies or make execution decisions.

## Current Objective

Calibrate the private KIS Paper data-ingress pace, then use the resulting
evidence to advance the owned daily or intraday collector that has a ready
cursor. Keep the reattested QQQ/SPY daily catalog available to frozen offline
Research contracts. The prospective QQQ 1m first-five pair is one Data product
for a named future observer; it is not the only Data output or a company hold.

## Current Facts

- The private daily cache has a QQQ/SPY common historical intersection of
  4,756 sessions and a QQQ/SPY/IWM intersection of 694 sessions. IWM is
  source-limited at its qualified bad-row boundary.
- On 2026-07-26, the existing offline daily loader reattested the exact QQQ/SPY
  pair with index hash `sha256:e0bb...01ac660` and full dataset hash
  `sha256:78b0...397718`. It exposed only the pair's common panel with
  `MODP=0_unadjusted` and the existing corporate-action limitation; it made no
  KIS call, raw scan, source blend, or IWM read. Research consumed only its
  derived chronological phase slices.
- The bounded historical intraday cache has 21 complete QQQ and SPY
  regular-session inputs. It remains source-scoped historical evidence.
- The prospective QQQ head is generation 10 with zero complete sessions out
  of five. Short/gapped records and minute_duplicate_conflict are source
  facts, not a Research or Execution hold.
- The existing intraday-head task has four KST triggers and owns its current
  cache. It may continue independently while the capability package runs.
- The 2026-07-26 source-safe QQQ probe accepted two full terminal-head pages,
  reused one in-memory Paper token, and stayed within the current request gate.
  It observed a gap within one exchange date. It did not prove historical
  pagination, a higher request ceiling, or a complete 390-minute session; raw
  bars were not retained by the probe. Evidence:
  `20260726T123512436025Z-f1575006a7319021.json` under the external artifact
  root.
- The first `session-capture` worker reuses the existing collector, one
  in-memory Paper market-data client/token, lock, request gate, and head cache.
  Its capture receipt is D:-resident, source-safe, and scoped only to the QQQ
  manifest from that invocation, so a legacy completed chunk cannot make a new
  attempt appear complete. The bounded smoke wrote
  `20260726T131355216487Z-cb15a58ccd594f44.json`; its terminal extended-session
  data qualified zero of 390 regular-session minutes. The QQQ capture transport
  result was complete while its coverage correctly remained input-pending.
- The one existing intraday-head Docker profile now invokes `session-capture`.
  Its four KST triggers, task identity, lock, request controls, page cap,
  observer isolation, and collector-exit authority are unchanged. An eligible
  QQQ result also retains the existing metadata-only preparation handoff. No
  scheduled run under this configuration has been claimed yet.
- D: free space is about 40.45 percent. Data acquisition remains within the
  existing 20 percent warning and 15 percent floor policy.
- The current 1.25-second request-start gate and 60-second categorical cooldown
  are temporary, measured controls after an `EGW00201` observation; they are
  not a verified daily quota. The five-minute token-start guard applies only to
  a new token request and never asks a worker to sleep for five minutes.

## Ready Queue

1. Inventory ready daily and intraday cursors from their metadata, then run one
   bounded single-client pace calibration. Record only source-safe request,
   accepted-page, categorical-limit, elapsed-time, and tested-interval facts.
2. Keep the current gate and cooldown until a calibration fact supports a
   change. Test one pacing variable at a time; do not create a second collector
   against the same cache or a parallel request flood.
3. Use the resulting evidence to run the existing finite catch-up or
   session-capture worker when its cursor is ready. Preserve the one-client,
   concurrency-one collector, lock, strict conflict handling, and `tr_cont`
   contract.
4. Keep partial or extended-session capture rows out of Research. Hand an
   immutable first-five pair to the isolated prospective observer only when the
   exact 390-minute Data contract is satisfied.

## Durable Constraints

- Market data stays under D:\market_data and never enters Git.
- Never fill, relabel, or repair KIS rows with another provider's data.
- A partial, gapped, conflicting, or timestamp-unqualified session cannot
  become a prospective regular-session Research input.
- A capability probe is finite and calibrated. It is not permission for an
  unbounded retry loop or parallel request flood.
- Treat token issuance, page pacing, and worker scheduling as separate facts.
  A `token_request_not_due` result yields this worker; it does not impose a
  five-minute foreground wait or block another ready collector/lane.

## Recovery

Current class: resume. Validate existing metadata and committed snapshots before
a network call. A bad cache is reconcile/restart evidence for that cache; an
empty or limited endpoint result is source evidence for that route only.

## Next Handoff

Return the KIS pace calibration and any resulting finite collection evidence,
then preserve the pair-only daily source contract for a future explicitly
frozen campaign. Do not infer historical reach or prospective completeness from
a terminal-head page, and do not wait for a prospective pair before advancing
other ready Data work.
