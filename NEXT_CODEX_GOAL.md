# Next Codex Goal

## Objective

Reconcile the first natural QQQ runtime-freshness cycle after the scoped
intraday-head schedule deployment, using only source-safe task, terminal,
session, and validation facts.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `RUNBOOK.md`, and the active stateboards.
2. Inspect the one existing `thericher-kis-paper-intraday-head` task before
   interpreting its output. Its natural next due time is worker-owned; do not
   manually invoke, duplicate, disable, or reschedule it.
3. Treat the prior `runtime-freshness-v2` reattachment as historical evidence,
   not a fresh market input.

## Work

1. **Data:** after one natural post-deployment task reaches a terminal state,
   read only the allowlisted head-index and terminal receipt metadata needed to
   establish the scheduled run identity, categorical collection status, cache
   generation/counts, and conflict state. Do not print or copy raw rows.
2. **Execution:** read only the paired source-safe QQQ session and validator
   outcome fields needed to establish whether the fresh runtime deadline yielded
   a truthful no-intent, local replay, or virtual-Paper lifecycle. Never force a
   new account, quote, order, cancellation, or reconciliation request to make a
   result appear.
3. **Validation:** prove that the observed terminal receipt is newer than the
   scoped deployment, links only to the named worker chain, and did not create a
   second scheduled task or unknown duplicate intent. Reattest the validator
   only if its own normal worker path produced an exact session identity.
4. If the worker is still running or has a scoped technical failure, preserve
   its source-safe task state and classify only that worker's recovery path. Do
   not foreground-wait, manually retry it, widen the two-minute deadline, or
   turn its outcome into a model result.

## Boundaries

- `KIS_PAPER_*` remains standing-authorized only through the installed worker.
  Do not read or route `KIS_LIVE_*`.
- No manual KIS/broker call, no new scheduler, no duplicate task, no paid work,
  no raw-row/account/broker-body disclosure, and no live behavior.
- A scheduler due time, stale input, no-intent, or scoped recovery result is not
  an operator approval hold or a stop for other ready lanes.
- Keep market data under `D:\market_data` and artifacts under
  `D:\thericher-v2\model-artifacts`.

## Completion

- One source-safe post-deployment terminal state is classified as `complete`,
  `recovery`, or still-running with an exact owner and next recovery action.
- The named task's runner, trigger count, `IgnoreNew`, and virtual-only route
  remain intact; no duplicate task or manually manufactured call exists.
- Stateboards identify the actual evidence and the next ready independent work,
  not a foreground wait.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective.

## Suggested Commit Message

`Reconcile scheduled QQQ freshness cycle`
