# Next Codex Goal

## Objective

Classify whether the observed local `SMCI` `Close`/`Unadjusted Close` ratio
transition has a magnitude consistent with the issuer's 10-for-1 split under
the current documented Norgate price-setting behavior, without changing a local
Norgate setting.

This advances data collection and backtest-validation readiness by resolving or
closing one field-meaning question before any provider or research use. It is
not a provider implementation, purchase decision, data export, campaign,
model, paper-trading, or live step.

## Ownership

- **Data Agent:** owns package/API metadata inspection, one no-side-effect
  local derivation, and non-raw evidence wording.
- **Review/Claude:** challenge any conclusion about field meaning or split
  interpretation. Claude is advisory; send no credentials or raw rows.

## Boundaries

- Use only the existing operator-created Norgate trial at
  `D:\market_data\us_equities\norgate_us_platinum_trial`, the existing
  `SMCI` window, and public no-auth vendor/issuer documentation.
- Do not read `.env`, credentials, or KIS data. Do not buy, renew, upgrade,
  export, redistribute, or delete Norgate data. Preserve the retained C: copy.
- Do not change Norgate global or user settings. If an API setting is not
  demonstrably query-local and side-effect-free, inspect it only and do not use
  it.
- Do not add a provider, cache, dependency, `CatalogedBars` path, Docker query
  bridge, manifest, raw-data artifact, campaign, model, GPU job, paper order,
  or live behavior.
- Do not infer a general split-adjustment rule, event availability, point-in-
  time correctness, event type/ratio coverage, universe correctness, or
  research eligibility from this one fixture.
- Keep `THERICHER_MODE=off`; all broker submission, modification, cancel, and
  capital allocation remain disabled.

## Required Work

1. Inspect the local `norgatedata` query signature/docstring and public vendor
   documentation for the current price-adjustment setting behavior. Record only
   non-secret field and setting names plus whether any setting is clearly
   query-local; do not alter a setting.
2. Reuse the exact `SMCI` `2024-09-27` through `2024-10-02` price window under
   the existing no-side-effect behavior. Record only bounds, row count, and a
   derived ratio-change category: tenfold, one-tenth, unchanged, other, or
   indeterminable. Do not print or retain raw price values or rows.
3. Compare that category with the issuer's documented 10-for-1 split. If the
   available setting/field facts do not establish that the ratio isolates the
   split for this fixture, record `unsupported`; do not infer or normalize a
   general adjustment convention.
4. Ask Claude for a concise falsification verdict before recording any positive
   field-meaning conclusion. A missing, ambiguous, or non-query-local setting
   is a valid stop condition for this branch, not a reason to mutate settings
   or expand queries.
5. Update `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md` only with durable
   facts, then replace this goal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the focused local metadata/derivation probe and official source used.

## Suggested Commit Message

`Classify Norgate split ratio semantics`
