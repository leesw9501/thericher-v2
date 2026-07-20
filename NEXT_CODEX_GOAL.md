# Next Codex Goal

## Objective

Harden the raw-`1m` qualification runner entirely offline so it never makes a
continuation request unless the first page establishes a deterministic oldest
bar for the documented one-minute-prior `KEYB` calculation.

## Required Reads

1. Run `.\scripts\start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`,
   `ARCHITECTURE.md`, `agents/data.md`, and `agents/execution.md`.
3. Read the raw-minute client, qualification runner, and fake-transport tests.
   Treat the terminal v4 summary and reservation marker as metadata only.

## Work Packages

### Execution Agent

- Identify the smallest pre-continuation check that proves the first page is
  strictly descending by one exchange-local minute before its final row is used
  for `KEYB`.
- Add focused offline tests for swapped, duplicate, and gapped first pages:
  each must stop before a second GET while preserving the one-token/two-page
  maximum.
- Keep the existing `QQQ` / `NAS` / `1m` endpoint allowlist and sanitized
  failure behavior. Do not create a retry facility or alter the v4 artifact.

### Data And Validation

- Keep the trusted capability registry unchanged and state why local ordering
  tests cannot qualify `1m`, `5m`, `10m`, `1h`, or `3h`.
- Independently check that the outcome makes no on-wire, data-retention,
  capability, or paper/live claim.

## Hard Boundaries

- Do not read `.env` or credentials and do not call KIS, Tiingo, Norgate, or a
  broker.
- Do not submit, modify, or cancel orders; leave `THERICHER_MODE=off`.
- Do not run GPU/model work, create a dataset/cache, change capital authority,
  or alter the v4 artifact, marker, or ledger.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Guard KIS minute continuation ordering`
