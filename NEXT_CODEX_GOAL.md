# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-post-reconciliation-observation-v1`: make one
bounded post-policy observation of the fixed QQQ/NAS and SPY/AMS KIS Paper D1
forward-cache route. This tests the deployed merge behavior against the current
external cache, not a strategy or causal-data claim.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Reuse the recorded
  Claude `supported-with-limits` recovery challenge; ask again only if the
  planned scope materially widens.
- Build the existing fixed-pair service from the committed checkout, then use
  its existing schedule runner: one offline preflight and, only for
  `collection_required`, at most one collector invocation. Do not add targets,
  pages, retries, a new scheduler, or a second invocation.
- `KIS_PAPER_*` use is standing-authorized only for this virtual-paper
  daily-market-data route. Do not call account, position, quote, order, or
  `KIS_LIVE_*` endpoints; do not enable live behavior.
- Retain raw market data only in the existing external cache. Never print or
  commit raw rows, dates, OHLCV values, credentials, tokens, account identifiers,
  or dynamic exception details. Inspect receipts and cache state only through
  existing source-safe offline readers.
- A cache write, exact duplicate, later append, partial result, or clean
  collector exit is not causal availability, provider finality, model evidence,
  GPU eligibility, or a Research/Execution/Paper consumer. A retained-revision
  quarantine never clears automatically; a same-route refetch is not independent
  recovery evidence.

## Required Work

1. Reattest the fixed-pair cache and source-safe preflight before the collector.
2. If preflight says `collection_required`, run exactly one existing collector;
   otherwise preserve its returned state without forcing collection.
3. Reattach only source-safe receipt, route-isolation, aggregate cache identity,
   target status/category/count, and recovery facts. Treat conflicts, cache
   mismatch, unavailable output, or non-ready causal qualification as scoped
   outcomes with no retry or clearance.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards. Preserve every
   causal/provider-finality limitation and record any Claude limits relied on.
5. Run required verification, commit, push, replace this file with exactly one
   next objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
