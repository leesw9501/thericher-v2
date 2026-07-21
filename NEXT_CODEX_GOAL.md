# Next Codex Goal

## Objective

During the next caller-confirmed regular Nasdaq session, make exactly one fresh,
prepared KIS virtual-paper raw-`1m` market-data observation for literal `QQQ` /
`NAS`, then record only its sanitized outcome and keep the KIS capability
unqualified.

This is `kis-paper-raw-minute-observation-v1`, not a retry, widening, or
interpretation of terminal v4. The operator has already authorized isolated
`KIS_PAPER_*` market-data reads and goal-owned scheduling. The active
`thericher-kis-raw-minute-observation-v1` Codex automation is one self-expiring
invocation only; it must not run outside its exact date/session guard or create
a retry.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `agents/data.md`, and `agents/execution.md`.
3. Read `scripts/observe_kis_paper_raw_minute.py`, its observer module, and
   focused tests before any execute attempt.
4. Check the external one-shot state first. If it is reserved or malformed,
   classify recovery and do not retry.

## Work Packages

### Data Agent

- Before an Execution invocation, independently check the Nasdaq calendar for
  a closure or early close, then freeze the actual current New York date and
  the literal observation scope. Do not invoke the script or read its
  configuration: Data does not call KIS or read credentials.
- Inspect only the sanitized summary and durable state. Record the result as
  `observed` or `rejected`; do not store raw data in Git or under `D:\market_data`.
- Do not qualify timestamps, completed bars, retention, storage rights,
  `5m`/`10m`, model inputs, or a paper strategy from this one observation.

### Execution Agent

- During a current New York weekday regular session only, after Data's
  calendar confirmation, the authorized one-shot automation may invoke exactly
  one credential-touching observation:

  ```powershell
  uv run python scripts\observe_kis_paper_raw_minute.py `
    --execute `
    --confirm-regular-nasdaq-session `
    --session-date YYYY-MM-DD
  ```

- Use the frozen actual current New York date. Do not alter symbol, exchange,
  page count, artifact root, or control objective.
- Confirm the observation remained separate from orders, account/balance/
  position/buying-power/open-order reads, capital, route/header work, and the
  disabled adapter. Do not add a transport or order path.

### Validation

- Independently review the sanitized summary, marker/ledger lifecycle, request
  bound, redaction, and no-retry recovery state. Do not tune or promote any
  model from this result.

## Hard Boundaries

- Do not submit, cancel, modify, or simulate a KIS order; do not read
  `KIS_LIVE_*`, change `THERICHER_MODE`, set capital, or enable an adapter.
- Do not call account, balance, position, buying-power, open-order, or live
  endpoints.
- Do not execute before a real current-session/date guard and explicit
  calendar confirmation both pass. Outside the session, make no KIS call and
  do not create a daemon, retry loop, or unscoped recurring schedule. The named
  self-expiring automation is authorized for this one objective only.
- Do not create a model, GPU job, dashboard feature, provider, or dataset from
  the observation.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Record bounded KIS raw minute observation`
