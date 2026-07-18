# Next Codex Goal

## Objective

Diagnose the rejected KIS virtual-paper overseas open-order inquiry using only
public official documentation and the existing redacted failure evidence.

This advances paper-trading readiness without touching an account or submitting
an order.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, Execution, and Review stateboards.

## Authority And Boundaries

- Do not read `.env`, credentials, account identifiers, or `KIS_LIVE_*`.
- Do not call a KIS API, submit, cancel, modify, or query an order/account, or
  change `THERICHER_MODE`.
- Public official KIS documentation and official GitHub examples may be read.
- Keep the existing redacted `open_orders_rejected` evidence immutable.
- Do not propose a paper capital envelope, canary order, live behavior, new
  broker framework, worker, scheduler, dashboard, report/gate family, or model
  change.

## Required Work

1. Execution compares the exact virtual-paper host, endpoint, method, TR ID,
   required query fields, continuation behavior, and account-product handling
   in `execution.kis_readonly` against current official sources.
2. If a documented mismatch is proven, make only the smallest isolated
   read-only correction and add fake-transport tests. If no mismatch is proven,
   record the precise non-secret operator verification needed for a future retry.
3. Data and Review independently check that no market-data, credential, or
   process-sprawl change leaked into the diagnosis.
4. Refresh stateboards, `HANDOFF.md`, and this next single goal; verify, commit,
   and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

Report the official sources consulted, exact proven mismatch or remaining
operator check, tests, commit/push result, intentionally omitted work, and the
next recommended goal.

## Suggested Commit Message

`Diagnose KIS paper open-order access`
