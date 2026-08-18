# Next Codex Goal

## Objective

Complete `kis-intraday-failure-category-confirmation-v1`: reattach one later
task-owned intraday-head terminal written after the first post-writer category binding
`intraday-head-20260818T1924006306454Z`. Compare only its closed category with
the existing `reason_unavailable` category. This is Data diagnosis, not a
recovery action, model result, PnL claim, Paper decision, or live route.

## Hard Boundaries

- Do not manually invoke a Task Scheduler task, KIS, Docker service, collector,
  or scheduler. The later run remains owned by the existing task.
- Never read credentials, `KIS_LIVE_*`, raw market rows, account values,
  private intents, broker bodies, order identifiers, command output, or
  exception text.
- Do not change task triggers, page counts, collector locks, request pace,
  downstream QQQ/SPY consumers, Docker services, KIS routes, or Paper behavior.
- Preserve every existing invocation marker and schedule terminal as immutable.
  The 2026-08-19 KST legacy marker remains `reason_unavailable` by compatibility,
  and the first post-writer marker remains one exact `reason_unavailable`
  binding; do not rewrite, backfill, or infer either root cause.
- A category is evidence only when the current pointer, immutable terminal, and
  exact schedule receipt all validate their hashes, run ID, timestamps, and
  outcomes through the existing offline reader. A missing, old, malformed, or
  unbound marker is `unknown`, not success, busy, or failure.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Inspect only source-safe static Task facts and the current offline
   reattachment result. Supply the first post-writer marker's paired opaque run
   ID and completion timestamp as the reader baseline, then confirm that the
   eligible later run differs from `intraday-head-20260818T1924006306454Z` and
   completes strictly later before interpreting it. `marker_not_later` is
   unknown/stale-pointer evidence, never a second category binding.
2. Reattach that later immutable marker through the existing offline
   reader. Record only opaque run/timestamps, the preserved terminal stage
   outcome, one closed failure category, binding hashes, and external-root-
   relative evidence pointers.
3. Classify narrowly:
   - matching `reason_unavailable` supplies the second independently
     hash-validated category binding required for a later recovery proposal;
   - a different allowed category records only divergence and leaves recovery
     unconfirmed.
   Neither outcome identifies an exact provider, Docker, persistence,
   Scheduler, or rate cause.
4. Retain the result as Data evidence only. Do not change behavior in this
   objective. Any later category-based recovery proposal requires a fresh
   Claude falsification-first verdict after the two bindings are verified.
5. Refresh only affected stateboards, the handoff, and the runbook. Keep Engine
   Research and Execution non-promoting unless their existing independent inputs
   qualify.

## Verification

Run the focused offline reader/reattachment tests for any changes, then the
goal-boundary authority group, Ruff, and credential-free Compose configurations.
Report source-safe facts only and retain the assumed-honest-host,
non-cryptographic Scheduler-origin limitation.
