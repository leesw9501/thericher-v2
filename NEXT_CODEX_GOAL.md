# Next Codex Goal

## Objective

Complete `kis-paper-intraday-direct-collection-capability-probe-v1`: run one
bounded direct KIS Paper market-data collection through the existing
`session-capture` collector path to distinguish a direct collector/provider
result from the task-owned host-dispatch result. This advances the data
recovery loop without treating either outcome as session completeness, finality,
model eligibility, Paper-trading, or live evidence.

## Boundaries

- `KIS_PAPER_*` reads for this one collector invocation are standing-authorized
  by `AGENTS.md`; use no other credential and never read or route `KIS_LIVE_*`.
  Do not call account, position, order, cancel, modify, broker, or live routes.
- Do not invoke, modify, reinstall, or start a Windows task, scheduler, or
  Docker service. Run the existing host collector once, with one in-memory
  client and its existing pacing/recovery controls; do not add a scheduler,
  retry loop, parallel flood, or timing/pacing change.
- Scope the probe to `QQQ/NAS` and `SPY/AMS`, `session-capture`, and the
  existing four-pages-per-target maximum. Keep any raw response/cache bytes
  only under `D:\market_data`; never print, log, artifact, or Git raw rows.
- Retain only source-safe aggregate outcome, closed reason category if the
  existing collector emits one, timestamps, opaque run identity, and external
  relative receipt/hash pointers. Do not retain or expose secrets, account
  identifiers, raw responses, command output, private runtime state, or order
  identifiers.
- Preserve `THERICHER_MODE=off`; the probe must not reach local-Paper,
  conditional session, dashboard, or any downstream consumer.

## Required Work

1. Reattest the existing collector's source contract and its tests before the
   call: direct mode must use only the allowlisted KIS Paper market-data path,
   external market-data/artifact roots, and no Paper/session/order branch.
2. Run exactly one host-side direct `session-capture` invocation with the
   predeclared two-symbol/four-page scope. Capture no command output beyond an
   allowlisted source-safe result. On a bounded failure, record the existing
   closed category or `reason_unavailable`; do not retry in this objective.
3. Reattach only the exact probe-owned source-safe receipt/cache aggregate and
   classify the result narrowly as `succeeded`, `nonzero`, or `unavailable`.
   A direct success does not prove a Scheduler/Docker cause; a direct nonzero
   does not prove provider cause or authorize a collector change.
4. Add only focused tests or a source-safe reader needed to prove the direct
   probe cannot read live/account/order credentials or invoke a downstream
   Paper branch. Update Data, Engine Research, Execution, orchestration,
   `HANDOFF.md`, and `RUNBOOK.md` with the narrow result.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe direct-probe result for the exact bounded scope, with no
  account/order/Paper/live call and no raw/secret/output retention.
- Strongest kill test: a route outside the two symbols, four-page cap, named
  market-data path, or external-root policy rejects before any KIS request;
  the probe cannot call a Paper/session/order branch.
- The conclusion stays asymmetric: it distinguishes only the direct collector
  result from the prior task-owned host-dispatch result, not Scheduler origin,
  Docker/container entry, provider cause, coverage, finality, model, PnL, or
  live behavior.
