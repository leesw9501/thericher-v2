# Next Codex Goal

## Objective

Turn the new KIS-native SPY/QQQ 1m cache into a recurring regular-session data
loop, then use the first sufficiently complete cache window for a bounded CPU
local-paper baseline. Keep the existing quote-derived KIS Paper session active
as an independent execution-learning loop.

This is a data-readiness and deterministic replay objective, not a profitability
or GPU-utilization claim. A short cache must not be disguised as a validated
intraday strategy.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market-data, account, order, cancel, modify,
  reconciliation, raw-retention, and goal-owned schedule work is authorized.
- Store retained KIS market data only under `D:\market_data`; generated
  artifacts stay under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`. Never store either in Git.
- Do not print or commit credentials, account identifiers, raw quote/broker
  bodies, raw order identifiers, or private intent state.
- Do not read `KIS_LIVE_*`, call a live host/route, use real capital, buy data,
  or expose a public service.
- Historical `raw_market_data_retained: false`, one-shot, or unresolved-canary
  records describe only their own recovery state. They never restrict a fresh
  correctly scoped KIS Paper data, schedule, account, or distinct order action.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read `agents/data.md`, `agents/engine-research.md`, and
   `agents/execution.md`.
4. Inspect the current intraday cache index before a new network call.
5. Ask Claude for a concise falsification-first drift check before adding a
   recurring external data schedule or changing session/timestamp semantics.
   Do not send credentials, raw market rows, or broker output.

## Role-Owned Work

### Data Agent

1. Reattest the current `QQQ/NAS` and `SPY/AMS` cache, then add one narrowly
   owned recurring invocation path for KIS-native 1m collection. It must use the
   persisted cursor, source pacing, external D: cache root, and bounded pages;
   it is not a general scheduler or agent platform.
2. Gather regular-session observations when the US market is open. Record only
   safe coverage, cursor, timestamp, boundary-overlap, completed-bar, and
   session-classification facts. Preserve unknown or extended-session behavior
   rather than inferring a calendar or filling gaps.
3. Establish the smallest evidence-backed `SessionWindow` rule that can label
   a regular session and early close, or retain `observed_unqualified` with an
   exact next source question. Continue independent cache collection either way.
4. Keep raw data outside Git and test recovery, exact deduplication, conflict
   rejection, no-network loading, and deterministic 1m-to-5m/10m/1h/3h output.

### Engine Research Agent

1. Keep the documented initial multi-timeframe contract frozen: completed KIS
   bars only, no source mixing, a next-1m-open to following-1m-open long-only
   target, 1 bp per-side fee plus 2 bps per-side slippage for the initial
   screen, and `flat`/`always_long`/`previous_bar_direction` comparators.
2. Once one source-qualified regular session provides the required completed
   window, run one CPU local-paper baseline and retain replayable artifacts
   outside Git. If coverage is still insufficient, run only a shape/replay smoke
   and leave the campaign in preparation rather than manufacturing labels.
3. Maintain breadth, depth, ensemble, and replication queues. Do not launch a
   GPU job until a frozen chronological intraday campaign dataset exists.

### Execution Agent

1. Keep `thericher-kis-paper-quote-session` active and integrate its next due
   sanitized outcome. An unknown existing intent is reconciled only on its own
   identity; it cannot block the data loop or a distinct Paper action.
2. Fix only a concrete virtual-route, safe-projection, pacing, or
   reconciliation defect found in the outcome. Do not add live routes or move
   credentials into dashboard/runtime projections.

## Completion Evidence

- A narrow recurring KIS-native intraday data invocation with a persisted
  cursor, external cache/artifact paths, and no live route.
- One regular-session source observation or a precise source limitation that
  keeps session semantics visibly unqualified while collection continues.
- A KIS-native CPU local-paper baseline if the data window is sufficient;
  otherwise a verified non-claiming cache/replay smoke and the exact remaining
  coverage requirement.
- No Paper approval latch, raw data, or secrets in Git.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add recurring KIS intraday data loop`
