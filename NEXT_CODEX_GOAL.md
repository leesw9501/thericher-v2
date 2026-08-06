# Next Codex Goal

## Objective

Build `source-local-qqq-mtf-window-matrix-v1`.

Use the completed `source-local-qqq-mtf-resampling-mechanics-v1` and
`source-local-qqq-mtf-window-feasibility-v1` QQQ/NAS receipts to freeze and
attest the full existing canonical six-profile causal observation-window matrix
at the existing 15:30 ET cutoff. This is target-free input geometry only; it
is not a model, target, strategy, backtest, prediction, or Paper-input
exercise.

## Hard Boundaries

- Do not call KIS, invoke or alter a task, submit/modify/cancel a Paper order,
  or read credentials or any `KIS_LIVE_*` value.
- Do not inspect or commit raw bars, prices, provider payloads, account/order
  data, credentials, weights, or generated artifacts. Keep artifacts under
  `D:\thericher-v2\model-artifacts`.
- Reuse the completed calendar/session resampler, causal window helpers, and
  canonical profile catalog. Do not change their shared semantics or create a
  second resampler or profile catalog.
- Do not create a campaign, target, decision, local-paper intent, sealed
  evaluation, model selection, ensemble, GPU appointment, scheduler, provider,
  route, or Paper permission. GPU remains unallocated.

## Required Work

1. Run a concise Throughput Review and inspect both completed QQQ MTF receipts
   plus the canonical profile catalog. Ask Claude only if a shared
   resampling/window/profile semantic must change; do not wait on a review.
2. Freeze the exact ordered six-profile catalog, completed M1 prefix, calendar
   scope, cutoff, parent receipt hashes, and full matrix shape before
   materialization.
3. Build a small Data-owned/Engine-consumed source-safe matrix attestation and
   CLI. It reports only per-profile/timeframe aggregate eligible-window counts,
   terminal exclusions, opaque commitments, and `complete` or
   `input_unavailable`. Write immutable artifacts outside Git.
4. Add focused tests for ordered-catalog binding, every profile's exact
   completed-bar geometry and cutoff alignment, no future-bar influence, no
   cross-session carry, partial M1 rejection, external-parent receipt integrity,
   external-artifact-only output, and no network/credential/KIS/broker access.
5. Run one CPU-only local-cache smoke without printing raw data, then refresh
   Data, Engine Research, and orchestration stateboards.

## Verification

Run focused tests and the source-local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Attest source-local multi-timeframe window matrix`
