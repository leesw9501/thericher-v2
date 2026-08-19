# Next Codex Goal

## Objective

Complete `kis-paper-daily-pair-forward-refresh-v1`: reattest the existing
`QQQ/NAS` and `SPY/AMS` D1 forward cache and, only when its credential-free
preflight reports `collection_required`, perform one exact existing Compose
refresh for the last completed US equity session. This advances source-local
forward data only; it does not prove finality, point-in-time eligibility, a
model, PnL, Paper behavior, or live behavior.

## Boundaries

- Use `KIS_PAPER_*` only through the existing pair-forward market-data service.
  Never read or route `KIS_LIVE_*`, and do not call account, position, order,
  cancel, modify, broker, or live endpoints.
- Use the existing `kis-paper-daily-pair-forward-preflight` and
  `kis-paper-daily-pair-forward` Compose services only. Do not invoke or
  change a Windows task/scheduler, build or pull images, add services, start a
  retry loop, or run parallel collection.
- Preserve `THERICHER_MODE=off`, the fixed QQQ/NAS plus SPY/AMS scope, and
  external cache/artifact roots. Never print, log, artifact, or commit raw
  market rows, credentials, account identifiers, or private runtime state.
- If preflight reports `cache_current`, do not make a credentialed KIS call.
  If it reports `collection_required`, make exactly one direct Compose
  collection attempt. Any defer, conflict, or failure closes that one attempt
  without retry.

## Required Work

1. Reattest the existing Compose contract and focused tests, then run the
   networkless preflight and retain only its source-safe categorical result.
2. When and only when collection is required, run one exact pair-forward
   service invocation and capture only allowlisted source-safe aggregate
   results. Otherwise record that no collection was needed and no KIS call was
   made.
3. Reattach the exact external receipt/cache summary through existing offline
   readers. Retain only its hash/pointer, target-count/category facts, and the
   explicit finality and predictive-eligibility limitation.
4. Add only a focused reader or test required to prove cache-current preflight
   cannot reach KIS collection and that the pair-forward service has no
   live/account/order route. Refresh the active stateboards, `HANDOFF.md`, and
   `RUNBOOK.md` with the narrow result.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe networkless preflight and either a cache-current result with
  no KIS invocation or one exact two-target source-safe collection outcome.
- Strongest kill test: wrong target scope/mode/roots/credential surface,
  preflight reaching KIS collection, or a collected result lacking an immutable
  external receipt and canonical target binding.
- No predictive, PnL, Paper, or live claim follows from this refresh.
