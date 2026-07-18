# Next Codex Goal

## Objective

Build one bounded, immutable full-history Tiingo standard-EOD evidence snapshot
for `SPY`, `QQQ`, and `IWM` outside Git.

This advances data collection for future feature/model research. It must not
train a model or turn the snapshot into campaign, paper-trading, ranking,
promotion, or profitability evidence.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Ask Claude for a short
provenance/overreach falsification check before changing the external data
contract, then invoke the Review checkpoint.

## Approved Authority And Boundaries

- Read only `TIINGO_API_TOKEN` from the ignored root `.env`; never print, log,
  store, commit, or send it to Claude. Do not read any other `.env` key.
- Use only Tiingo's already approved no-cost standard daily endpoints for
  `SPY`, `QQQ`, and `IWM`. Do not purchase, upgrade, use a login-gated source,
  call KIS, submit an order, or access live credentials.
- Keep `THERICHER_MODE=off`. Do not train, use GPU, create candidates,
  campaigns, paper/local orders, a dashboard, or a profitability claim.
- Store raw responses, normalized data, manifests, and any Data artifact only
  under `D:\market_data` or `D:\thericher-v2\model-artifacts`; never Git.
  Warn below 20% free `D:` space and stop before the 15% floor.
- Preserve the existing short Tiingo and Yahoo snapshots unchanged. A new
  snapshot must have a new disjoint identifier and must not silently replace an
  existing source.

## Required Work

1. Inventory the existing Tiingo snapshots and estimate the bounded download
   before any request. Stop and report rather than retrying when standard access,
   rights, quota, or free-space checks fail.
2. If the standard API provides the history, acquire exactly one new immutable
   `SPY`/`QQQ`/`IWM` raw-EOD plus corporate-action snapshot with raw response
   hashes, normalized-data hash, source/as-of metadata, exact symbol/date
   coverage, and explicit `divCash`/`splitFactor` semantics. No secret-like
   value may enter a response-derived artifact.
3. Add or extend only the narrow offline Data loader and focused tests needed to
   re-attest the new snapshot. Keep it separate from the Yahoo wrapper and all
   campaign `CatalogedBars` paths.
4. State precisely what the new history does and does not establish. It may
   improve retrospective development evidence; it does not establish point in
   time universe membership, independence, ranking, sealed holdout validity, or
   profitability.
5. Update Data and Engine Research stateboards, `HANDOFF.md`, and this next
   goal before ending the task.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add full-history Tiingo EOD evidence`
