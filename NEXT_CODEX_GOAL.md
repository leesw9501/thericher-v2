# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-v4-preflight-and-one-shot-collection-v1`:
apply the completed source-safe v4 subphase contract to one independently
scoped QQQ/SPY D1 forward-cache observation. This advances Data recovery only;
it does not make current data, causal input, strategy, model, execution, or
trading eligible.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first recovery check before the external invocation. A missing
  response is `review_unavailable`, not agreement or a hold on this
  standing-authorized private Paper Data package.
- Use only the named KIS Paper daily market-data client path. `KIS_PAPER_*`
  reads are authorized; never read or route `KIS_LIVE_*`. Never print or retain
  credentials, account identifiers, raw broker bodies, or raw market rows.
- Reuse the existing shared pair-forward service and exact v4 static contract
  hash `sha256:95e0ec0fd7408e237cbb79e4010e152291dd4322f58133bd4c46207c258dc893`.
  Build/configure only that existing service if needed; do not add a worker,
  scheduler, provider, public surface, consumer, or runtime replacement.
- Run one credential-free preflight. Invoke exactly one existing collector only
  if the preflight is source-safe `collection_required`, its runtime contract
  hash matches v4, and no active pair-forward collector owns the cache. A
  mismatch, non-required status, or ownership conflict closes this invocation
  without a collector call. No automatic retry or parallel flood.
- Reattach only source-safe receipt and aggregate cache/index facts before and
  after the allowed call. Treat a v4 subphase as the static source region where
  an exception surfaced, not its exact cause. Preserve all causal timing,
  provider-finality, Research, Execution, Paper, and live conclusions.

## Required Work

1. Verify the current shared-image/runtime-contract and exact cache ownership
   facts without exposing private data.
2. Run the one credential-free v4 preflight and record its immutable external
   receipt pointer/hash and route-isolation facts.
3. If and only if it requires collection, run one existing QQQ/SPY collector
   invocation and reattach its source-safe outcome plus aggregate cache/index
   comparison. Do not retry.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with the exact
   result. A v4 label may guide a later targeted recovery package, but it must
   not itself become a causal, model, or Paper promotion claim.
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
