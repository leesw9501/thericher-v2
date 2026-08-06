# Next Codex Goal

## Objective

Build `intraday-head-0424-source-safe-followup-v1`: after the existing
2026-08-07 04:24 KST intraday-head task runs, reattach only its exact
source-safe terminal pointer, matching immutable receipt, Scheduler result,
and any matching offline QQQ/session/coverage facts. This advances the data
collection loop by recording measured coverage or a scoped recovery without
turning either into a model, Paper lifecycle, fill, PnL, alpha, or promotion
claim.

The completed prior objective added pure same-cycle target allocation: it
preserves caller order, requires one shared snapshot and unique identities, and
uses capacity only for accepted enters. It has no data, model, KIS, Paper, or
broker surface; its Claude review was `review_unavailable`.

## Hard Boundaries

- Do not manually call KIS, invoke or duplicate the intraday-head task, submit
  or modify Paper orders, or alter a scheduler, broker route, order behavior,
  credential path, dashboard, Docker/runtime, capital rule, or live behavior.
- Do not inspect or retain raw market data, secrets, account facts, private
  intents, order identifiers, or provider payloads. Never read or expose
  `KIS_LIVE_*`.

## Required Work

1. After the existing task completes, hash-validate its one task-owned current
   pointer and matching immutable terminal receipt. Read the installed task's
   categorical Scheduler result without inspecting its action arguments.
2. Reattach only categorical collection, cumulative regular-session coverage,
   QQQ-session, validation, terminal, and recovery facts. If an exact matching
   offline validator exists, confirm its identity internally and report only its
   category and contract; do not print IDs or paths.
3. Preserve a scoped recovery exactly and let the task own its own future run.
   Do not retry, change pacing, or convert a failed input into an operator
   approval or a global lane hold.
4. While the task is due, continue only a truly ready non-conflicting package.
   Do not foreground-wait, manufacture a duplicate experiment, or alter a
   scheduler merely to observe this one outcome. Refresh stateboards and this
   file before ending.

## Verification

Run focused receipt/coverage reattachment tests, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Reattach 04:24 intraday coverage receipt`
