# Next Codex Goal

## Objective

Complete `kis-intraday-later-terminal-reattachment-v1`: reattach the first
strictly later task-owned intraday-head terminal after
`intraday-head-20260818T2120005941479Z` using the existing source-safe offline
projection. It may produce only a scoped terminal/coverage/availability
category; it must not infer a broker fill, PnL, alpha, model result, provider
cause, or Scheduler-origin proof from a task outcome.

## Hard Boundaries

- Do not read `.env`, credentials, or any `KIS_*` value; do not call KIS,
  invoke a broker, submit or alter an order, invoke Task Scheduler, or start
  Docker services. Do not manually invoke or duplicate the owning collector.
- Read only the existing source-safe schedule/terminal projection and its
  allowlisted external receipt paths. Do not read, print, copy, hash, or
  persist raw market rows, broker bodies, private intents, or task output.
- Do not alter the task, its timing, pages, Docker path, collector, receipt
  writer, causal-attestation writer, or a consumer. A nonzero category is a
  diagnostic only; a successful partial terminal is not comparable failure
  evidence.
- The 2026-08-18 baseline is not a later result. If the current pointer still
  binds that run, retain `marker_not_later` or equivalent scoped stale state;
  do not count it as a second observation or foreground-wait for a new run.

## Required Work

1. Run the existing offline schedule projection once. If it yields a new,
   valid later run, reattach its matching terminal through the existing reader;
   otherwise record only the returned categorical stale/unavailable state.
2. Compare its opaque run ID and completion time with the fixed baseline before
   classifying it later. Retain only the existing source-safe hashes and
   categories; never write a new receipt merely for an unavailable/stale read.
3. Update Data, Execution, and orchestration stateboards plus `HANDOFF.md`
   only if the categorical state changes. Keep the task-owned next due fact
   non-blocking and move to another ready package rather than waiting.

## Verification

Run focused projection tests if code changes. Report only the source-safe
terminal/receipt pointer, categorical result, and next due/recovery fact.
