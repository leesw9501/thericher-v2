# Next Codex Goal

## Objective

Prepare one decision-ready, no-cost recommendation for the smallest paid source
that could supply US daily point-in-time research evidence: historical universe
membership and delistings, raw OHLCV, and corporate-action lineage.

This advances the data-collection and backtest-validation loop. It is a source
decision, not a purchase, download, provider implementation, model task, or
trading milestone.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
`agents/data.md`, `agents/engine-research.md`, and `agents/review.md`.

Assign Data ownership and ask a temporary Review Agent to check that the result
is one decision memo rather than a provider/gate/report framework. Ask Claude
for a short drift-check only if it is available; do not treat its absence as
approval.

## Boundaries

- Use only official public product, pricing, license, and documentation pages.
- Do not buy, log in, enter payment details, download data, query an API, or
  read `.env` or credentials.
- Do not add a provider, cache, data artifact, dependency, campaign, model,
  GPU job, paper order, KIS access, or live behavior.
- Do not portray Tiingo IEX r1, the failed archive attempt, Yahoo data, or an
  unpurchased supplier as PIT, independent validation, or profitability data.
- Do not request an operator decision until one minimum viable product, current
  cost, rights, coverage, storage estimate, and exact approval question are
  documented from official sources.

## Required Work

1. Compare the minimum viable Sharadar and Norgate offerings using official
   public evidence only. Capture current price/cadence, US universe and delisted
   coverage, point-in-time membership, raw-price and corporate-action semantics,
   delivery/API format, private-use rights, and estimated local storage.
2. State whether either option resolves the active research blocker. Prefer one
   smallest viable product, or explicitly conclude that neither is sufficient.
3. Add the concise comparison and any exact operator approval question to
   `agents/data.md`. Update `HANDOFF.md` and `DECISIONS.md` only with durable
   facts and replace this file with the next single objective before ending.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Record intraday archive validation stop`
