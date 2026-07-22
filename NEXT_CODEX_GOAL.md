# Next Codex Goal

## Objective

Build the first reusable KIS-native intraday cache for Paper decision inputs,
starting with SPY and QQQ, while preserving the scheduled quote-derived KIS
Paper session as an independent execution-learning loop.

The intended consumer path is honest `Bar` data at 1m with deterministic 5m,
10m, 1h, and 3h resampling. It is a data and execution-foundation objective,
not a profitability, GPU-utilization, or strategy-promotion claim.

## Standing Authority And Boundaries

- All private `KIS_PAPER_*` market-data, account, order, cancel, modify,
  reconciliation, raw-retention, and goal-owned schedule work is authorized.
- Store newly retained KIS market data only under `D:\market_data`; generated
  artifacts stay under `D:\thericher-v2\model-artifacts` or
  `/app/model_artifacts`. Never store either in Git.
- Do not print or commit credentials, account identifiers, raw quote/broker
  bodies, raw order identifiers, or private intent state.
- Do not read `KIS_LIVE_*`, call a live host/route, use real capital, buy data,
  or expose a public service.
- A historical `raw_market_data_retained: false` field and preserved unknown
  canary state are evidence about their own records only. Neither restricts a
  later correctly scoped KIS Paper data or session action.

## Required First Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, and
   `RUNBOOK.md`.
3. Read the active stateboards:
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
4. Read the current KIS daily/backfill and `Bar` consumption contracts before
   changing the intraday provider or resampling surface.
5. Ask Claude for a concise falsification-first drift check before changing the
   provider contract, point-in-time/timestamp semantics, or cache architecture.
   Do not send credentials, raw broker output, or private data rows.

## Role-Owned Work

### Data Agent

1. Inventory the existing KIS Paper raw-minute code and narrow official KIS
   minute-history surface for SPY and QQQ. Use bounded real Paper requests when
   they answer an implementation question; record only endpoint capability,
   timestamp/session semantics, pagination facts, counts, and closed failures.
2. Replace terminal one-shot behavior with a small resumable cache contract:
   provider identity, raw-byte storage, manifest/index, hashes, cursor, exact
   deduplication, recovery, and a canonical `Bar` loader. Preserve source
   limitations rather than repairing rows silently.
3. Add deterministic 1m-to-5m/10m/1h/3h resampling from the canonical cache.
   Keep the session/timezone rule explicit and avoid mixing Tiingo/Norgate data
   into a KIS runtime window. Establish holiday and early-close semantics from
   source evidence before calling the weekday execution time window a full
   exchange calendar.
4. Add focused tests for no Git writes, raw-retention outside the repo, cursor
   recovery, duplicate/conflict behavior, timestamp ordering, and resampling.

### Execution Agent

1. Keep `thericher-kis-paper-quote-session` active. Read and integrate only its
   sanitized external outcome after the next eligible due invocation; do not
   re-run or mutate an ambiguous existing intent.
2. Fix only a concrete virtual-route, safe-projection, pacing, or reconciliation
   defect revealed by that outcome. A closed Paper failure is evidence, not an
   approval hold or a reason to stop fresh distinct Paper work.

### Engine Research Agent

1. Define the first intraday campaign input contract from the actual cache:
   feature windows, target timestamp, session exclusion behavior, cost model,
   and naive baseline. Do not claim a candidate is eligible until the cache is
   sufficiently verified.
2. Keep breadth, depth, ensemble, and replication queues current. Start GPU
   work only when a frozen eligible campaign contract exists; use the research
   Docker image and external artifact root.

## Completion Evidence

- A verified, resume-capable KIS-native SPY/QQQ intraday cache boundary with
  canonical 1m `Bar` consumption and deterministic higher-timeframe resampling.
- The first scheduled due-session KIS Paper outcome, or a specific safe failure
  that identifies the next virtual-route repair.
- No KIS Live access and no raw/secret/private data in Git or public output.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add KIS native intraday cache foundation`
