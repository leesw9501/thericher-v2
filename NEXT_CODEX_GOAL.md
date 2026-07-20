# Next Codex Goal

## Objective

Run one bounded, operator-authorized KIS virtual-paper **read-only**
reconciliation through the existing Docker `kis-readonly` profile. Refresh the
local paper-console snapshot or record one sanitized unavailable outcome so the
next true operator decision, if any, is based on current broker evidence.

## Required Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `ARCHITECTURE.md`, `agents/data.md`, and `agents/execution.md`.
3. Read the `kis-readonly` Compose profile, console bridge, snapshot schema,
   and focused tests. Confirm that the current authority permits read-only
   `KIS_PAPER_*` access only.

## Work Packages

### Execution Agent

- Perform exactly one invocation:

  ```powershell
  docker compose --profile kis-readonly run --rm --no-deps kis-readonly
  ```

- It may use only `KIS_PAPER_*` inside the isolated profile. Do not print or
  retain token, account number, symbol, price, balance, position, or raw broker
  response. Preserve the existing Docker-local runtime snapshot and external
  sanitized evidence rules.
- Do not retry a rejected/unavailable result. Use `--recover-evidence` only if
  a fresh complete runtime snapshot exists but its evidence write failed; that
  recovery must make no KIS call.

### Data And Validation

- Confirm that broker-account facts do not qualify market-data timeframes or
  alter the trusted data registry.
- Independently verify that no order, cancel, live call, capital envelope, or
  public exposure can occur through this invocation.

## Decision Boundary

- If the one read is complete and establishes a usable native currency plus an
  empty reconciled account, calculate no capital proposal yet. Report the
  source-labelled available funds and ask the operator to approve or change a
  paper capital envelope in that same currency.
- If it is unavailable or incomplete, record the bounded result and continue
  with another ready offline lane; do not treat it as an account, service, or
  authorization diagnosis.

## Hard Boundaries

- No `KIS_LIVE_*`, order submission, modification, cancellation, or mode change.
- No nonzero paper capital envelope, model/paper promotion, GPU work, or market
  data acquisition.
- Do not mount or log `.env`; do not alter terminal raw-minute v4 evidence.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Refresh KIS paper read-only snapshot`
