# Next Codex Goal

## Objective

Build `kis-intraday-schedule-receipt-qqq-session-identity-v1`: repair the
existing intraday-head host dispatcher so its already validated safe QQQ
prospective session ID and matching offline-validation session ID reach the
existing terminal schedule receipt. Prove a valid task-owned `no_intent`
session can complete its offline validation and terminal receipt, while absent,
conflicting, or mismatched identities remain scoped recovery results.

The preceding 2026-08-07 00:29 KST task result is exactly collection
`exit_zero`, QQQ session `no_intent`, terminal
`recovery/prospective_session_id_unavailable`, and Scheduler result `20`.
Its data, Paper, fill, PnL, alpha, and model status remain unchanged. The cause
is host receipt argument omission, not a reason to rerun the task or infer a
broker outcome.

## Hard Boundaries

- Do not manually invoke KIS or duplicate the existing intraday-head task.
- Do not add or change a scheduler, broker route, order behavior, capital rule,
  credential path, dashboard, or live behavior.
- Do not read or expose `KIS_LIVE_*`, secrets, account facts, private intents,
  order identifiers, or raw market data.
- Preserve the exact prior task-owned receipt and pointer; tests use only
  synthetic or existing source-safe fixtures.

## Required Work

1. Add the smallest host-dispatcher argument wiring for already validated safe
   QQQ session IDs only when present.
2. Add focused tests for successful `no_intent` plus offline-validation receipt
   completion, and for absent, conflicting, or mismatched IDs remaining
   recovery.
3. Run a network-disabled host/receipt simulation. Do not call KIS.
4. Rebuild only the existing intraday-head profile services after verification
   so the next task-owned run uses the committed source.
5. Record the bounded result and Claude's `review_unavailable` timeout in the
   relevant stateboards. Refresh this file before ending the goal.

## Verification

Run the focused tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Repair intraday schedule receipt handoff`
