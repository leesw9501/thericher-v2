# Data Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Data projection, not a ledger.

## Ownership

Own provider behavior, acquisition, provenance, calendars, symbols, canonical
storage, resampling, manifests, temporal splits, and data-quality evidence.
Do not select strategies or make execution decisions.

## Current Objective

Integrate the tested KIS Paper intraday session-capture path with the one
existing intraday-head task while preserving source separation, cache
correctness, and the isolated prospective-observer handoff. The prospective
QQQ 1m first-five pair is one Data product for a named future observer; it is
not the only Data output or a company hold.

## Current Facts

- The private daily cache has a QQQ/SPY common historical intersection of
  4,756 sessions and a QQQ/SPY/IWM intersection of 694 sessions. IWM is
  source-limited at its qualified bad-row boundary.
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
- D: free space is about 40.45 percent. Data acquisition remains within the
  existing 20 percent warning and 15 percent floor policy.

## Ready Queue

1. Rewire only the existing `thericher-kis-paper-intraday-head` task/profile to
   invoke the tested `session-capture` mode. Do not create a task, trigger, or
   independent scheduler.
2. Preserve the one-client, concurrency-one collector, existing request gate,
   cooldown, lock, strict conflict handling, and `tr_cont` continuation
   contract. A terminal page remains current-head evidence only.
3. Preserve the existing isolated preparation and observation handoff: a
   qualified QQQ result may prepare its immutable pair, while a partial or
   extended-session capture remains source evidence and cannot enter Research.
4. Add profile/dispatcher tests proving that the collector outcome stays
   authoritative, the observer remains network-disabled, and no account,
   order, or live route is introduced.
5. Continue normal daily/intraday cache work when its owned cursor is ready.
   Hand an immutable first-five pair to the isolated prospective observer only
   when the exact 390-minute Data contract is satisfied.

## Durable Constraints

- Market data stays under D:\market_data and never enters Git.
- Never fill, relabel, or repair KIS rows with another provider's data.
- A partial, gapped, conflicting, or timestamp-unqualified session cannot
  become a prospective regular-session Research input.
- A capability probe is finite and calibrated. It is not permission for an
  unbounded retry loop or parallel request flood.

## Recovery

Current class: resume. Validate existing metadata and committed snapshots before
a network call. A bad cache is reconcile/restart evidence for that cache; an
empty or limited endpoint result is source evidence for that route only.

## Next Handoff

Return the integrated profile/dispatcher evidence and the exact effect on Data
coverage. Do not infer historical reach or prospective completeness from a
terminal-head page, and do not wait for a prospective pair before advancing
other ready Data work.
