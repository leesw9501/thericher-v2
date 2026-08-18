# Next Codex Goal

## Objective

Complete `kis-intraday-failure-category-reattachment-v1`: reattach the first
later task-owned intraday-head terminal written after the closed failure-category
writer is installed. Preserve the existing stage exit code and distinguish only
the retained `dispatcher_config`, `collector_provider`, or
`reason_unavailable` category. This is Data diagnosis, not a recovery action,
model result, PnL claim, Paper decision, or live route.

## Hard Boundaries

- Do not manually invoke a Task Scheduler task, KIS, Docker service, collector,
  or scheduler. The later run remains owned by the existing task.
- Never read credentials, `KIS_LIVE_*`, raw market rows, account values,
  private intents, broker bodies, order identifiers, command output, or
  exception text.
- Do not change task triggers, page counts, collector locks, request pace,
  downstream QQQ/SPY consumers, Docker services, KIS routes, or Paper behavior.
- Preserve every existing invocation marker and schedule terminal as immutable.
  The current 2026-08-19 KST bound nonzero is a legacy marker and must remain
  `reason_unavailable`; do not rewrite, backfill, or infer its root cause.
- A category is evidence only when the current pointer, immutable terminal, and
  exact schedule receipt all validate their hashes, run ID, timestamps, and
  outcomes through the existing offline reader. A missing, old, malformed, or
  unbound marker is `unknown`, not success, busy, or failure.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Inspect only source-safe static Task facts and the current offline
   reattachment result. Confirm that the first later eligible run differs from
   the 2026-08-19 legacy marker before interpreting it.
2. Reattach one later immutable marker through the existing offline reader.
   Record only opaque run/timestamps, the preserved terminal stage outcome,
   one closed failure category, binding hashes, and external-root-relative
   evidence pointers.
3. Classify narrowly: a zero collection exit must expose `reason_unavailable`;
   a nonzero may expose `dispatcher_config`, `collector_provider`, or
   `reason_unavailable`. The category does not identify an exact provider,
   Docker, persistence, Scheduler, or rate cause.
4. If one later bound category is present, retain it as Data evidence only.
   Do not change behavior in this objective. Before any future recovery proposal
   based on a category, obtain a fresh Claude falsification-first verdict and
   require at least two independently hash-validated matching task bindings.
5. Refresh only affected stateboards and the handoff. Keep Engine Research and
   Execution non-promoting unless their existing independent inputs qualify.

## Verification

Run the focused offline reader/reattachment tests for any changes, then the
goal-boundary authority group, Ruff, and credential-free Compose configurations.
Report source-safe facts only and retain the assumed-honest-host,
non-cryptographic Scheduler-origin limitation.
