# Next Codex Goal

## Objective

Complete `kis-intraday-task-path-failure-localization-v1`: add the smallest
future-only, source-safe classification that can distinguish a dispatcher/config
failure from a collector/provider failure for an existing intraday-head task
path that ends nonzero. Preserve the exact stage exit code and never turn the
current `collection_exit_nonzero` fact into a root-cause claim.

## Hard Boundaries

- Do not manually invoke a Task Scheduler task, KIS, Docker service, collector,
  or scheduler. A later validation remains owned by the existing task.
- Never read credentials, `KIS_LIVE_*`, raw market rows, account values,
  private intents, broker bodies, order identifiers, command output, or
  exception text.
- Do not change task triggers, page counts, collector locks, request pace,
  downstream QQQ/SPY consumers, Docker services, KIS routes, or Paper behavior.
- Preserve every existing invocation marker and schedule terminal as immutable.
  The 2026-08-19 KST exact bound task-path nonzero remains
  `reason_unavailable`, not backfilled or rewritten.
- A retained reason must use a closed allowlist of category constants. Unknown,
  malformed, multiple, or free-text-looking output must remain
  `reason_unavailable`; it must never be sanitized, truncated, or persisted.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Inventory the current dispatcher and schedule-receipt stage contract using
   source only. State exactly which safe existing stage facts are already
   available and which causal distinction is absent.
2. Add one narrow, networkless classifier for future collection-service output.
   It may accept only an exact allowlisted structured category that already
   belongs to the collector contract; it must reject any arbitrary line,
   free-text exception, secret-like string, unknown status, or ambiguous output.
3. Bind the optional category to a new future immutable terminal/marker path
   without altering existing receipts, terminal exit codes, task configuration,
   or collector behavior. The existing offline reader must expose only the
   category or `reason_unavailable`.
4. Add focused synthetic tests proving that dispatcher/config and
   collector/provider categories stay distinct, source-free text cannot enter a
   receipt, old evidence remains unchanged, and the reader needs no network,
   credentials, Docker, KIS, or raw market data.
5. Ask Claude for a falsification-first challenge before relying on a category
   to propose any collection behavior change. No timing, paging, pace, or
   consumer change belongs to this objective.

## Verification

Run focused receipt/runner/classifier tests for any changes, then the
goal-boundary authority group, Ruff, and credential-free Compose configurations.
Report source-safe facts only and explicitly retain the assumed-honest-host,
non-cryptographic Scheduler-origin limitation.
