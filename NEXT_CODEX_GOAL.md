# Next Codex Goal

## Objective

Build `kis-intraday-schedule-receipt-qqq-session-identity-followup-v1`:
reattach one exact result from the existing intraday-head task's 2026-08-07
02:28 KST invocation after the host-only QQQ safe-ID receipt repair. Preserve
the matching task-owned terminal receipt and offline validation fact exactly;
it may be complete or scoped recovery and must never become an alpha,
fill-quality, PnL, or model-promotion claim.

The preceding 00:29 KST task is immutable
`recovery/prospective_session_id_unavailable` with Scheduler result `20` after
collection `exit_zero` and QQQ `no_intent`. The repaired dispatcher and existing
profile images are verified offline. Do not infer a runtime result from code or
rerun the task manually.

## Hard Boundaries

- Do not manually invoke KIS or duplicate the existing intraday-head task.
- Do not add or change a scheduler, broker route, order behavior, capital rule,
  credential path, dashboard, or live behavior.
- Do not read or expose `KIS_LIVE_*`, secrets, account facts, private intents,
  order identifiers, or raw market data.
- Preserve prior task-owned receipts and pointers. Inspect only the one current
  source-safe pointer, matching immutable receipt, Scheduler result, and the
  matching existing offline validator fact.

## Required Work

1. After the existing 02:28 KST task runs, read and hash-validate only its
   source-safe terminal pointer and matching immutable receipt.
2. Reattach only categorical collection, QQQ-session, validation, terminal, and
   Scheduler facts. Do not inspect raw inputs or broker payloads.
3. If the task reports a scoped recovery, preserve its exact reason and keep it
   local; do not retry or turn it into an approval wait.
4. While waiting, continue only ready non-conflicting private work. Do not
   foreground-wait for the task.
5. Refresh stateboards and this file before ending the goal.

## Verification

Run focused reattachment tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reattach intraday receipt follow-up`
