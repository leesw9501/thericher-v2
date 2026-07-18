# Next Codex Goal

## Objective

Diagnose the virtual-paper overseas balance failure using only public official
documentation and the existing redacted evidence.

This advances paper-trading readiness without touching an account or making a
second probe.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, Execution, and Review stateboards.

## Authority And Boundaries

- Do not read `.env`, credentials, account identifiers, or `KIS_LIVE_*`.
- Do not call a KIS API, submit, cancel, modify, or query an order/account, or
  change `THERICHER_MODE`.
- Public official KIS documentation and official GitHub examples may be read.
- Preserve the two immutable redacted failure artifacts. The newest safe facts
  are `balance_rejected`, `balance`, `VTTS3012R`, and HTTP `500`; do not infer a
  root cause from them or report raw response content.
- Do not propose paper capital, execute a new probe, enable live behavior, or
  add a broker framework, worker, scheduler, dashboard, report/gate family,
  market-data change, or model work.

## Required Work

1. Execution compares the fixed virtual balance host, GET path, `VTTS3012R`,
   query fields, US-exchange coverage, continuation behavior, and 8-2 account
   product handling against current official public sources.
2. If a documented mismatch is proven, make only the smallest isolated
   read-only correction with fake-transport tests. Otherwise, write a ranked
   non-secret hypothesis list and the exact operator pairing check that would
   distinguish it; do not make another KIS call.
3. Data and Review independently confirm no market-data, credential, or
   process-sprawl change leaked into the diagnosis. Refresh stateboards,
   `HANDOFF.md`, and this next single goal; verify, commit, and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

Report official sources, the exact proven mismatch or ranked remaining
hypotheses, tests, commit/push result, intentionally omitted work, and the next
recommended goal.

## Suggested Commit Message

`Diagnose KIS paper balance access`
