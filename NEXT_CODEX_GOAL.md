# Next Codex Goal

## Objective

Prove or close the `SPY/NAS` `1m` KIS Paper alternate-exchange historical
continuation contract, then bootstrap only that exact route's durable serial
collector if the source demonstrates real backward progress.

`QQQ/NAS` and `SPY/AMS` already closed as source-limited for their exact
`PINC=1` continuation contracts. This objective must not generalize either
result to KIS as a provider.

## Start

1. Run `./scripts/start_next_codex_task.ps1` and read `HANDOFF.md`, `AGENTS.md`,
   `ARCHITECTURE.md`, `DECISIONS.md`, `RUNBOOK.md`, and the active stateboards.
2. Reattach the existing minute capability probe, intraday backfill collector,
   provider configuration, and their focused tests. Do not inspect or print raw
   market rows.
3. Ask Claude for one short falsification-first drift check before changing the
   route configuration or collector contract. Reuse no credentials, raw rows,
   account identifiers, or secret-bearing output in that prompt.

## Authority And Boundaries

- `KIS_PAPER_*` is standing-authorized for this private **market-data-only**
  work through the existing Data-owned client path. Do not call account, quote,
  order, cancellation, modification, or reconciliation endpoints.
- Use one in-memory client/token, the installed one-second request-start gate,
  and one active collector for the exact cache. Do not parallelize requests or
  create a request flood.
- Probe no more than three pages. Stop the probe on the first categorical limit
  or error. A second same-route attempt is allowed only when the recovery rule
  has a documented, measured reason.
- Store market data only under `D:\market_data` and generated evidence only
  under `D:\thericher-v2\model-artifacts`. Keep raw rows, credentials, and
  provider bodies out of Git, logs, stateboards, and Claude.
- Do not read or route `KIS_LIVE_*`, enable live behavior, alter Paper-order
  behavior, select a model, or add a dashboard/report workflow.

## Work

1. **Data:** add the already allowlisted `SPY/NAS` `1m` route to the existing
   source-safe capability-probe interface. Preserve the current QQQ/NAS and
   SPY/AMS evidence unchanged.
2. Run one bounded `PINC=1` capability probe. Record only accepted-page count,
   categorical limit/error count, continuation category, cursor-progress
   category, historical-range category, and elapsed-time bucket.
3. Treat the route as continuation-capable only if two or more accepted pages
   have strict non-overlapping backward cursor/date progress and no duplicate
   conflict. A terminal page, missing cursor, stalled cursor, or duplicate
   conflict closes **only** SPY/NAS as `source_limited`.
4. If continuation is proven, register only SPY/NAS in the existing durable
   serial collector and perform a bounded bootstrap of at most 20 accepted
   pages. Persist its cursor, counts, pace, recovery class, and next action.
   Do not add another symbol, endpoint, or scheduler in this objective.
5. **Validation:** add focused tests for route allowlisting, strict progression,
   source-limited closure, cursor checkpoint recovery, and no account/order/live
   surface. Keep raw provider rows mocked in tests.

## Completion

- A source-safe external probe receipt records the exact SPY/NAS result.
- Either the route has a durable serial cursor checkpoint after its bounded
  bootstrap, or it is truthfully closed as source-limited without a provider-wide
  claim.
- No KIS account/order call, live route, secret output, raw-row Git artifact,
  model promotion, or new approval gate exists.
- Refresh the Data and orchestration stateboards, replace this file with exactly
  one next objective, then continue.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Probe KIS intraday continuation route`
