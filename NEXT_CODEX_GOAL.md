# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-commit-phase-diagnostic-v1`: add a minimal,
source-safe fixed commit-phase diagnostic for future QQQ/SPY D1 pair-forward
`cache_contract` failures. This advances Data recovery only; it does not make
current data, causal input, strategy, model, execution, or trading eligible.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first drift check before changing the recovery contract. A
  missing response is `review_unavailable`, not agreement or a stop on this
  isolated local package.
- Use source and fixtures only. Do not read credentials, call KIS, start
  Docker, invoke a collector or scheduler, write the external cache, or retry
  the completed collection.
- Keep the existing `commit_failure_kind` behavior intact. A phase may appear
  only on a future `failure_stage=commit` receipt whose fixed kind is
  `cache_contract`; it must be absent for success, every non-commit stage, and
  storage or validation kinds.
- The only allowed phase values are fixed source constants representing static
  operation boundaries: `cache_prepare`, `snapshot_persist`, `index_persist`,
  and `cache_reverify`. Never retain an exception message, exception class,
  path, raw row, credential, account datum, cache value, or dynamic detail.
- Preserve the public cache exception behavior for callers. Do not infer the
  phase of either completed receipt or add a new runtime worker, provider,
  queue, consumer, approval step, or promotion path.

## Required Work

1. Add the smallest internal phase-carrying mechanism needed to associate a
   caught pair-forward cache-contract failure with its static commit boundary.
2. Extend the source-safe collector payload and static runtime contract only as
   needed for the optional phase. Keep receipt top-level schema unchanged.
3. Add focused tests for every allowed phase, field omission outside its exact
   scope, preserved exception behavior, and a private-detail canary proving no
   dynamic exception content serializes.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with the narrow
   v2 outcome and the new diagnostic contract; no causal, Research, Execution,
   Paper, or live conclusion may change.
5. Run verification, commit, push, replace this file with exactly one next
   objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
