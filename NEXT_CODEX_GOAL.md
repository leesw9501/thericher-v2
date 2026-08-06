# Next Codex Goal

## Objective

Build `source-local-qqq-mtf-window-feasibility-v1`.

Use the completed `source-local-qqq-mtf-resampling-mechanics-v1` QQQ/NAS
catalog contract to attest a frozen, target-free causal window profile at the
existing 15:30 ET cutoff: M1=30, M5=6, M10=3, H1=2, H3=2 completed bars. This
is feature-input geometry only; it is not a model, target, strategy, backtest,
prediction, or Paper-input exercise.

## Hard Boundaries

- Do not call KIS, invoke or alter a task, submit/modify/cancel a Paper order,
  or read credentials or any `KIS_LIVE_*` value.
- Do not inspect or commit raw bars, prices, provider payloads, account/order
  data, credentials, weights, or generated artifacts. Keep artifacts under
  `D:\thericher-v2\model-artifacts`.
- Reuse the existing calendar/session resampler and completed-bar window
  contracts. Do not change their shared semantics or create a second resampler.
- Do not create a campaign, target, decision, local-paper intent, sealed
  evaluation, model selection, ensemble, GPU appointment, scheduler, provider,
  route, or Paper permission. GPU remains unallocated.

## Required Work

1. Run a concise Throughput Review and inspect the completed MTF mechanics
   receipt plus the existing causal window-profile helpers. Ask Claude only if
   a shared window/resampling semantic must change; do not wait on a review.
2. Freeze the QQQ/NAS catalog identity, completed M1 prefix, calendar scope,
   cutoff, and exact five-timeframe window profile before materialization.
3. Build a small Data-owned/Engine-consumed source-safe attestation and CLI.
   It reports only aggregate eligible-prefix/window counts, incomplete or stale
   categories, causal-prefix commitment, and `complete` or `input_unavailable`.
   Write immutable artifacts outside Git.
4. Add focused tests for cutoff alignment, no future-bar influence, no
   cross-session carry, partial M1 rejection, terminal H1/H3 exclusion,
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

`Attest source-local multi-timeframe causal windows`
