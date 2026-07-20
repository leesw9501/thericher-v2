# Next Codex Goal

## Objective

Prepare one fresh, bounded KIS virtual-paper raw-`1m` market-data observation
for `QQQ` / `NAS` during a future regular Nasdaq session, without reusing the
terminal 2026-07-20 v4 observation or turning a market-data capability into an
order capability.

The operator has already authorized isolated `KIS_PAPER_*` market-data reads.
This goal prepares the smallest executable observation boundary first; a later
single attempt may run only after its own exact session/date guard passes.

## Required Reads

1. Run `./scripts/start_next_codex_task.ps1`.
2. Read `HANDOFF.md`, `AGENTS.md`, `DECISIONS.md`, `ARCHITECTURE.md`,
   `RUNBOOK.md`, `agents/data.md`, and `agents/execution.md`.
3. Read the existing raw-minute client, terminal v4 runner, capability record,
   and focused tests before editing.
4. Ask Claude CLI for a short falsification-first drift check before adding a
   new observation worker or changing recovery/side-effect behavior.

## Work Packages

### Data Agent

- Reuse existing typed client and sanitizer boundaries where possible; do not
  duplicate or reopen the terminal v4 reservation, artifact, or date policy.
- Add the smallest separate preparation path for one future `QQQ` / `NAS`
  raw-`1m` observation. It must default to dry-run, require an explicit execute
  confirmation, and reject every date/window except a caller-declared regular
  Nasdaq session verified immediately before execution.
- Bound a future execution to one paper token, one first page, and at most one
  continuation page. Retain only sanitized counts, timestamp bounds, field
  presence, and continuation facts outside Git; never raw prices, volumes,
  cursors, credentials, account identifiers, or responses.
- Keep the capability `observed` or `rejected`; do not qualify timestamps,
  retention, completed bars, storage rights, `5m`/`10m`, a model input, or a
  paper strategy under this goal.

### Execution Agent

- Review the preparation boundary for complete separation from orders,
  balances, positions, capital, route/header contracts, and the disabled
  adapter. Do not add an order client or transport.

### Validation

- Independently check one-shot bounds, redaction, recovery, and no accidental
  broker-order side effect.

## Hard Boundaries

- Do not submit, cancel, modify, or simulate a KIS order; do not read
  `KIS_LIVE_*`, change `THERICHER_MODE`, set capital, or enable an adapter.
- Do not call account, balance, position, buying-power, open-order, or live
  endpoints. Do not read `.env` during dry-run or tests.
- Do not run a network observation until its explicit execute/date/session
  guard is implemented, tested, and passes. No background scheduler or daemon.
- Do not store market data in Git or raw data in an artifact. Do not create a
  model, GPU job, dashboard feature, or data provider from the observation.

## Verification

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

## Suggested Commit Message

`Prepare bounded KIS raw minute observation`
