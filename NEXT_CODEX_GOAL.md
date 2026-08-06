# Next Codex Goal

## Objective

Build `source-local-session-reset-ema-mechanics-v1`: use the existing pure
15/30 session-reset EMA rule and target adapter to replay a deterministic frozen
source-local QQQ/NAS M1 input through the existing local-paper seam.

This is engineering mechanics evidence only. The current cache lacks observed
decision-time availability and provider finality, so this objective cannot make
a predictive, PnL, profitability, selection, ensemble, GPU, KIS Paper-input,
or broker claim.

## Hard Boundaries

- Do not call KIS, invoke or alter any task, submit/modify/cancel a Paper
  order, or read any credential or `KIS_LIVE_*` value.
- Do not inspect or commit raw bars, prices, provider payloads, account/order
  data, credentials, model weights, or generated artifacts. Keep any result
  under `D:\thericher-v2\model-artifacts`.
- Do not open a predictive campaign, sealed evaluation, model selection,
  ensemble, GPU appointment, scheduler, provider, route, or Paper permission.
- Keep every simulated fill `source: local_paper`; no KIS adapter may be
  imported or reached.

## Required Work

1. Ask Claude CLI for a concise falsification-first mechanics drift check
   before new replay architecture. If unavailable, record only
   `review_unavailable` and continue with local evidence.
2. Reuse the Donchian source-local replay's external-artifact and causal input
   discipline rather than creating a parallel framework. Freeze the first 20
   chronological complete QQQ/NAS regular M1 sessions, session reset, EMA
   15/30 parameters, completed-bar-close decision timing, and next-M1-open
   local-paper fill rule before reading outcomes.
3. Build a small replay module and script that emit only source-safe aggregate
   receipt fields: frozen input commitment, session count, rule activation or
   no-rule-activation category, local-paper/replay count, terminal-flat status,
   and explicit input-unavailable/fail-closed category. Write artifacts outside
   Git.
4. Add focused tests for session reset, warmup, completed-bar causality,
   future-bar and later-session prefix invariance, incomplete-session rejection,
   `source: local_paper` fills, replayability, and terminal-flat completion.
5. Refresh Engine Research and orchestration stateboards. Keep GPU unallocated;
   this package is CPU-only.

## Verification

Run focused model/replay tests and the source-local smoke, then:

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add EMA source-local replay mechanics`
