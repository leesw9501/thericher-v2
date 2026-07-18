# Next Codex Goal

## Objective

Assess whether an existing broad US-equity daily snapshot under `D:\market_data`
can support a small, explicitly development-only universe for future research.

This advances data collection and feature/model research. It must not imply
point-in-time membership, model selection, profitability, or readiness for
external paper trading.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Invoke the Review checkpoint.

## Boundaries

- Do not read `.env`, credentials, or account data; make no network, KIS, or
  broker call, and leave `THERICHER_MODE=off`.
- Use existing files under `D:\market_data` only. Do not acquire data, copy raw
  data into Git, or breach the 15% free-space floor.
- Do not train a model or use the GPU. Do not rank, promote, open a holdout,
  claim profitability, or submit a local or external order.
- Do not add a provider framework, scheduler, dashboard, report family, or
  v1-style data gate. Keep any reader or contract narrow and reusable.

## Required Work

1. Let the Data Agent perform a bounded inventory of the existing broad daily
   snapshot: provenance, fields, symbol/date coverage, completeness, and what
   can be established without pretending to know historical universe membership.
2. If the snapshot is usable for development-only research, add the smallest
   hash-bound local reader or selection contract needed to name a small fixed
   universe. Label survivorship and point-in-time limitations directly. If it
   is not usable, record the concrete operator data requirement instead.
3. Ask Claude for a short falsification check if the proposed contract could
   hide survivorship, leakage, or an architecture expansion. Invoke the Review
   checkpoint before integration.
4. Update the Data and Engine Research stateboards, `HANDOFF.md`, and this
   next goal; verify, commit, and push.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Assess broad daily development universe`
