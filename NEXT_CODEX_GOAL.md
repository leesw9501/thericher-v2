# Next Codex Goal

## Objective

Complete `kis-intraday-head-static-task-contract-reattest-v1`: determine
whether the installed `thericher-kis-paper-intraday-head` task's source-safe
static task, runner, and Compose contract still matches the checked-in
`session-capture` collector contract behind the current
`collection_exit_nonzero / reason_unavailable` observation. This advances the
market-data recovery loop without inferring a provider cause, session
completeness, finality, or model eligibility.

## Boundaries

- Do not invoke, modify, reinstall, or start a Windows task, Docker service,
  collector, KIS route, broker route, or scheduler. Do not read `.env`, any
  credential, `KIS_LIVE_*`, raw market rows, private runtime state, or task
  output.
- Inspect only source-safe Task Scheduler metadata, checked-in runner and
  Compose source, and the existing source-safe invocation/terminal readers.
  Do not use a current/latest artifact selector or infer a cause from task exit
  code, cache time, or a missing receipt.
- Retain only component-level match/mismatch/unavailable categories and hashes
  under `D:\thericher-v2\model-artifacts`; no command text, secret, account,
  market, broker, or private-state content belongs in Git or a stateboard.
- A matching contract retains the existing scoped `reason_unavailable`; a
  mismatch is a bounded follow-on repair input, not permission to alter timing,
  pacing, task configuration, or a downstream consumer in this objective.

## Required Work

1. Add one small static inspector that reads only the exact installed task's
   source-safe Scheduler metadata and compares its enabled/action/trigger/
   settings shape to the checked-in scheduler installer, runner, and
   credential-free Compose parse. It must retain and emit only categorical
   results, never action command text, paths, cache metadata, or task output.
2. Reattach the current invocation/terminal reader result only as the known
   task-stage context. Classify the static contract as `matches`, `mismatch`,
   or `unavailable`; retain a component category only for a proven mismatch.
3. Treat `Running` as an observational state, not a mismatch. Require the
   action comparison to prove the first `session-capture` collection route;
   it must not overstate the later conditional Paper-session branch as
   read-only.
4. If a behavior change is proposed from the result, obtain a concise
   falsification-first Claude drift-check before relying on it. Otherwise do
   not call Claude for the static audit alone.
5. Refresh Data, orchestration, `HANDOFF.md`, and `RUNBOOK.md`; run required
   verification, commit, push, replace this file with exactly one material next
   company objective, and continue.

## Completion Evidence

- One source-safe static contract result tied to the named installed task and
  the checked-in session-capture route, with no task/Docker/KIS invocation.
- Strongest kill test: a missing, disabled, multi-action, unexpected-trigger,
  runner, Compose-profile, or settings mismatch cannot be reported as
  `matches`, while `Running` alone does not become a false mismatch.
- No task timing, collector pacing, scheduler definition, KIS call, raw data,
  model, GPU, Paper order, PnL, or live behavior changes in this objective.
