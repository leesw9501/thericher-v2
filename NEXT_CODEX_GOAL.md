# Next Codex Goal

## Objective

Build `intraday-head-capture-receipt-binding-v1`: make the existing
intraday-head terminal receipt cryptographically bind only its same-run
source-safe session-capture cumulative-coverage receipt, so offline
reattachment can report categorical coverage without reading raw bars or
choosing a newest artifact.

The 2026-08-07 04:24 KST task advanced its terminal pointer: collection exited
zero and the exact QQQ Paper-only session was `no_intent`, but offline
validation was `unavailable`; terminal recovery is
`prospective_validation_payload_unavailable` with Scheduler result `20`.
No coverage claim is available because the current terminal contract lacks an
exact capture-receipt binding. A fresh Claude falsification check returned
`supported-with-limits`: binding must include the same schedule run identity,
preserve old receipts as explicitly unbound rather than corrupt, and prevent a
stale but internally consistent pointer rollback. It establishes provenance
only, never data qualification.

## Hard Boundaries

- Do not manually call KIS, invoke or duplicate an intraday task, or submit or
  modify any Paper order.
- Preserve installed task identity, timing, `IgnoreNew`, and broker routes.
- Do not alter data semantics, raw-data retention, model eligibility,
  Paper/live authority, dashboard, capital rule, or live behavior.
- Do not log, store, or expose raw bars, prices, provider payloads,
  credentials, accounts, intents, order IDs, or `KIS_LIVE_*`.
- The existing task alone owns the next 06:20 KST execution.

## Required Work

1. Use the recorded Claude `supported-with-limits` falsification check before
   the provenance/recovery contract change. Reconsult only if the proposed
   contract materially expands; categorize an unavailable invocation only as
   `review_unavailable`.
2. Make a new session-capture receipt carry its owning schedule `run_id` and
   add a minimal source-safe terminal chain: capture time, immutable full
   SHA-256, and categorical cumulative-coverage digest/category only.
3. Make the offline reader verify pointer -> terminal receipt -> deterministic
   exact capture receipt -> run identity -> hash/digest. It must use only the
   caller-supplied guarded cache root, require direct regular files, require
   capture time no later than terminal time and the same ET session date, and
   reject mismatches, links/reparse surfaces, timestamp conflicts, and
   latest-artifact selection.
4. Preserve existing receipts as `legacy_unbound` without attaching coverage.
   Reject stale pointer rollback while preserving the existing single-task
   writer. Add focused tests for normal binding, legacy behavior, and every
   rejection case.
5. Build the existing image through the normal local path only if required for
   the next task-owned run; do not change the task definition. Reattach the
   existing 06:20 task outcome only if it occurs during this objective;
   otherwise preserve its `next_due` and continue another ready,
   non-conflicting package.

## Verification

Run focused binding tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Bind intraday coverage receipt to terminal evidence`
