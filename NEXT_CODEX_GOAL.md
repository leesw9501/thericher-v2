# Next Codex Goal

## Objective

Run exactly one post-diagnosis KIS virtual-paper read-only discovery through
the existing bounded client.

This advances paper-trading readiness by obtaining one live-like account-state
observation, never by submitting an order.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data, Engine Research, Execution, and Review stateboards.

## Authority And Boundaries

- The existing operator approval permits one use of only the four
  `KIS_PAPER_*` values through `load_kis_paper_config`; do not inspect or print
  `.env`, credentials, account identifiers, or `KIS_LIVE_*`.
- Use only the fixed virtual host and existing `execution.kis_readonly` client.
  Make one discovery attempt; do not retry it automatically.
- Keep `THERICHER_MODE=off`; do not submit, modify, or cancel an order, query a
  live account, allocate paper capital, or propose a capital envelope.
- Persist only the existing external redacted evidence shape under
  `D:\thericher-v2\model-artifacts`. Do not copy account state into Git, logs,
  Claude prompts, or the completion report.
- Do not add a broker framework, worker, scheduler, dashboard, report/gate
  family, market-data change, or model work.

## Required Work

1. Execution runs one bounded discovery using the existing CLI/client. It must
   preserve the prior failure artifact, keep submission disabled, and write one
   new external evidence artifact only for this attempt.
2. If it fails closed, do not retry. Inspect only its status, reason, fixed
   endpoint/TR ID, and HTTP-status metadata; never persist or report response
   text or response-derived codes.
3. If it collects a snapshot, confirm only that the reconciliation remains
   `safe_to_submit: false`; do not expose values or advance to capital planning.
4. Data and Review confirm that the run changed no market data and added no
   process sprawl. Refresh stateboards, `HANDOFF.md`, and this next single goal,
   then verify, commit, and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

Report only the safe discovery outcome, external artifact path, tests,
commit/push result, intentionally omitted work, and the next recommended goal.

## Suggested Commit Message

`Retry KIS paper read-only discovery`
