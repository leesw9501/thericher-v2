# Next Codex Goal

Read `HANDOFF.md`, `VISION.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`,
`RUNBOOK.md`, and the active `agents/` stateboards first. Then continue from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Complete `kis-spy-scheduled-timing-observation-v1`: consume the first real
source-safe receipts produced by the existing `thericher-kis-paper-intraday-head`
task and establish the bounded current facts for its 13:31 ET and 15:31 ET
summer-time runs.

The product outcome is an evidence-backed account of current collector timing
and post-collection prefix state. It must not infer 15:30 decision-time
availability, change cadence or receipt validity, or become a strategy or
Paper-trading result.

## Boundaries

- Let only the existing owned scheduler make KIS Paper market-data calls. Do
  not start a collector manually, create a duplicate worker/cache, or widen
  the target scope beyond the existing SPY/QQQ head collection.
- Do not call or read KIS account, position, quote, order, submit, modify,
  cancel, reconciliation, or live routes. Never read or route `KIS_LIVE_*`.
- Consume only external source-safe receipts and scheduler metadata. Do not
  retain or display credentials, raw bars, prices, request URLs, account
  identifiers, or broker payloads.
- Preserve the current trigger times, frozen prospective-SPY baseline,
  exclusive validity, virtual-Paper route, and terminal schedule behavior.
  No single receipt is authority to change any of them.
- The scheduler-owned session due times are not foreground waits. Dispatch any
  ready offline review or recovery package while they remain pending.

## Required Work

1. **Data:** reattest the first scheduled timing receipts and task outcomes.
   Record the exact safe timing/offset/category/count facts, receipt lineage,
   and any scoped collector recovery fact. Distinguish an early-before-cutoff
   run from an at-or-after-expiry run.
2. **Engine Research:** verify that every interpretation retains
   `decision_time_availability: not_observed`; classify only what the frozen
   15:30 decision can and cannot infer from each receipt.
3. **Execution:** reattest that the observed schedule runs made no account,
   quote, order, canary, local-paper, or live route. Do not alter the adapter.
4. **Integration:** if both current summer-time observations are available,
   write one compact Data/Engine recommendation for a later, separately
   approved schedule/validity design experiment. If either remains pending or
   source-limited, preserve its owned `next_due`/recovery state and continue
   another ready lane rather than creating a wait.
5. Ask Claude for a short falsification-first challenge before treating two
   observed receipts as grounds for a schedule, availability, or Paper-route
   proposal. A timeout is `review_unavailable`, not agreement or a block.

## Completion Evidence

- source-safe reattestation of the relevant external timing receipts and task
  outcome(s), with no raw/provider/account/order output;
- focused tests if parsing, isolation, or interpretation code changes;
- refreshed Data, Engine Research, Execution, Research Steward,
  orchestration, and handoff stateboards; required verification, commit, and
  push;
- if a receipt is still not due, durable scheduler-owned `next_due` plus all
  ready offline evidence is a bounded completion state, not a foreground hold.

## Verification

```powershell
uv run --extra dev pytest -q <changed focused tests>
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile kis-paper-intraday-head config --quiet
```
