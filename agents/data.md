# Data Agent

## Status

Active, no running job. The current Data task improves the **data collection**
loop by making existing local coverage training-ready without creating a new
research gate.

## Engine Loop

- Data collection.
- Backtest and walk-forward validation support.

## Owns

- Provider interfaces, local caches, calendars, symbol metadata, resampling,
  and warning-only data-quality summaries.
- Inventory and license-compatible reuse/acquisition of market data.

## Must Not

- Call KIS, read credentials or `.env`, or modify broker/strategy code.
- Use paid, login-gated, manual, or license-unclear sources without operator
  approval.
- Turn research data-quality warnings into blocking gates unless execution
  requires a hard stop.

## Resources

- Market-data root: `D:\market_data`; known roots: `pit_sources` and
  `us_equities`.
- External Data artifacts: `D:\thericher-v2\model-artifacts\data-agent`.
- Storage policy: maintain at least 15% free space; warn at 20%; do not acquire
  or expand local data when doing so would breach the 15% hard floor.
- Autonomous acquisition is allowed only when it is useful to the active goal,
  no-auth, no-cost, and license-compatible. Payment, login, manual access, or
  unclear rights require operator approval.

## Current Objective

Produce a training-ready catalog and useful free-data coverage from existing
local data. Current intraday evidence is smoke-ready, not model-selection-ready:
catalog symbol/date splits, label availability, leakage checks, holdout rules,
and quality summaries before it is treated as model-selection evidence.

## Ready Queue

1. Build or refresh the bounded catalog from known local roots when an active
   Engine Research objective needs exact symbols, date ranges, or holdout
   eligibility.
2. Identify a specific free, no-auth, license-compatible coverage gap only when
   existing local data cannot serve the active objective and free space remains
   above the hard floor.
3. Keep the ADP `2026-06-09T14:05:00Z` strict early-label bar as conditional
   context only; reopen it only for a goal that explicitly rescues that row.

## Running

- None.

## Operator Help Needed

- None now.

## Durable Knowledge

- Known inventory: 2 top-level roots, 5 snapshots, and 5 useful files under
  `D:\market_data` in the 2026-07-17 bounded inventories.
- Intraday: Yahoo 1-minute canonical data at
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
  `snapshot=2026-06-18\ohlcv_1m.csv.gz` contains 572,894 rows, 250 symbols,
  and spans `2026-06-09T13:30:00Z` through `2026-06-16T19:59:00Z`.
- Intraday: `snapshot=2026-07-09-shadow-t0-8d-probe` contains CVS, FCX, and KO
  from 2026-06-29 through 2026-07-09. It is suitable for bounded smoke work.
- Daily/PIT: `D:\market_data\pit_sources` is a known root, but no exact
  daily-file count, symbols, dates, or license coverage is currently verified;
  catalog it before relying on it.
- Warning-only checks have found incomplete resample buckets; the known ABNB
  first-240-bar window has one missing 1-minute interval. Do not treat either
  as an execution hard stop.

## Recovery

- Start from the active objective, inspect only the exact local coverage it
  needs, and reuse the catalog/artifacts before scanning broadly.
- Stop acquisition on credential/payment/manual access, unclear rights, two
  consecutive automated failures for one source, loss of active-goal benefit,
  or projected breach of the 15% free-space floor.
- Record a genuine unresolved requirement in `Operator Help`; retain detailed
  historical lineage in Git commit `8f416f8` and external artifacts.

## Recent Evidence

- `data-agent-market-data-inventory-cadence-20260717-r2`: bounded metadata
  inventory confirmed 2 roots, 5 snapshots, and 5 useful files; no acquisition.
- `data-agent-post-mpwr-lane-rotation-inventory-20260717-r1`: no immediate
  data-lane follow-up or operator request; the post-MPWR evidence question was
  already answered by existing artifacts.

## Next Handoff

Keep the next Data step scoped to the training-ready catalog or an exact
coverage gap named by the active goal. Fresh-symbol, MPWR, AMAT bridge, and
non-AMAT context remain passive unless that goal names the required symbols and
date ranges.
