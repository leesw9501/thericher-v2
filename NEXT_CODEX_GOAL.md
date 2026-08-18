# Next Codex Goal

## Objective

Complete `norgate-host-readiness-bridge-v1`: build and run one compact,
host-only Norgate readiness bridge that converts the local client/runtime state
into categorical, source-safe evidence. It may inspect only the client ready
flag, configured-database membership, update metadata in memory, and the two
predeclared local database-root metadata candidates. It must not read a price,
membership, listing, corporate-action, or raw market row.

## Hard Boundaries

- Do not read `.env`, credentials, or any `KIS_*` value; do not call KIS,
  invoke a broker, submit or alter an order, invoke Task Scheduler, or start
  Docker services.
- Use only `D:\thericher-v2\host-runtimes\norgate-python\Scripts\python.exe`
  for the actual bridge. Do not install, update, configure, start, close, or
  automate Norgate Data Updater; do not use the project Python runtime as a
  substitute for an actual client check.
- Never invoke `price_timeseries`, list/index membership, listings, capital
  events, or any existing daily-capability/pilot script in this objective. Never
  print or persist raw Norgate rows, prices, symbols, dates, database paths,
  subscription values, or client output.
- Emit only a fixed categorical schema: host runtime available/unavailable,
  local API ready/not-ready/unavailable, US Equities configured/not-configured,
  and active-root resolution `one`/`none`/`multiple`/`not_checked`. A bridge
  failure is an `input_unavailable` result, not a retry loop or approval wait.

## Required Work

1. Add synthetic tests for source-safe output, no raw-data method access,
   candidate-root resolution, host-runtime failure, and no credential/network
   path. Keep the host bridge independent of project-runtime Norgate imports.
2. Run the bridge once through the isolated host runtime and persist one
   immutable aggregate receipt outside Git. Reattach only its categorical
   result; do not rerun the prior daily capability probe.
3. Refresh Data, Engine Research, and orchestration stateboards, `HANDOFF.md`,
   and `RUNBOOK.md`. Keep Research Steward GPU custody and Execution
   non-promoting; only a `ready/one` result may create a distinct next Data goal.

## Verification

Run focused Norgate bridge/receipt tests, the goal-boundary authority test
group, Ruff, credential-free Compose configurations, and `git diff --check`.
Report only source-safe facts and the external evidence pointer.
