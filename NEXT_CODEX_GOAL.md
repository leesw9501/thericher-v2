# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-v2-fresh-cache-bootstrap-v1`: establish one
isolated, forward-only KIS Paper D1 cache for `QQQ/NAS` and `SPY/AMS` after the
v1 cache retained revision conflicts, without altering, clearing, copying, or
relabeling v1 data.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a
  concise falsification-first challenge before changing the persistent cache
  recovery design.
- `KIS_PAPER_*` may be read only through the named daily market-data owner
  path. Do not read or route `KIS_LIVE_*`; do not call account, position,
  quote, order, submit, modify, cancel, or broker-execution endpoints.
- Keep v1 immutable and create v2 only under
  `D:\market_data\us_equities\kis_paper_private\daily-qqq-spy-forward\v2`.
  Never copy raw v1 rows into it. Keep raw data out of Git, logs, stateboards,
  Claude prompts, and source-safe receipts.
- A v2 collection is collection/provenance evidence only. It cannot clear v1
  quarantine, establish point-in-time availability/finality, rank, train,
  allocate GPU, create an ensemble, or create an Execution/Paper consumer.
- Use one owned client and bounded serial collection. A source-backed or
  measured token/rate gate belongs to the worker; never foreground-wait.
  Do not replace it with a parallel request flood.

## Required Work

1. Freeze a versioned v2 cache identity, source-safe receipt contract,
   immutable-v1 separation check, and exact QQQ/NAS + SPY/AMS scope before a
   network call.
2. Add focused tests for v1/v2 root separation, raw-data exclusion from public
   evidence, KIS Paper-only route isolation, durable cursor/recovery behavior,
   and no model/Execution consumer.
3. Run a credential-free preflight, then one eligible bounded KIS Paper
   daily-market-data collection when its owned gate permits. Record only
   source-safe aggregate evidence; a deferred, failed, or partial collection
   is a scoped result, not a retry loop or approval wait.
4. Independently reattach the v2 receipt/cache identity and refresh
   `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with its exact limitation.
5. Run required verification, commit, push, replace this file with exactly one
   material next objective, and continue.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example --profile research config --quiet
git diff --check
```
