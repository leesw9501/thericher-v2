# Next Codex Goal

## Objective

Build one bounded, private six-symbol NAS D1 forward-cache path that can later
supply a new all-symbol prospective observation without mutating the frozen
historical panel.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattest the frozen NAS D1 panel and the completed prospective
   `input_unavailable` receipt before opening a new cache namespace.
3. Ask Claude for a concise falsification-first check of the forward-cache
   boundary, source provenance, and leakage/survivorship limitations. If OAuth
   remains expired, record `review_unavailable` and continue this private,
   non-promoting Data package.

## Contract

- Data owns this package. Engine Research may prepare its consumer contract but
  must not rerun the prospective observer until a complete all-six-symbol
  decision, `t+1`, and `t+2` window exists. Execution remains independent.
- Use the standing-authorized KIS Paper market-data client only for a bounded
  current-D1 capability probe and collection. Do not call account or order
  endpoints, read `KIS_LIVE_*`, submit a broker order, or expose data publicly.
- Store raw cache bytes only under a new `D:\market_data` forward namespace;
  never write data, credentials, raw provider bodies, or model artifacts to
  Git. Keep source-safe status evidence and mutable cursor/recovery facts
  separate from the frozen historical panel.
- The fixed symbols are `AAPL`, `AMZN`, `GOOGL`, `META`, `MSFT`, and `NVDA` on
  NAS. They are a fixed consumer basket, not a point-in-time universe claim.
- Do not merge, overwrite, backfill into, or reinterpret the frozen historical
  NAS panel. Do not blend another provider, rank candidates, tune a model,
  construct an ensemble, promote a result, or create a Paper order.
- A partial result, endpoint limit, closed-session absence, or failed page
  closes only the affected source/cache cursor with a source-safe recovery
  state. It never blocks another ready lane or becomes a human approval gate.

## Work

1. **Data:** define the forward-cache layout, immutable source-safe receipts,
   deduplication key, durable cursor, recovery states, and a read-only
   historical-plus-forward consumer projection. The projection must preserve
   the frozen panel hash and must not write merged rows back into it.
2. **Data:** run one bounded single-client KIS Paper current-D1 capability
   probe, then collect useful complete pages serially at measured accepted-page
   pace. Record source-safe coverage, accepted/error counts, and the next
   recovery action without printing credentials or raw rows.
3. **Validation:** add focused tests proving six-symbol isolation, frozen-panel
   immutability, source-safe persistence, cursor recovery, and no credential,
   account, order, or live route in offline test paths.
4. **Engine Research:** preserve the frozen candidate package and only record
   whether the new cache has the exact three-session common-window consumer
   input. Do not run a new observation, rank a candidate, or dispatch GPU work
   merely because the cache exists.

## Completion

- A distinct six-symbol forward cache exists under `D:\market_data` with a
  source-safe `ready`, `partial`, `input_unavailable`, or `source_limited`
  status and a recoverable cursor where appropriate.
- The frozen historical panel hash is reattested unchanged, and any newly
  materialized common-session coverage is stated without raw rows or a
  point-in-time universe claim.
- Focused tests cover the cache contract and route boundaries. Refresh the
  relevant stateboards and replace this file with exactly one next objective.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Add NAS D1 forward cache path`
