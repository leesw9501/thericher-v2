# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-runtime-image-provenance-v1`: make the
existing QQQ/SPY D1 pair-forward preflight, readiness, and collector use an
attestable common source/image contract, so a stale service image is detected
before any later collection. This is Docker/runtime provenance only, not a data,
strategy, causal-input, execution, or trading objective.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first drift check before changing the Compose/image contract.
- Do not read credentials, call KIS, make network requests from the container,
  write a market-data cache, run readiness, or invoke the collector.
- Never read or route `KIS_LIVE_*`, print secret/config-variable names, account
  data, raw market rows, raw broker bodies, or exception text.
- Keep the existing pair-forward routes, cache format, token/rate gates,
  schedule, and consumer boundary. Do not add a provider, endpoint, queue,
  worker, scheduler, or Research/Execution consumer.
- Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw cache
  data stays under `D:\market_data`; neither enters Git.

## Required Work

1. Add one canonical source-safe runtime contract fingerprint to pair-forward
   receipts. It may identify only the stage-aware collector source contract by
   SHA-256; it must not retain source text, raw data, credentials, account data,
   or a host path.
2. Make the three existing pair-forward Compose services share one explicit
   local image/build contract, so a build of that contract cannot leave the
   collector on a separately tagged stale image. Preserve each service's
   existing network, credential, cache-mount, and command isolation.
3. Add focused tests for deterministic fingerprinting, receipt safety,
   shared-image Compose topology, and compatibility of preflight/readiness/
   collector behavior. Strongest kill test: if the services can still select
   distinct image tags or the fingerprint can expose mutable/private input, do
   not run an in-container check.
4. After focused tests pass, build the existing shared contract and run exactly
   one credential-free, networkless preflight. Reattach only its source-safe
   fingerprint and isolation/status facts. Do not invoke readiness or collector.
5. Refresh stateboards, `HANDOFF.md`, and `RUNBOOK.md`; run verification,
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
