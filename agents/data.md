# Data Agent Stateboard

AGENTS.md owns policy and NEXT_CODEX_GOAL.md owns the company objective. This
is the current Data projection, not a ledger.

## Ownership

Own provider behavior, acquisition, provenance, calendars, symbols, canonical
storage, resampling, manifests, temporal splits, and data-quality evidence.
Do not select strategies or make execution decisions.

## Current Objective

Implement the first measured KIS Paper intraday session-capture path while
preserving source separation and cache correctness. The prospective QQQ 1m
first-five pair is one Data product for a named future observer; it is not the
only Data output or a company hold.

## Current Facts

- The private daily cache has a QQQ/SPY common historical intersection of
  4,756 sessions and a QQQ/SPY/IWM intersection of 694 sessions. IWM is
  source-limited at its qualified bad-row boundary.
- The bounded historical intraday cache has 21 complete QQQ and SPY
  regular-session inputs. It remains source-scoped historical evidence.
- The prospective QQQ head is generation 8 with zero complete sessions out of
  five. Short/gapped records and minute_duplicate_conflict are source facts,
  not a Research or Execution hold.
- The existing intraday-head task has four KST triggers and owns its current
  cache. It may continue independently while the capability package runs.
- The 2026-07-26 source-safe QQQ probe accepted two full terminal-head pages,
  reused one in-memory Paper token, and stayed within the current request gate.
  It observed a gap within one exchange date. It did not prove historical
  pagination, a higher request ceiling, or a complete 390-minute session; raw
  bars were not retained by the probe. Evidence:
  `20260726T123512436025Z-f1575006a7319021.json` under the external artifact
  root.
- D: free space is about 40.45 percent. Data acquisition remains within the
  existing 20 percent warning and 15 percent floor policy.

## Ready Queue

1. Implement one owned, concurrency-one session-capture worker around one
   in-memory KIS Paper market-data client/token per bounded invocation. Keep
   the existing request gate and cooldown unchanged.
2. Treat `tr_cont` as the only continuation authority. Continue only when it
   is present; on a terminal page collect current-head evidence only and never
   synthesize a historical `KEYB` cursor.
3. Persist raw provider rows, manifests, provenance, deduplication, and
   recovery state only under D:. Write source-safe coverage facts including
   complete/partial/gapped regular-session status and the 390-minute contract.
4. Add fake-transport tests for token/client lifetime, continuation versus
   terminal-head behavior, strict conflict handling, coverage classification,
   bounded recovery, and no account/order/live route.
5. Run one bounded Data-only KIS Paper smoke after the worker is implemented.
   A market-time wait, a partial session, or a rate retry remains owned by that
   worker and cannot block another lane.
6. Continue normal daily/intraday cache work when its owned cursor is ready.
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

Return the tested worker, a source-safe smoke result, and the exact effect on
Data coverage. Do not infer historical reach or prospective completeness from
a terminal-head page, and do not wait for a prospective pair before advancing
other ready Data work.
