# Next Codex Goal

## Objective

Create one immutable, prospective Tiingo standard-EOD refresh for the already
approved `SPY`/`QQQ`/`IWM` scope. This is forward data lineage only, not model,
paper-trading, or profitability work.

## Context

- The local replacement inventory found no fresh local training candidate:
  `D:\thericher-v2\model-artifacts\data-agent\local-replacement-inventory\local-replacement-inventory-r2\summary.json`
  (`sha256:c7c1de08e33b3ea2a70688a9ec71903ba39ea00531c38bacf43bd053a5c1cf8d`).
- The prior fixed-ETF Tiingo snapshot ends at `2026-07-10`.
- Paid PIT data remains an operator purchase decision. Do not buy or enroll.
- The target-position policy graph is now the durable engine direction, but this
  narrow data goal does not implement it, train its experts, or build the future
  KIS paper console. It only preserves prospective lineage needed by later
  eligible research.

## Start

1. Run `.\scripts\start_next_codex_task.ps1` and read the required project,
   policy, and Data/Engine stateboard files.
2. Ask Claude for a short falsification-first check before relying on returned
   coverage, revisions, or prospective eligibility.

## Data Work

1. Use the existing guarded reader to read only `TIINGO_API_TOKEN` from root
   `.env`; never print, log, retain, or parse another value.
2. Make at most three standard-EOD requests, exactly `SPY`, `QQQ`, and `IWM`,
   for dates after `2026-07-10`. Do not widen symbols, endpoints, history, or
   provider scope.
3. Store raw bytes, normalized raw-D1 fields, hashes, rights marker, dates, and
   gaps in a new immutable `D:\market_data` snapshot. Do not overwrite or merge
   the prior source.
4. Reattest offline on host and Docker where practical. Keep all data/artifacts
   external to Git and classify the result as prospective lineage only.
5. Keep the exact paid-data need visible: private-use US daily data with
   historical listing/delisting, as-of universe, and verified adjustment lineage.

## Boundaries

- No KIS, order, local-paper, live, or `THERICHER_MODE` change.
- No credential access except that one approved Tiingo token line.
- No Yahoo/IEX/Norgate/broad-universe/paid action, model training, GPU data job,
  r4 retry, model comparison, ensemble, dashboard/KIS-console change,
  scheduler, daemon, or report family.

## Completion

Refresh stateboards, `HANDOFF.md`, `DECISIONS.md`, and this goal. Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Commit, push, and report the snapshot/hash, coverage, gaps/revisions, token
scope used, blocked model condition, and next objective.
