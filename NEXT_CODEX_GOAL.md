# Next Codex Goal

## Objective

Build `source-local-qqq-mtf-resampling-mechanics-v1`.

Use the existing verified local KIS-private QQQ/NAS M1 catalog and the existing
session resampling path to attest one frozen, causal completed-bar input
contract for M1, M5, M10, H1, and H3. This establishes shared multi-timeframe
input semantics for later research; it is not a model, strategy, or
profitability exercise.

## Hard Boundaries

- Do not call KIS, invoke or alter any task, submit/modify/cancel a Paper
  order, or read any credential or `KIS_LIVE_*` value.
- Do not inspect or commit raw bars, prices, provider payloads, account/order
  data, credentials, model weights, or generated artifacts. Keep artifacts
  under `D:\thericher-v2\model-artifacts`.
- Do not create a predictive campaign, target, decision, local-paper intent,
  sealed evaluation, model selection, ensemble, GPU appointment, scheduler,
  provider, route, or Paper permission.
- Keep this package source-local and CPU-only. It may use deterministic
  synthetic fixtures in tests but no network, secret, or raw-cache output.

## Required Work

1. Run a concise Throughput Review, then inspect the existing M1 session
   resampler and current QQQ/NAS catalog contract before editing. Ask Claude for
   a short falsification-first drift check only if the work requires changing
   shared session/resampling semantics; do not wait on an unavailable review.
2. Freeze the exact local catalog identity and select the first 20 complete
   regular sessions inside an explicit calendar scope. Reuse existing
   session/calendar semantics; do not create a second resampler.
3. Build a small Data-owned/Engine-consumed mechanics attestation and script
   that reports only source-safe aggregates for M1/M5/M10/H1/H3: selected
   session count, completed bucket counts, partial-bucket/drop category,
   causal-prefix commitment, and `complete` or `input_unavailable` status.
   Write immutable artifacts outside Git.
4. Add focused tests proving session alignment, no future-bar influence,
   no cross-session carry, partial/incomplete M1 rejection, correct H3 terminal
   bucket handling, external-artifact-only output, and no network/credential/
   KIS/broker access.
5. Run one CPU-only local-cache smoke without printing raw data. Refresh Data,
   Engine Research, and orchestration stateboards. GPU remains unallocated.

## Verification

Run focused resampling tests and the source-local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add source-local multi-timeframe resampling mechanics`
