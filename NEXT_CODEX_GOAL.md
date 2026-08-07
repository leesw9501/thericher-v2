# Next Codex Goal

## Objective

Build `private-kis-paper-account-snapshot-refresh-v1`.

Use the existing named read-only KIS Paper account bridge to create one fresh,
sanitized local account snapshot that the completed loopback-only private
dashboard can display. This is an operational-observability step for Paper
trading, not an order or strategy feature.

## Hard Boundaries

- Read only `KIS_PAPER_*` through the existing account-read bridge. Never read,
  reference, route, log, or persist `KIS_LIVE_*`.
- Do not submit, modify, cancel, simulate, or imply a broker order. Do not call
  an order, quote, market-data, or live endpoint unless the existing
  read-only-account bridge demonstrably needs that exact documented endpoint.
- Keep raw responses, credentials, account identifiers, and dashboard tokens
  out of Git, logs, browser HTML, screenshots, and external artifacts.
- Preserve the dashboard's loopback-only host boundary, explicit
  container-bind exception, local pause controls, existing KIS collectors, and
  local-paper replay behavior.
- A missing, stale, malformed, or rejected account read must render an explicit
  unavailable state; do not invent cash, positions, prices, open orders, or
  orderability.
- Do not add a second scheduler or a new broker client when the existing named
  bridge suffices. Do not alter model research, GPU allocation, strategy
  selection, or market-data collection.

## Required Work

1. Run a concise Throughput Review. The dashboard package is complete and the
   next ready Execution package is the existing read-only account bridge; the
   task-owned Data collection and independent research preparation continue on
   their own ownership.
2. Reattest the current bridge, snapshot schema, dashboard reader, and Compose
   ownership. Prove statically that the dashboard itself imports neither a KIS
   client nor order functionality and that the bridge cannot read live
   configuration or call an order endpoint.
3. Run one bounded KIS Paper account-refresh attempt through the existing
   bridge. Retain only its sanitized snapshot in the existing private runtime
   root and a source-safe categorical result or receipt outside Git. Never
   print raw response data, credentials, or account identifiers.
4. Reopen the local Docker dashboard and verify the resulting available or
   unavailable state against the bridge's categorical outcome. Exercise no
   broker-order action; a local pause-control round trip is optional only when
   it helps validate that the snapshot refresh did not change control state.
5. Add focused tests for bridge-only `KIS_PAPER_*` ownership, absence of live
   config and order endpoints, sanitization of the snapshot projection,
   unavailable/stale rendering, and a dashboard route that remains broker-free.
   Reuse existing contracts rather than duplicate them.
6. Refresh the Execution, Infra, orchestration, and handoff stateboards with
   only the current snapshot result, evidence pointer, recovery class, and next
   action. Ask Claude only if implementation would change broker authority,
   dashboard architecture, or execution recovery semantics.

## Verification

```powershell
.\scripts\run_parallel_tests.ps1 -RequireCleanTempRoot
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
docker compose config --quiet
```

## Suggested Commit Message

`Refresh private KIS Paper account snapshot`
