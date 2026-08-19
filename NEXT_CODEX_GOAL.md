# Next Codex Goal

## Objective

Complete `kis-paper-intraday-container-post-gate-capability-probe-v1`: after
the completed first container attempt yielded before any token POST because the
shared token-start gate was not due, make one new, post-gate attempt through
the exact existing `kis-paper-intraday-head` Compose collector. This separates
a due-gate container result from the direct-host result and the task-owned
host-dispatch result without treating any result as Scheduler origin, session
completeness, finality, model eligibility, Paper-trading, or live evidence.

## Boundaries

- `KIS_PAPER_*` reads for this one collector invocation are standing-authorized
  by `AGENTS.md`; use no other credential and never read or route `KIS_LIVE_*`.
  Do not call account, position, order, cancel, modify, broker, or live routes.
- Do not invoke, modify, reinstall, or start a Windows task or scheduler. Run
  only the existing `kis-paper-intraday-head` Compose service once with
  `--rm --no-deps --pull never`; do not build, pull, add a service, add a
  scheduler, retry loop, parallel flood, or timing/pacing change.
- Reattest before execution that the service has its checked-in
  `session-capture` command, `THERICHER_MODE=off`, only its two KIS
  market-data variables, and the external `D:\market_data`/artifact roots.
  Scope remains `QQQ/NAS` and `SPY/AMS` with the existing four-page maximum.
  Keep raw response/cache bytes only under `D:\market_data`; never print,
  log, artifact, or Git raw rows.
- Retain only source-safe aggregate outcome, closed reason category if the
  existing collector emits one, timestamps, opaque run identity, and external
  relative receipt/hash pointers. Do not retain or expose secrets, account
  identifiers, raw responses, command output, private runtime state, or order
  identifiers.
- Preserve `THERICHER_MODE=off`; the probe must not reach local-Paper,
  conditional session, dashboard, or any downstream consumer.

## Required Work

1. Reattest the existing service contract, focused tests, and the shared
   token-start gate before the call. The non-mutating gate check must report
   `due`; if it does not, retain a scoped `deferred` result and do not invoke
   Compose in this objective. A due precheck is advisory only; the service's
   own atomic claim remains authoritative.
2. Run exactly one direct Compose `session-capture` invocation with the
   predeclared two-symbol/four-page scope only when the precheck is due.
   Capture no command output beyond an allowlisted source-safe result. On a
   bounded failure or a lost atomic token race, record the existing closed
   category or `reason_unavailable`; do not retry in this objective.
3. Reattach only the exact probe-owned source-safe receipt/cache aggregate and
   classify the result narrowly as `succeeded`, `nonzero`, `deferred`, or
   `unavailable`. A container success does not prove a Windows Task/Scheduler
   cause; a container nonzero does not prove a provider cause or authorize a
   collector change.
4. Add only focused tests or a source-safe reader needed to prove the
   post-gate container probe cannot read live/account/order credentials or
   invoke a downstream Paper branch. Update Data, Engine Research, Execution,
   orchestration, `HANDOFF.md`, and `RUNBOOK.md` with the narrow result.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe post-gate result for the exact bounded scope, with no
  account/order/Paper/live call and no raw/secret/output retention; or a
  source-safe `deferred` result with no Compose invocation.
- Strongest kill test: a Compose route outside the named service, two symbols,
  four-page cap, named market-data path, off-mode/external-root policy, or
  credential allowlist rejects before Docker or any KIS request; a non-due
  gate never launches Compose, and the probe cannot call a Paper/session/order
  branch.
- The conclusion stays asymmetric: it distinguishes only the new due-gate
  containerized collector result from the direct-host and task-owned
  host-dispatch results, not Scheduler origin, provider cause, coverage,
  finality, model, PnL, or live behavior.
