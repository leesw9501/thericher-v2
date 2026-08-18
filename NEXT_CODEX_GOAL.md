# Next Codex Goal

## Objective

Complete `kis-intraday-full-session-capture-recovery-v1`: turn the existing
single KIS Paper intraday-head collection path into a verifiably complete M1
regular-session accumulator, or establish the exact source/scheduler constraint
that prevents it and deploy the smallest evidence-backed recovery. This advances
actual data collection, not a model, PnL claim, Paper decision, or live route.

## Hard Boundaries

- Use KIS Paper market-data only through the named Data owner path. Never call
  an account, order, position, quote, or live endpoint; never read or route
  `KIS_LIVE_*`.
- Do not read credentials, raw M1 rows, account values, private intents, broker
  bodies, or identifiers.
- Keep one task, one collector lock, the measured one-second request-start
  gate, token-start guard, cooldown, and external cache/artifact roots. Do not
  add a parallel flood or a duplicate task.
- Do not manually invoke the existing quote-session/Paper task to test this
  work. A later scheduled data result remains task-owned.
- Preserve the immutable 2026-08-15 and 2026-08-17 scoped
  `input_unavailable/session_coverage_incomplete/current_session_short`
  evidence. The new causal-attestation writer may not attach or backfill either
  terminal.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Obtain a concise Claude falsification-first drift check before any installed
   schedule or dispatcher change. It must challenge the inferred capture-window
   geometry, duplicate-run risk, provider-continuation assumption, and recovery
   kill test.
2. Add a metadata-only capture-topology audit that uses the existing cache
   index/manifests and source-safe Task Scheduler facts, never raw M1 rows, to
   distinguish trigger loss, overlap, source-window limits, and retained-cache
   topology. Its output must give aggregate session coverage and an explicit
   bounded recovery recommendation.
3. When the audit supports a fix, update only the existing task/dispatcher
   contract and its installer/static tests to accumulate a whole 390-minute
   regular session. Keep downstream QQQ/SPY Paper consumers unchanged and do
   not create another task.
4. Build and statically reattest the existing image/task definition, then let
   the existing task own the next observation. Update Data, Engine Research,
   Execution, orchestration, HANDOFF, and RUNBOOK facts. Do not promote a model
   or Paper input merely because a collection path is installed.

## Verification

Run focused contract tests, the goal-boundary authority group, Ruff, and both
Compose configurations. Report the metadata-only audit and any task deployment
fact without raw rows or credentials.
