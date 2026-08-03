# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build `kis-spy-paginated-prefix-capability-v1`: an isolated, source-safe Data
capability probe that can determine whether a fresh, paginated SPY 1m
09:30--15:30 ET prefix can be captured and verified inside the frozen
15:30--15:31 ET validity interval.

This is a timing-and-coverage feasibility experiment only. It must not change
the existing `thericher-kis-paper-intraday-head` schedule, prospective-SPY
baseline TTL, virtual-Paper route, model selection, PnL, or GPU eligibility.

## Boundaries

- KIS Paper market-data reads through one new named, goal-owned Data worker and
  scheduler are standing-authorized. Do not use account, position, quote,
  order, submit, modify, cancel, reconciliation, or any live route. Never read
  or route `KIS_LIVE_*`.
- Preserve the existing head collector and its Paper-cycle behavior. The new
  worker owns a dedicated cache and artifact namespace outside Git; it must not
  reuse a warm partial cache as fresh evidence.
- Keep raw market data only under `D:\market_data` and generated receipts only
  under `D:\thericher-v2\model-artifacts`. Never log secrets, account IDs, raw
  rows, prices, request URLs, private intents, or broker bodies.
- The observer stage is data-only: network disabled, read-only market-data
  mount, no execution import, no KIS credential environment, and no Paper or
  local-paper behavior.
- Use raw serialized UTC and America/New_York timestamp strings as primary
  evidence. Do not host-local-convert Eastern timestamps.

## Required Work

1. **Data:** implement a bounded same-client paginated collection/capture path
   with explicit continuation, page-seam, complete-minute, and fresh-run
   binding facts. It may attempt at most four 120-row pages for the one SPY
   session; a missing continuation or incomplete prefix is a truthful scoped
   result, not a retry flood.
2. **Timing:** add an ET-gated, DST-safe owned scheduler path. It runs a
   data-only 15:29:30 ET negative control and a separate actual 15:30 ET
   feasibility observation; the irrelevant KST trigger is a no-network no-op.
   Record collection start, return, and observer finish in UTC plus serialized
   Eastern offset/DST form.
3. **Negative control:** the 15:29:30 path must never claim a complete 15:30
   prefix. Treat such a claim as a stale-cache/timestamp kill result that
   invalidates any later positive observation from this path.
4. **Success contract:** a positive result requires successful fresh collection,
   continuous completed 09:30--15:30 coverage across verified page seams, and
   all capture-path timestamps before 15:31 ET. Name it only
   `availability_within_validity_after_collection`.
5. **Isolation:** add focused tests proving no broker/account/quote/order/local
   paper/live access, no credential read in the observer, no raw-data/artifact
   escape to Git, and correct daylight/standard-time dispatch. Keep the
   existing forward-pair DST issue separate; do not repair it in this goal.
6. **Integration:** retain `decision_time_availability: not_observed` unless a
   later dedicated evidence contract justifies a narrower claim. A runtime
   failure or absent market session is Data evidence only and must not pause
   independent Engine work.

## Completion Evidence

- host and isolated Docker tests cover pagination, stale-cache negative
  control, DST dispatch, timing bounds, and execution isolation;
- the new scheduler is installed without changing the existing head task;
- one source-safe runtime receipt is reattested when its owned session occurs,
  or its explicit `next_due` and independent ready work are left to the worker;
- required verification, commit, and push complete; then replace this file
  with exactly one next company objective.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
```
