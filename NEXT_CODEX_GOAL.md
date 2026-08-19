# Next Codex Goal

## Objective

Complete `kis-paper-intraday-quarantined-head-recovery-capture-v1`: after the
completed due-gate container attempt independently fetched a candidate then
quarantined conflicting retained head chunks for both targets, make one later
clean-capture attempt through the exact existing Compose collector. This tests
only the existing quarantine recovery path; it is not a cache edit, retry loop,
Scheduler claim, session-completeness, finality, model, Paper-trading, or live
evidence.

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

1. Reattest the existing service contract, focused tests, quarantine semantics,
   and shared token-start gate before the call. The non-mutating gate check
   must report `due`; otherwise retain a scoped `deferred` result and do not
   invoke Compose. A due precheck is advisory only; the service's own atomic
   claim remains authoritative.
2. Run exactly one direct Compose `session-capture` invocation with the
   predeclared two-symbol/four-page scope only when the precheck is due.
   Capture no command output beyond an allowlisted source-safe result. Do not
   manually edit, clear, restore, or inspect raw cache bytes. On a bounded
   failure, a lost atomic token race, or another retained-cache conflict,
   record the existing closed category and stop this recovery path.
3. Reattach only the exact new source-safe receipt/cache aggregate and
   classify it narrowly as `recovered`, `nonzero`, `deferred`, or
   `unavailable`. A clean result is only an isolated capture recovery; it does
   not prove a Windows Task/Scheduler cause, complete session, provider
   finality, a qualified model input, or a Paper consumer.
4. Add only focused tests or a source-safe reader needed to prove the recovery
   probe cannot read live/account/order credentials, mutate raw bytes outside
   the existing quarantine path, or invoke a downstream Paper branch. Update
   Data, Engine Research, Execution, orchestration, `HANDOFF.md`, and
   `RUNBOOK.md` with the narrow result.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One source-safe post-quarantine result for the exact bounded scope, with no
  account/order/Paper/live call and no raw/secret/output retention; or a
  source-safe `deferred` result with no Compose invocation.
- Strongest kill test: a Compose route outside the named service, two symbols,
  four-page cap, named market-data path, off-mode/external-root policy, or
  credential allowlist rejects before Docker or any KIS request; a non-due
  gate never launches Compose, a recurring retained-cache conflict closes this
  recovery path, and the probe cannot call a Paper/session/order branch.
- The conclusion stays asymmetric: it distinguishes only one post-quarantine
  capture result from the prior direct-host/container/task-owned observations,
  not Scheduler origin, provider cause, coverage, finality, model, PnL, or
  live behavior.
