# Next Codex Goal

## Objective

Build one small, deterministic, development-only daily outcome materializer
paired with the existing `SPY`/`QQQ`/`IWM` feature result.

This advances feature/model research preparation. It must not train a model or
turn the broad Yahoo source into campaign, paper-trading, ranking, promotion, or
profitability evidence.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Ask Claude for a short leakage
falsification check before changing the data-to-research boundary, then invoke
the Review checkpoint.

## Boundaries

- Do not read `.env`, credentials, or account data; make no network, KIS, or
  broker call, and leave `THERICHER_MODE=off`.
- Use only the existing static broad-daily wrapper and its feature result. Do
  not acquire, rewrite, widen, or copy market data; do not breach the `D:`
  free-space floor.
- Do not train a model, use the GPU, create decisions, candidates, a campaign,
  local/external orders, artifacts, or a profitability claim.
- Keep the existing Data raw-bar boundary closed to generic callers. Do not add
  a provider framework, feature/label registry, scheduler, dashboard, report
  family, or v1-style gate.

## Required Work

1. Let Data and Engine Research define one explicit one-observed-session daily
   outcome for each feature row, with unambiguous timing: features at completed
   session `t`, outcome derived only from the next observed completed session,
   and an explicit statement that the outcome is unavailable at `t`.
2. Keep the result immutable and in memory. Preserve the source hash and all
   development-only limitations, including raw corporate-action uncertainty,
   survivorship, unproven PIT membership, and unproven delisting coverage.
3. Add focused tests for session alignment across weekend/holiday gaps,
   deterministic ordering, feature/outcome timing separation, source
   reattestation, no generic raw-bar or `CatalogedBars` bypass, and rejection of
   any attempt to use the result as a campaign or local-paper input.
4. Update the Data and Engine Research stateboards, `HANDOFF.md`, and this next
   goal before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add development daily outcome materializer`
