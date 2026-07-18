# Next Codex Goal

## Objective

Determine whether the fixed-ETF Norgate raw-D1 history boundary observed at
2024-07-18 is caused by the bounded query shape or by the locally installed
trial data coverage.

This is a small Data Agent capability audit. It may clarify an exact operator
NDU action if local coverage is missing, but it must not change settings,
download data, retain new raw data, choose a source, or open research/GPU work.

## Ownership

- **Data Agent:** owns the bounded host-only probe, local coverage metadata,
  and exact operator request if configuration is needed.
- **Review/Claude:** is optional unless the result would be used for a
  survivorship, temporal-availability, or data-promotion claim.
- **Engine Research Agent:** remains an observer and cannot consume the result.

## Boundaries

- Use only the existing Windows-host Norgate trial, fixed `SPY`/`QQQ`/`IWM`,
  D1, query-local `StockPriceAdjustmentType.NONE`, `PaddingType.NONE`, and
  `numpy-recarray`. Do not use Docker, KIS, `.env`, credentials, or secrets.
- Use at most three predeclared non-overlapping date windows that distinguish
  before-boundary, boundary, and current coverage. Record only per-symbol row
  counts, minimum/maximum returned dates, response fields, package version,
  and errors; never raw OHLCV values or rows.
- Do not change NDU settings, invoke an updater, create exports/snapshots,
  persist a cache/artifact, or retry with different settings. Do not infer why
  coverage is absent merely from an empty/short response.
- Inspect only non-secret local metadata or official local-package help needed
  to identify an operator configuration step. Do not inspect `.env`, account,
  browser, or unrelated user files.
- Do not create a provider, catalog, campaign, strategy, model, GPU job,
  paper order, report family, dashboard, or public service.

## Required Work

1. Check the prior alignment evidence and choose the three date windows before
   calling the local client. State the falsification condition: shorter or empty
   historical responses do not prove the reason for the coverage limit.
2. Run the maximum nine bounded host-only calls once, in deterministic
   symbol/window order. Keep the results in process and print only aggregate
   metadata permitted above.
3. Inspect local Norgate updater/package documentation or non-secret metadata
   only if necessary. If an operator action is needed, report exact UI steps,
   expected download size, data-history benefit, and why no automatic change was
   made. If no action is discoverable, close the audit as `unsupported`.
4. Refresh `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`, replace this
   goal, then continue while no real operator approval boundary remains.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the windows, aggregate response metadata, result, any exact operator
action needed, and no raw data.

## Suggested Commit Message

`Add Norgate raw-D1 alignment snapshot`
