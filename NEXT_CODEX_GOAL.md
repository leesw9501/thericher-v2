# Next Codex Goal

## Objective

Build a narrow Windows-host-only Norgate raw-daily provider adapter behind the
existing market-data interface, using the official query-level `NONE` adjustment
setting without modifying a local Norgate configuration.

This advances data collection toward a reproducible development-data path and
the future eligibility-driven GPU research batch. It is not a data export,
Docker bridge, campaign, training run, model selection, paper-trading, or live
step.

## Ownership

- **Data Agent:** owns the adapter, source-boundary tests, one nonpersistent
  host smoke, and source limitations.
- **Review/Claude:** give a short architecture drift-check before implementation
  and independently review the boundary before integration. Do not send raw
  rows, credentials, or trial data.
- **Infra capability:** confirm only that the adapter is host-Windows-only; it
  must not create a Docker/Norgate bridge.

## Boundaries

- Use only the existing operator-created Norgate trial at
  `D:\market_data\us_equities\norgate_us_platinum_trial` through its official
  Windows Python package. Do not read `.env`, credentials, or KIS data.
- Use a query-local `StockPriceAdjustmentType.NONE` setting only. Do not write
  or mutate an NDU/global/user configuration.
- Keep raw Norgate data in process only: no cache, export, artifact, manifest,
  Git data, derived dataset, or Docker mount/query path.
- Lazy-load the optional Norgate package and fail closed on a non-Windows host
  or unavailable package. Tests must use injected fakes, not actual trial data.
- Do not create `CatalogedBars`, a campaign, GPU job, model, paper order,
  execution path, or public service. Do not claim point-in-time correctness,
  event semantics, research eligibility, or provider rights beyond this adapter.
- Preserve the retained C: copy and keep `THERICHER_MODE=off`.

## Required Work

1. Ask Claude for a concise architecture drift-check before editing. State the
   existing provider interface, lazy optional dependency, host-only boundary,
   query-local `NONE` setting, no-persistence rule, and no campaign use.
2. Implement the smallest adapter following existing provider patterns. It must
   request only the caller's bounded symbol/date window, map raw daily OHLCV
   into existing `Bar` contracts, validate ordinary bar invariants, and avoid
   changing any Norgate setting.
3. Add focused mock-based tests proving no network, credentials, setting mutation,
   Docker use, raw-data persistence, or package import at module import time is
   required. Cover unavailable/non-Windows failure and bounded raw-bar mapping.
4. Run one host-only nonpersistent smoke query against the existing trial.
   Report only symbol, requested/returned bounds, count, fields, and validation
   outcome; do not print or save raw rows or price values.
5. Update `agents/data.md`, `HANDOFF.md`, and `DECISIONS.md` with only durable
   boundary facts, then replace this goal.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose --env-file .env.example config --quiet
```

Report the focused host smoke and Claude verdict.

## Suggested Commit Message

`Add host-only Norgate daily provider`
