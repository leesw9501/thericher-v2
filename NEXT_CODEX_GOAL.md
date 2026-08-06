# Next Codex Goal

## Objective

Build `simplify-orchestration-current-projection-v1`: replace the historical
narrative in `agents/orchestration.md` with a concise, current-only
cross-lane projection. This improves the data collection, research, validation,
and paper-trading loop by making ready work, owned resources, external due
facts, the current bottleneck, and one reversible improvement immediately
dispatchable without rereading historical incidents.

The completed prior objective reattached the exact 2026-08-07 02:28 KST
intraday-head receipt as `recovery/collection_exit_nonzero` with Scheduler
result `1`; QQQ session and validation were `not_applicable`. It is retained
only as a current recovery fact, never an alpha, fill, PnL, or model claim.

## Hard Boundaries

- Do not call KIS, submit or modify Paper orders, or manually invoke any task.
- Do not add or change a scheduler, broker route, order behavior, capital rule,
  credential path, dashboard, Docker/runtime, or live behavior.
- Do not read or expose `KIS_LIVE_*`, secrets, account facts, private intents,
  order identifiers, or raw market data.
- Do not rewrite historical receipts, artifacts, source contracts, or role-lane
  implementation. Git and external artifacts retain history.

## Required Work

1. Ask Claude CLI for a short falsification-first governance drift-check before
   editing. Treat an unavailable response as `review_unavailable`, not assent.
2. Replace only the stale historical narrative in `agents/orchestration.md`
   with these current sections: company objective, Ready / Owned / Due table,
   current bottleneck, current reversible improvement, and current recovery
   action. Keep the facts needed for the next dispatch, not a chronological
   ledger.
3. Preserve all active external ownership and exact recovery facts, including
   the 04:24 KST intraday-head due fact, without changing their workers.
4. Verify that the compressed projection retains the current objective, every
   active owner/resource/due fact, the bottleneck, improvement, and recovery
   action. Refresh the other stateboards and this file only if their current
   facts change.

## Verification

Run a focused governance/stateboard consistency check, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Simplify orchestration stateboard`
