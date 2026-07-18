# Next Codex Goal

## Objective

Build one bounded, offline raw-D1 source-alignment diagnostic for `SPY`, `QQQ`,
and `IWM` using the existing fixed ETF evidence and the new full-history Tiingo
standard-EOD snapshot.

This advances feature/model research by measuring retrospective source agreement
before any new model work. It is not an independence test, a model-selection
input, a campaign, a paper-trading result, or a profitability claim.

## Required First Reads

Run `./scripts/start_next_codex_task.ps1`, then read `HANDOFF.md`, `VISION.md`,
`ARCHITECTURE.md`, `AGENTS.md`, `DECISIONS.md`, `RUNBOOK.md`, `agents/README.md`,
and the Data and Engine Research stateboards. Ask Claude for a short
source-alignment overreach check before changing a cross-source contract, then
invoke the Review checkpoint.

## Boundaries

- Read only existing external market-data evidence. Do not read `.env`, call a
  network API, download data, call KIS, submit or simulate orders, or access
  credentials.
- Do not train, use GPU, create candidates, run a campaign, produce local-paper
  fills, rank a model, open a holdout, or make a profitability claim.
- Re-attest every input through its owning Data loader. Do not expose raw bars
  or turn the Tiingo snapshot into `CatalogedBars`.
- Keep the comparison bounded to the exact `SPY`/`QQQ`/`IWM` overlap. Preserve
  all existing snapshots and write no new external artifact unless a single
  small deterministic summary is necessary for recovery.

## Required Work

1. Inventory and re-attest the fixed raw-D1 evidence and full-history Tiingo
   snapshot without reading raw files through an unverified path.
2. Add the smallest Data-owned, in-memory alignment result needed to measure
   common-session coverage and raw OHLCV agreement/differences by symbol. Keep
   adjusted fields and corporate-action inference out of the comparison.
3. Add focused tests proving the diagnostic is offline, credential-free,
   rejects tampered input, remains outside campaign/paper paths, and does not
   call model or broker code.
4. Run one actual external-data smoke and record only concise descriptive facts:
   coverage, agreement/difference counts, and limits. State that matching data
   does not prove independence, PIT validity, execution quality, or profit.
5. Update the Data and Engine stateboards, `HANDOFF.md`, and this next goal.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose --env-file .env.example config --quiet`.

## Suggested Commit Message

`Add raw daily source alignment diagnostic`
