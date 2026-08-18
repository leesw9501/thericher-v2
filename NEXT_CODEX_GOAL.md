# Next Codex Goal

## Objective

Complete `kis-intraday-invocation-receipt-reattachment-v1`: reattach the first
later task-owned invocation marker from the existing intraday-head dispatcher
to determine the exact boundary between Scheduler start, collector completion,
terminal receipt, and retained M1 topology. This is a bounded Data diagnosis,
not a model, PnL, Paper decision, or live route.

## Hard Boundaries

- Do not manually invoke a Task Scheduler task, KIS, Docker service, collector,
  or scheduler. A later result remains owned by the existing task.
- Never read credentials, `KIS_LIVE_*`, raw market rows, account values,
  private intents, broker bodies, or order identifiers.
- Use only source-safe static Task facts, the validated external invocation
  pointer/immutable receipts, the existing offline terminal reader, and
  metadata-only cache topology. A missing pointer is `unknown`, not a task or
  collection outcome.
- Keep one task, one collector lock, the measured request-start gate,
  token-start guard, cooldown, and external roots. Do not add a duplicate task,
  collector, request flood, or foreground wait.
- Do not change trigger timing, page counts, downstream QQQ/SPY consumers,
  Docker services, KIS routes, or Paper behavior in this objective.
- Preserve the 2026-08-15 and 2026-08-17 immutable terminal facts. Do not
  touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Inspect only the first fresh, task-owned current invocation marker after
   this objective starts. Recompute the pointer/immutable receipt hashes and
   retain only opaque run ID, timestamps, categorical collection/terminal
   outcomes, and the exact external evidence pointer.
2. Reattach it to the matching source-safe schedule-terminal and capture-topology
   evidence. Classify narrowly as marker unavailable, start-only, terminal
   unavailable, collector nonzero, retained partial, or complete-session only
   when the exact receipts support that category. Do not infer a missed trigger
   from missing retained chunks.
3. If a fresh marker establishes a precise technical constraint, ask Claude for
   a concise falsification-first check before proposing the smallest recovery.
   Keep all downstream consumers and Task configuration unchanged unless a new
   single objective owns a measured, evidence-backed change.
4. Refresh Data, Engine Research, Execution, orchestration, HANDOFF, and
   RUNBOOK facts. Engine Research remains non-promoting unless independently
   qualified input evidence exists.

## Verification

Run focused offline reader/receipt/topology tests for any changes, then the
goal-boundary authority group, Ruff, and both Compose configurations. Report
only source-safe evidence and explicitly state the assumed-honest-host
provenance limitation.
