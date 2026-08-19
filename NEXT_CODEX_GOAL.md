# Next Codex Goal

## Objective

Complete `kis-intraday-head-collection-dispatch-boundary-v1`: add one closed,
source-safe boundary around the existing task-owned Docker collection dispatch
so a future immutable invocation can distinguish an unreached dispatch from a
returned Docker command. This narrows the existing
`collection_exit_nonzero / reason_unavailable` recovery path without claiming a
container start, KIS call, provider cause, session completeness, finality, or
model eligibility.

## Boundaries

- Before changing the existing dispatcher/receipt boundary, obtain a concise
  falsification-first Claude drift-check. Its result narrows only this recovery
  instrumentation; it cannot authorize scheduler, timing, pacing, route,
  credential, or Paper behavior changes.
- Do not manually invoke, modify, reinstall, or start a Windows task, Docker
  service, collector, KIS route, broker route, or scheduler. Do not read
  `.env`, credentials, `KIS_LIVE_*`, raw market rows, private runtime state,
  Docker output, or task output.
- Keep the existing task definition, trigger times, run limit, Docker profile,
  collector command, page cap, retry/pacing, KIS route, and later conditional
  Paper branch behavior exactly unchanged. No new scheduler or worker.
- The new markers must be immutable, root-relative, allowlisted, and bind to
  the existing opaque invocation lineage. Retain only timestamps, closed stage
  categories, hashes, and source-safe relative evidence pointers; never command
  text, output, secret, account, market, broker, or private-state content.

## Required Work

1. Freeze the exact existing dispatch call and the smallest closed taxonomy for
   `not_reached`, `dispatch_started`, `dispatch_returned_zero`,
   `dispatch_returned_nonzero`, and `unavailable`. Prove that a dispatch marker
   means only host-side call boundary, never container entry, collector start,
   KIS activity, or provider outcome.
2. Add a small default-deny writer/reader pair that binds `dispatch_started` and
   `dispatch_returned_*` to the existing invocation before a future task-owned
   terminal can consume them. A malformed, missing, duplicate, stale, or
   cross-run marker must read as `unavailable` and leave the existing terminal
   classification unchanged.
3. Add focused tests for exact lineage/hash binding, no-output/no-secret
   retention, default-deny failure behavior, and preservation of the existing
   collection/Paper branch and nonzero exit semantics. Do not create a task run
   as test evidence.
4. Update only the relevant Data, Execution, orchestration, `HANDOFF.md`, and
   `RUNBOOK.md` contracts. A later task-owned result is the sole evidence for
   runtime observation; do not use a current/latest artifact selector to
   manufacture one during this objective.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- Claude challenge and a frozen closed dispatch taxonomy, plus source-safe
  writer/reader tests that reject missing, duplicate, malformed, stale, or
  cross-run markers.
- The existing installed route has unchanged command/profile/timing/pacing and
  Paper behavior by source-level tests; no Task, Docker, KIS, broker, raw data,
  model, GPU, order, PnL, or live action occurs in this objective.
- A future result can report host-side dispatch boundary only; it cannot be
  overinterpreted as Docker/container, collector, provider, or market evidence.
