# Next Codex Goal

## Objective

Complete `norgate-trial-d1-capability-reprobe-v1`: run exactly one bounded,
host-only Norgate US Equities D1 capability probe through the existing isolated
Norgate Python runtime. This is a fresh local capability measurement after the
operator's updater work, not a retry loop, subscription claim, campaign,
model-selection, KIS, Paper, or live action.

## Hard Boundaries

- Do not read `.env`, credentials, or any `KIS_*` value; do not call KIS,
  invoke a broker, submit or alter an order, invoke Task Scheduler, or start
  Docker services.
- Use only `D:\thericher-v2\host-runtimes\norgate-python\Scripts\python.exe`
  and the existing `scripts\run_norgate_trial_daily_capability_probe.py` path.
  Do not install, update, configure, start, close, or automate the Norgate Data
  Updater; do not use a project Python runtime as a substitute.
- Use one unique run label and one invocation. Never print raw Norgate rows,
  prices, symbols, dates, database paths, subscription values, or client output.
  Keep any source bytes under `D:\market_data`, generated evidence outside Git,
  and only source-safe categorical output in documentation.
- If the local API is unavailable, catalog is missing, the host runtime is
  absent, or the probe is non-qualifying, record that scoped category and stop
  this probe without a foreground wait, duplicate launch, retry loop, or
  operator-approval request. Do not launch the D1 pilot in this objective.

## Required Work

1. Verify the isolated host runtime exists, then run the existing probe once
   with a new run label. Reattach only its source-safe output/receipt facts.
2. Classify the result narrowly as `qualified_for_offline_research`,
   `input_unavailable`, or `local_api_not_ready`; do not infer an update,
   subscription, rights, full-history, corporate-action, or model result.
3. Refresh Data, Engine Research, and orchestration stateboards, `HANDOFF.md`,
   and `RUNBOOK.md`. Keep Research Steward GPU custody and Execution
   non-promoting; a qualified result may only create a distinct next Data goal.

## Verification

Run focused Norgate capability/receipt tests, the goal-boundary authority test
group, Ruff, credential-free Compose configurations, and `git diff --check`.
Report only source-safe facts and the external evidence pointer.
