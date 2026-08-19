# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-v3-preflight-and-one-shot-collection-v1`:
reattach one credential-free v3 QQQ/SPY D1 pair-forward preflight and, only if
it requires collection, execute exactly one fresh KIS Paper market-data outcome
through the existing collector. This advances bounded Data recovery only, not
causal input, strategy, model, execution, or trading eligibility.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first recheck before collection. A missing response is
  `review_unavailable`, not agreement or a stop on an independent local package.
- Use only the existing shared-tag pair-forward Compose services. Build only the
  existing collector image tag; do not create a second image, provider, queue,
  worker, scheduler, or Research/Execution consumer.
- The preflight is credential-free, network-disabled, and cache-read-only. Do
  not run readiness. Run the collector only when the fresh preflight is exactly
  `collection_required` and its payload v3 contract hash matches current host
  source; otherwise close with no collector invocation.
- The collector may read `KIS_PAPER_*` only inside its existing service and may
  call only its KIS Paper QQQ/SPY daily market-data route and external pair
  cache. Do not call account, position, quote, order, or live endpoints.
- Inspect the selected local image identity after build and immediately before
  the collector only as a narrow same-tag stability check; do not claim immutable
  image provenance. Invoke the collector at most once with no build or pull.
- Retain only categorical status, fixed stage/kind/optional phase, contract
  match, safe aggregates, route isolation, artifact policy, and cache-change
  observation. A missing phase remains unknown, never a retry premise.
- Never read or route `KIS_LIVE_*`, print secret/config-variable names, account
  data, raw market rows, raw broker bodies, private cache values, or exception
  text. Generated receipts stay under `D:\thericher-v2\model-artifacts`; raw
  cache data stays under `D:\market_data`; neither enters Git.

## Required Work

1. Reattach the v2 `commit/cache_contract` receipt as phase-unknown and verify
   no Research or Execution consumer treats this cache as decision-time or
   finality input.
2. After Claude recheck and focused tests, build the existing shared tag and run
   exactly one credential-free v3 preflight. Recompute its receipt hash and
   compare only its payload contract hash against the current host static hash.
3. Only if that exact preflight is matching `collection_required`, invoke the
   existing collector once with no build or pull. Recompute its receipt hash and
   retain only the allowed source-safe facts. Do not infer the exact cause from
   a missing phase or an observed lack of cache mutation.
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
