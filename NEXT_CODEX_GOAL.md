# Next Codex Goal

## Objective

Resolve one narrow data-coverage question: determine whether Tiingo IEX can
return a non-overlapping historical 5-minute window before the r1 snapshot's
`2026-01-13` first session.

This advances data collection only. It must not create a second snapshot,
change r1, start model/paper/campaign work, or claim that an older window is
available until an exact bounded response proves it.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Assign the read-only inventory or
probe design to the Data role. Do not ask Claude for a new-source acceptance:
this is a scope probe of the already accepted Tiingo IEX endpoint, not a new
provider or lineage contract.

## Boundaries

- Read only `TIINGO_API_TOKEN` through the existing approved safe reader, and
  never print, log, commit, artifact, or send it to Claude.
- Use at most two bounded Tiingo IEX probe requests in total. Start with one
  SPY request for `2024-01-02` through `2024-06-28`, `5min`, explicit OHLCV
  columns, `afterHours=false`, and `forceFill=false`.
- Do not persist raw response bytes, a response hash, a new snapshot, or a
  provider/cache artifact from the probe. Record only non-secret request/result
  metadata needed for the next decision.
- Do not call KIS, read other credentials, submit/simulate orders, use GPU,
  train, create a candidate/campaign, or claim performance.
- Do not pay, log in, bypass access controls, or contact a new provider.
- Preserve the 20% warning and 15% D-drive floor, although this probe should
  not write market data.

## Required Work

1. Reattest r1 metadata offline and confirm its observed response cap: 10,000
   bars per symbol and first shared session `2026-01-13`.
2. Make the one exact SPY probe. Record only HTTP result, row count, first and
   last timestamp, and response schema; do not save the response.
3. If it returns a non-overlapping 2024 window, close the question as
   `windowed access supported` and prepare the next single objective for one
   chunked immutable r2 snapshot, with predeclared windows, request count,
   storage estimate, and no overwrite of r1.
4. If it returns r1-equivalent/latest data, empty data, or an access error,
   use at most one clearly justified second probe to distinguish a date-filter
   issue from unavailable history. Then close the path with exact evidence and
   recommend either a different eligible source or a concise paid-data request
   only when it materially solves the gap.
5. Update Data and Engine Research stateboards, `HANDOFF.md`, and this file
   before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Probe Tiingo IEX historical window access`
