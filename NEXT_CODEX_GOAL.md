# Next Codex Goal

## Objective

Test the observed date relationship between the Norgate `Capital Event` marker
and its daily `Close`/`Unadjusted Close` ratio transition for the existing
`SMCI` split fixture.

This advances data collection and backtest-validation readiness by trying to
falsify a leakage-prone interpretation before any provider or research use. It
is not a provider implementation, purchase decision, data export, campaign,
model, paper-trading, or live step.

## Ownership

- **Data Agent:** owns one tight local query pair, explicit date clipping, and
  non-raw derived timing evidence.
- **Review/Claude:** challenge any conclusion that narrows event availability
  or the interpretation of derived price-ratio timing. Claude is advisory; send
  no credentials or raw rows.

## Boundaries

- Use only the existing operator-created Norgate trial at
  `D:\market_data\us_equities\norgate_us_platinum_trial` and the existing
  official SMCI filing facts.
- Do not read `.env`, credentials, or KIS data. Do not buy, renew, upgrade,
  export, redistribute, or delete Norgate data. Preserve the retained C: copy.
- Do not add a provider, cache, dependency, `CatalogedBars` path, Docker query
  bridge, manifest, raw-data artifact, campaign, model, GPU job, paper order,
  or live behavior.
- Do not infer event availability, ex-date semantics, event type/ratio
  meaning or coverage, complete PIT history, universe correctness, or research
  eligibility from this one fixture.
- Keep `THERICHER_MODE=off`; all broker submission, modification, cancel, and
  capital allocation remain disabled.

## Required Work

1. Query `SMCI` daily price data and `Capital Event` over one tight window
   spanning `2024-09-27` through `2024-10-02`. Explicitly clip the event result
   in memory before comparison, even if it again returns the wider trial range.
2. Record only requested and returned bounds, row counts, event-marker dates,
   and whether the derived `Close`/`Unadjusted Close` ratio changes on
   `2024-09-30`, `2024-10-01`, another date, or not deterministically. Do not
   print or retain raw market-data rows or price values.
3. Compare that timing with the issuer's documented after-close effective time
   on `2024-09-30` and split-adjusted trading on `2024-10-01`. Treat a marker
   on `2024-09-30` as unavailable for same-session use unless a separate
   source-timestamp contract proves otherwise.
4. Ask Claude for a concise falsification verdict before recording a positive
   timing conclusion. A mismatch, ambiguous ratio transition, duplicate dates,
   or unproven source availability is `unsupported`; do not repair, shift, or
   reinterpret source data.
5. Update `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md` only with durable
   facts, then replace this goal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the focused local probe and official filing source used.

## Suggested Commit Message

`Test Norgate capital-event timing`
