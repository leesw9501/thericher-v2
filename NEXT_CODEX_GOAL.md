# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-commit-failure-classification-v1`: make a
future QQQ/SPY D1 pair-forward `commit` failure diagnostically classifiable
without exposing private details. This is a local recovery-code and test
objective, not a KIS collection, cache-refresh, causal-input, strategy, model,
execution, or trading objective.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first drift check before changing the commit recovery boundary.
- Do not read credentials, call KIS, invoke any Docker service, write an
  external cache, run a scheduler, or retry the completed one-shot collector.
- Never read or route `KIS_LIVE_*`, print secret/config-variable names, account
  data, raw market rows, raw broker bodies, private cache values, or exception
  text.
- Preserve the pair cache format, retention policy, target scope, route
  isolation, token/rate controls, schedule, and consumer boundary. Do not add a
  provider, worker, queue, or Research/Execution consumer.
- Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw cache
  data stays under `D:\market_data`; neither enters Git.

## Required Work

1. Reattach the completed shared-contract collector receipt as
   `unavailable/collector_unavailable/failure_stage=commit`, plus the valid
   seven-session offline cache reattestation and observed zero cache-file/index
   modifications in its invocation window. Treat the exact commit cause as
   unknown rather than inferring it from the stage.
2. Add one optional, fixed `commit_failure_kind` only to source-safe receipts
   whose `failure_stage` is `commit`: `cache_contract` for
   `KisPaperDailyPairForwardCacheError`, `storage` for `OSError`, and
   `validation` for `ValueError`. It must never contain exception text, class
   names, paths, raw data, credentials, account data, or dynamic values.
3. Add focused tests for all three fixed mappings, absence on non-commit and
   successful outcomes, receipt-schema compatibility, and source safety.
   Strongest kill test: if an exception's dynamic detail can reach a receipt or
   the field leaks to another failure stage, do not accept the change.
4. Refresh stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run verification,
   commit, push, replace this file with exactly one next objective, and
   continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
