# Next Codex Goal

## Objective

Run one bounded Norgate trial semantics check using public, independently
verifiable fixtures inside the observed trial horizon.

This advances data collection and backtest-validation readiness by testing the
meaning of two local point-in-time signals. It is not a provider implementation,
purchase decision, data export, campaign, model, paper-trading, or live step.

## Ownership

- **Data Agent:** owns fixture selection, bounded local queries, date handling,
  and evidence wording.
- **Infra capability:** confirms only the existing host/Docker read-only mount
  when needed. It must not implement a bridge.
- **Review/Claude:** use a short falsification check before relying on a
  positive fixture conclusion. Claude is advisory; no credential or raw rows.

## Boundaries

- Use only the existing operator-created Norgate trial at
  `D:\market_data\us_equities\norgate_us_platinum_trial` and public,
  no-auth official sources for fixture facts.
- Do not read `.env`, credentials, or KIS data. Do not buy, renew, upgrade,
  export, redistribute, or delete Norgate data. Preserve the retained C: copy.
- Do not add a provider, cache, dependency, `CatalogedBars` path, Docker query
  bridge, manifest, raw-data artifact, campaign, model, GPU job, paper order,
  or live behavior.
- Do not infer a complete PIT universe, delisting coverage, event lineage,
  source correctness, or long-history eligibility from these two fixtures.
- Keep `THERICHER_MODE=off`; all broker submission, modification, cancel, and
  capital allocation remain disabled.

## Required Work

1. Select two independently documented fixtures within the local trial range:
   one historical index-membership change and one capital event. Prefer original
   official index/issuer notices; if neither can be established without an
   ambiguous source, record that limitation and do not substitute a weaker claim.
2. Query the local Windows Norgate package over tight before/after windows.
   Record only symbol, requested and returned date bounds, field name, counts,
   indicator transitions, and non-secret query behavior. Do not retain or print
   raw market-data rows.
3. For the capital-event query, independently apply an in-memory date clip and
   demonstrate whether the returned series requires that clip. Do not implement
   reusable provider code from the result.
4. Compare observed indicator timing with the public fixture date. A mismatch,
   missing transition, unclear effective-date convention, or ambiguous event
   type is a valid `unsupported` result, not a reason to adjust data or retry
   unboundedly.
5. Request a concise Claude falsification verdict before recording any positive
   semantic finding. Update `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md`
   only with durable facts, then replace this goal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report any focused local probe and official fixture source used.

## Suggested Commit Message

`Check Norgate fixture semantics`
