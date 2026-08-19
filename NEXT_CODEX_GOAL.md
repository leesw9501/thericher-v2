# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-v2-preflight-and-one-shot-collection-v1`:
reattach one credential-free v2 QQQ/SPY D1 pair-forward preflight and, only if
it requires collection, execute one fresh KIS Paper market-data outcome through
the existing collector. This advances bounded Data recovery only, not causal
input, strategy, model, execution, or trading eligibility.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first recheck before the collection because the v2 runtime
  contract changes what a later commit-stage receipt can establish.
- Use only the existing shared-tag pair-forward Compose services. Build only the
  existing collector image tag; do not create a second image, provider, queue,
  worker, scheduler, or Research/Execution consumer.
- The preflight is credential-free, network-disabled, and cache-read-only. Do
  not run readiness. Run the collector only when the fresh preflight is exactly
  `collection_required` and its payload v2 contract hash matches current host
  source; otherwise close with no collector invocation.
- The collector may read `KIS_PAPER_*` only inside its existing service and may
  call only its KIS Paper QQQ/SPY daily market-data route and external pair
  cache. Do not call account, position, quote, order, or live endpoints.
- Invoke the collector at most once. Do not retry automatically, infer data
  availability/finality, or treat a cache write as a model/Execution input.
- Never read or route `KIS_LIVE_*`, print secret/config-variable names, account
  data, raw market rows, raw broker bodies, private cache values, or exception
  text.
- Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw cache
  data stays under `D:\market_data`; neither enters Git.

## Required Work

1. Reattach the v1 `commit` receipt as unresolved and verify there is still no
   Research/Execution decision-time or finality consumer for this cache.
2. After Claude recheck and focused tests, build the existing shared tag and run
   exactly one credential-free v2 preflight. Recompute its receipt hash and
   compare only its payload contract hash against the current host static hash.
3. Only if that exact preflight is matching `collection_required`, invoke the
   existing collector once with no build or pull. Recompute its receipt hash and
   retain only categorical status, optional fixed stage and commit kind, contract
   match, safe aggregates, route isolation, artifact policy, and cache-change
   observation. A missing optional kind remains unknown, never a retry premise.
4. If the cache changes, record that fact only; defer causal qualification to a
   separate objective. If it does not, close the exact outcome without a loop.
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
