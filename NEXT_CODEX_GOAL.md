# Next Codex Goal

## Objective

Build and start `kis-paper-private-daily-backfill-v1`: a paced, resumable,
private KIS Paper daily-data lane for the initial ETF universe `QQQ`, `SPY`,
and `IWM`.

The completed `QQQ` collector proved real raw retention on `D:`: two pages,
200 input rows, 199 unique rows, one exact dedupe, and a matching atomic
manifest/control record. Turn that working path into repeatable backfill work,
not another approval exercise.

`KIS_PAPER_*` credential use, market/account/order calls, paper submission,
routine sizing, and goal-owned scheduling are standing-authorized. Only
`KIS_LIVE_*` and real-money routes remain unavailable.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `agents/data.md`, and `agents/execution.md`.
3. Inspect the completed private daily collector, its tests, and its manifest
   without printing raw rows, credentials, or account values.
4. Ask Claude for a concise drift-check before widening the hard-coded KIS
   daily query allowlist or introducing the resumable worker contract. Do not
   send Claude credentials, raw rows, or account information.

## Work Packages

### Data Agent

- Define a canonical private daily-cache layout with immutable raw snapshots,
  one logical manifest index, per-symbol/date cursors, source-adjustment mode,
  hashes, dedupe facts, and recovery state under `D:\market_data`.
- Confirm the KIS venue mapping for `QQQ`, `SPY`, and `IWM` from official
  documentation or bounded response evidence before each symbol is collected.
  Do not assume the existing `NAS` probe mapping applies to every ETF.
- Preserve raw daily cache bytes only on `D:`. Keep the cache private, local,
  unserved, and unredistributed.

### Execution Agent

- Generalize the current daily query boundary only to the fixed initial ETF
  universe and verified venue mappings. Keep endpoint, paper host, response
  parsing, secret redaction, and no-live routing explicit.
- Implement a small goal-owned backfill worker that selects the next unresolved
  symbol/date chunk, writes an atomic snapshot and manifest/index update, and
  can resume after interruption. This is a concrete data worker, not a generic
  scheduler platform.
- Use paced chunks: at most two daily pages per collection session, a measured
  two-second interval within a chunk, and an adaptive deferred retry after a
  rejection. A rejected chunk must remain visible and retryable; it is not a
  terminal business or operator stop.
- Start the lane with real KIS Paper calls after focused tests. Continue useful
  chunks while storage, source terms, and recovery evidence remain healthy.

### Engine Research Agent

- Inspect the retained manifest/index contract and define the minimum daily
  history and provenance needed before it becomes a research dataset. Do not
  manufacture GPU work from an immature cache.
- Keep a ready daily selection/feature baseline queue so it can begin as soon
  as the Data contract reaches its stated minimum.

### Validation

- Independently check raw/manifest/index hashes, cursor progression,
  deduplication, pacing, redaction, and recovery behavior.
- Confirm the worker retains actual raw-data facts (`true` when stored) rather
  than inheriting a metadata-only marker default.

## Operating Boundaries

- There is no paper-capital, profitability, report, dashboard, trade-count, or
  per-call approval gate.
- Do not read `KIS_LIVE_*`, call a live route, expose secrets, or publish/serve
  KIS-originated data.
- Preserve the agreed D: free-space floor and stop the affected cache only if
  applicable source terms prohibit retention.
- Keep raw-minute acquisition as a separate ready data package; do not block
  the daily lane on it or pretend daily data alone supplies intraday features.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Add resumable KIS daily backfill lane`
