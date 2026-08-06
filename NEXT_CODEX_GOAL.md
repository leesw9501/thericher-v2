# Next Codex Goal

## Objective

Build `intraday-qqq-v4-scheduled-validation-observation-v1`: reattach one
exact task-owned intraday QQQ terminal/session/validation chain after the
existing 2026-08-07 06:20 KST invocation, and classify it as a deterministic
source-safe validation result or its exact local recovery category.

`intraday-qqq-offline-validation-reliability-v1` is complete. Its v4
validator emits the top-level `status: validated` consumed by the scheduler and
binds it into a new immutable validation identity. The historical 04:24 KST
v3 terminal remains `recovery/prospective_validation_payload_unavailable` and
`legacy_unbound`; do not rewrite it.

## Hard Boundaries

- Do not manually call KIS, invoke or duplicate any task, submit/modify/cancel
  a Paper order, or read any credential or `KIS_LIVE_*` value.
- Preserve installed task identity, timing, `IgnoreNew`, broker routes, and
  raw-data retention.
- Do not expose raw bars, prices, provider payloads, credentials, accounts,
  intents, order IDs, or secret-like values in Git, logs, artifacts, or
  review prompts.
- Do not turn a missing or malformed session record into a validated result,
  model claim, coverage qualification, Paper permission, or GPU campaign.

## Required Work

1. After the existing task completes, begin at its exact source-safe terminal
   pointer and verify the immutable terminal, capture binding, QQQ session ID,
   and same-ID v4 validation artifact without scanning for a latest session or
   raw cache data.
2. Record only categorical evidence: task result, terminal status/recovery,
   QQQ session status, validation status/contract, identity match, and
   capture-binding class. A valid QQQ `no_intent` with v4 `validated` is a
   validation fact only, not a data-quality, model, PnL, or Paper conclusion.
3. Preserve distinct recovery for missing, malformed, stale, unsafe, or
   mismatched evidence. Do not repair, relabel, or overwrite the historical
   v3 receipt, and do not make a false success from an absent artifact.
4. Keep the observation offline and side-effect-free. Reuse the existing task,
   validator, and services; do not add a scheduler, route, worker, public
   surface, KIS call, broker action, or local-Paper mutation.
5. Do not wait in the foreground for 06:20 KST. Retain the task-owned
   `next_due` fact and continue any ready non-conflicting package. If the task
   has not run before a bounded package boundary, keep its observation pending
   without treating it as an operator block.

## Verification

Run any focused reader/projection tests changed by this objective, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Observe intraday QQQ v4 validation`
