# Next Codex Goal

## Objective

Complete `kis-daily-pair-forward-v5-readiness-and-one-shot-collection-v1`:
use the authenticated virtual-host capability only to make one fresh, bounded
QQQ/SPY D1 forward-cache observation when the existing shared gates allow it.
This advances Data recovery only; it does not qualify causal input, strategy,
model, execution, Paper trading, or live behavior.

## Boundaries

- Run `./scripts/start_next_codex_task.ps1` first, then read `HANDOFF.md`,
  `AGENTS.md`, `RUNBOOK.md`, and the active stateboards. Ask Claude for a short
  falsification-first recovery check before the external collector invocation.
  A missing response is `review_unavailable`, not agreement or a hold.
- Reattach the authenticated token-only receipt
  `sha256:d07e12f8ca521ca32cc00a4a0f81625ad5b503fa0505bad026969aca95db8261`
  before relying on it. It proves only one token capability, not a daily data
  result or a consumer promotion.
- Use only the existing KIS Paper pair-forward readiness and collector service.
  `KIS_PAPER_*` reads are authorized through this named Data path; never read
  or route `KIS_LIVE_*`. Never print or retain credentials, tokens, account
  identifiers, raw broker bodies, or raw market rows.
- Run at most one existing credential-free readiness invocation. Only if its
  source-safe result is currently ready with the shared token and rate gates
  open, no active pair-forward collector owns the cache, and its static contract
  matches the existing v4 collector, run exactly one existing collector.
  Otherwise close this invocation without a collector call. No retry, parallel
  flood, scheduler change, or foreground waiting.
- Reattach only source-safe receipt and aggregate cache/index facts. Preserve
  the v4 receipt and all causal timing, provider-finality, Research, Execution,
  Paper, PnL, and live conclusions.

## Required Work

1. Source-only inspect the current readiness/collector route and reattach the
   authentication capability receipt.
2. Run the one readiness invocation and record its immutable external receipt
   pointer/hash plus route-isolation facts.
3. If and only if readiness permits it, run one existing QQQ/SPY collector and
   reattach its source-safe outcome and aggregate cache/index comparison. Do
   not retry.
4. Refresh `HANDOFF.md`, `RUNBOOK.md`, and active stateboards with the exact
   outcome. It must remain Data-only.
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
