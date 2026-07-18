# Next Codex Goal

## Objective

Build one bounded, host-only raw-D1 cross-source alignment snapshot for the
fixed `SPY`/`QQQ`/`IWM` ETF set, using Norgate's query-local unadjusted daily
fields and the existing external Tiingo raw-D1 source only as a comparison.

The outcome is a data-source evidence result. It may establish or deny narrow
raw-field alignment, but it must not declare a research dataset eligible or
start CPU/GPU model work.

## Ownership

- **Data Agent:** owns the minimal host-only extractor, snapshot lineage,
  comparison, storage, and source limitations.
- **Review/Claude:** challenges field adjustment, date boundaries, comparison
  semantics, survivorship, and any eligibility claim before reliance.
- **Engine Research Agent:** observes only. It must not consume this snapshot,
  schedule a campaign, or launch a GPU job.

## Boundaries

- Use only the existing Norgate trial on the Windows host, the fixed three
  ETFs, D1, `StockPriceAdjustmentType.NONE`, `PaddingType.NONE`, explicit
  `numpy-recarray`, and one bounded date window. Do not use Docker, KIS,
  `.env`, credentials, or secret-like files.
- Store Norgate-origin output, manifest, hashes, comparison summary, and EULA
  deletion marker only under `D:\market_data`; never Git, C:, Docker, or
  `D:\thericher-v2\model-artifacts`. Preserve the retained C: NDU copy.
- Confirm D: is at or above the 20% warning level before acquisition and stop
  below the 15% hard floor. Do not extract a wider universe or retry by silently
  shortening dates, dropping symbols, or changing adjustments.
- Keep the Norgate snapshot distinct from the membership matrix and from the
  Tiingo snapshot. Do not create a provider, `CatalogedBars` loader, campaign,
  strategy, model, GPU queue, paper order, report family, dashboard, or public
  service.
- Compare only literal raw-D1 fields and explicit common sessions. Do not
  normalize, rescale, choose a preferred source, or infer corporate-action,
  timestamp, publication-time, PIT, delisting, or model-training eligibility.
- Do not print or place raw bars, prices, volumes, symbols beyond the fixed
  public ETF names, tokens, account data, or row-level data in Git artifacts.

## Required Work

1. Ask Claude for a concise falsification-first drift-check before editing or
   acquisition. State the raw-field contract, fixed date window, adjustment and
   padding settings, exact comparison scope, stop rules, and the fact that
   source alignment cannot itself create eligibility.
2. Implement the smallest mock-tested host-only extractor and comparison helper.
   It must validate every response, use deterministic ordering, stage externally
   until all three symbols validate, and leave no partial published snapshot on
   a source or comparison failure.
3. Read the already cataloged Tiingo raw-D1 data through its existing approved
   local boundary. Compare only session presence and literal field equality or
   inequality counts for the fixed common window; record counts and hashes, not
   raw values or a winner.
4. Run once only after tests and fresh D: preflight pass. Report only external
   path, date window, symbol count, session/count summaries, comparison counts,
   hashes, package version, disk state, and validation outcome.
5. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue only if no true operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the Claude verdict, focused tests, external snapshot summary, and any
genuine operator data help required.

## Suggested Commit Message

`Add Norgate membership matrix snapshot`
