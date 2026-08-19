# Next Codex Goal

## Objective

Complete `kis-paper-daily-broad-continuation-capability-v1`: determine whether
the existing KIS Paper daily-broad durable cursor can make real persisted-page
and monotonic cursor progress through one short, serial, direct Compose
continuation. This advances external data collection only. The current-listing,
non-PIT breadth cache remains source-local and cannot become a predictive,
ranking, ensemble, Paper, or live claim through this objective.

## Boundaries

- `KIS_PAPER_*` reads for the named existing daily-market-data collector are
  standing-authorized. Never read or route `KIS_LIVE_*`, and do not call
  account, position, order, cancel, modify, broker, or live endpoints.
- Use only the existing `kis-paper-daily-broad-backfill` Compose service and
  checked-in `scripts/backfill_kis_paper_daily_broad.py` continuation path.
  Do not create, change, start, or invoke a Windows task/scheduler; do not
  build, pull, add a service, use a parallel flood, or launch a long worker.
- The one direct worker is capped at `--max-chunks 8` and
  `--max-runtime-seconds 900`. Its durable cache worker lock and cursor lease
  are authoritative; any advisory active-process check cannot authorize a
  second writer. Do not retry this objective.
- Reattest `THERICHER_MODE=off`, current-listing-only/non-PIT/non-ranking
  scope, external `D:\market_data` and artifact roots, and the service's
  market-data-only credential surface before execution. Keep all raw bytes only
  under `D:\market_data`; do not print, log, artifact, or Git raw rows,
  credentials, account identifiers, or private runtime state.
- Retain only source-safe aggregate counts, closed categories, safe cursor date
  categories, timestamp, opaque evidence hash/pointer, and route-isolation
  facts. A no-progress, busy, token-gated, rate-limited, storage-floor, or
  source-limited result closes this short probe without a retry loop.

## Required Work

1. Reattest the existing Compose contract and focused unit tests. Run the
   collector's non-network preflight, and inspect only source-safe durable
   worker-lock/cursor metadata before the call. Record the pre-call cursor
   aggregate as a comparison point; never inspect raw daily rows.
2. Run exactly one direct Compose continuation at the fixed eight-chunk,
   900-second bound. Capture no command output beyond allowlisted source-safe
   aggregate results. The in-service lock and gate remain authoritative.
3. Reattach only the exact worker-owned external evidence. A `collected` or
   `complete` result is capability success only when it records at least one
   accepted persisted page and its durable cursor advances monotonically from
   the pre-call safe aggregate. Otherwise classify the closed result narrowly
   and do not propose a long worker from it.
4. Add only the focused reader/test required to prove the progress claim is
   impossible without persisted accepted pages and cursor advancement, and that
   the service cannot access live/account/order routes. Update Data, Engine
   Research, Execution, orchestration, `HANDOFF.md`, and `RUNBOOK.md` with the
   narrow result.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe preflight and one exact source-safe continuation outcome for
  the fixed bound, with no account/order/Paper/live call and no raw/secret
  output retention.
- Strongest kill test: a worker lock/lease collision, unchanged cursor,
  zero accepted persisted pages, wrong service/roots/mode/credential surface,
  or any live/account/order path rejects before a long worker can be proposed.
- The conclusion remains narrow: a successful probe proves only current
  source-local daily collection progress. It does not prove point-in-time
  correctness, corporate-action completeness, a qualified research input,
  model performance, PnL, Paper eligibility, or live behavior.
