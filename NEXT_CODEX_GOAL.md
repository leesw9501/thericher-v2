# Next Codex Goal

## Objective

Build and run the first resumable KIS Paper daily-history acquisition campaign
for the existing fixed current NAS basket: `AAPL`, `AMZN`, `GOOGL`, `META`,
`MSFT`, and `NVDA` on `NAS`.

The campaign must turn the existing two-page capability observation into a
separate durable historical cache with measured temporal reach and sustained
accepted-page progress. It is data acquisition only, not a historical universe,
model selection, replay, Paper order input, or live behavior.

## First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read HANDOFF.md, AGENTS.md, DECISIONS.md, RUNBOOK.md, and all active
   stateboards.
3. Read the existing daily-universe probe, private daily collector, KIS market
   data client/rate gate, catch-up runner, Compose services, and focused tests.
4. Ask Claude for a short falsification-first drift-check before introducing a
   new collector or Compose profile. Do not send credentials, account facts,
   raw rows, or data values. An unavailable Claude CLI is recorded as
   `review_unavailable`, not a hold on this private Data work.

## Required Work

1. Create a new KIS-Paper-only daily-history collector and its own Docker
   profile. It must use the existing fixed six-symbol NAS registry and start
   from the qualified `2026-07-24` head, then move each durable cursor backward
   toward `1990-01-01` or that symbol's actual source terminal.
2. Keep its raw daily snapshots, immutable manifests, and per-target cursors
   under a new `D:\market_data` cache root. Keep only source-safe receipts,
   hashes, coverage buckets, and progress summaries under
   `D:\thericher-v2\model-artifacts`. Do not mutate or blend the existing
   two-page probe cache, frozen panel, or QQQ/SPY/IWM catalog.
3. Use one reusable Paper client/token per active collector and the existing
   measured 1.0-second shared request-start gate. A worker may continue serial
   cursor pages while eligible; it yields only itself for a categorical limit,
   shared retry time, storage floor, source terminal, or bounded worker runtime.
   Never foreground-sleep, infer an unlimited daily quota, or issue a parallel
   request flood.
4. Make each active collector emit the Data stateboard projection required by
   AGENTS.md: scope, cursor, accepted/categorical page counts, measured pace,
   remaining-work estimate or `unknown`, ETA bucket or `unknown`, `next_due`,
   and recovery class. A runtime-bound partial collection must be `resume`, not
   a failure or a human approval hold.
5. Run the first real collection cycle through the new Compose profile only.
   Compose may inject `KIS_PAPER_*`; do not open, print, copy, or pass `.env`
   values on a command line. Record only source-safe output categories in chat
   and Git.
6. Add focused tests for fixed-registry route isolation, durable cursor resume,
   source-safe progress/ETA projection, external storage containment, and no
   account/order/live path. Use temporary Execution and Validation roles for
   independent route and resume/sanitization checks.

## Hard Boundaries

- Use `KIS_PAPER_*` only in the owned market-data collector/Compose profile.
  Never read or route `KIS_LIVE_*`.
- Preserve `THERICHER_MODE=off`; do not call account, position, open-order,
  order submit, modify, cancel, reconciliation, quote, or live endpoints.
- Do not call Tiingo, use paid data, change the fixed registry, or acquire a
  public historical universe.
- The fixed current basket is not a point-in-time universe, ranking input, or
  strategy result. Do not create a model, GPU campaign, replay, PnL claim, or
  Paper decision from this collection.
- Do not store raw market data, credentials, or generated artifacts in Git.
- A source terminal, rate limit, storage stop, failed page, or incomplete
  cursor applies only to that collector. Persist truthfully and continue every
  independent ready lane.

## Completion Evidence

- New collector/profile and a first real source-safe collection outcome with a
  separate D: cache, immutable manifest, cursor state, and external receipt.
- Data stateboard contains the required current progress projection; `unknown`
  is acceptable only where the first run cannot yet measure it.
- Independent Execution/Validation confirms no account/order/live route,
  no secret/raw value output, and correct resume behavior.
- No order, account, position, quote, Tiingo, or live broker call occurred.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

Before ending, verify, commit, push, and replace this file with exactly one
next company objective. A source-limited or recoverable partial run is evidence
for this collector, not a reason to wait for operator approval or halt another
lane.

## Suggested Commit Message

`Add resumable six-symbol daily history collector`
