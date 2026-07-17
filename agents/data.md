# Data Agent

## Status

Active, no running job. The bounded training-readiness catalog is complete and
improves the **data collection** loop without creating a new research gate.

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

For the refreshed objective, inspect only the newest useful daily snapshot for
the predeclared `SPY`, `QQQ`, and `IWM` instruments. Define one adjustment and
ordering policy, then publish a hash-bound external subset only if it can
honestly support development training.

## Ready Queue

1. Answer a specific catalog question from Engine Research without rescanning
   unchanged files.
2. Continue the official symbol-directory prospective series with a new dated
   immutable snapshot when a future active goal requests capture; never
   overwrite or treat it as historical PIT evidence.
3. Identify a specific free, no-auth, license-compatible coverage gap only when
   existing local data cannot serve the active objective and free space remains
   above the hard floor.
4. Keep the ADP `2026-06-09T14:05:00Z` strict early-label bar as conditional
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
- The 2026-07-18 catalog fully inspected the three named intraday files and the
  newest daily snapshot. Intraday row counts are 572,894, 7,103, and 8,276;
  `snapshot=2026-06-23` daily contains 7,390,436 rows. Five daily snapshots
  were shallow-inventoried and SHA-256 hashed.
- The r2 integration catalog has stable ID
  `sha256:63f761b45b7b080ca9dcabde0f2d27ddb6464d6ec5f6234b977baf08ca8d95bb`.
  Each inspected entry exposes a stable Data-owned `dataset_id`, prefixed
  `dataset_hash`, UTC construction timestamp, and Research-compatible ranking
  and sealed-holdout eligibility facts.
- Data exports immutable `CatalogedBars` and an offline Yahoo canonical 1-minute
  loader that verifies the catalog's SHA-256 against the actual gzip bytes
  before parsing one homogeneous symbol stream. Direct construction is closed;
  only the verified loader creates this campaign evidence. It uses no Research
  imports, network, or credentials.
- No inspected file is model-selection training eligible or sealed-holdout
  eligible. Intraday coverage is under the 20-session catalog floor and its
  point-in-time universe provenance is unproven. Daily point-in-time universe,
  delisting, corporate-action, and full-OHLC adjustment provenance is unproven.
- During the r2 catalog run, `D:` had 40.61% free space and no data, network, or
  credential access occurred.
- The first official Nasdaq Trader symbol-directory snapshot was captured at
  `D:\market_data\us_equities\official_symbol_directory\raw\snapshot=2026-07-18`.
  It contains unaltered `nasdaqlisted.txt`, `otherlisted.txt`, and
  `TradingSystemAddsDeletes.txt` plus one manifest. It is private,
  non-commercial, prospective-only evidence and does not repair historical
  universe membership, survivorship, or delisting history.
- SEC files were not requested: compliant automation would require an honest
  identifying User-Agent/contact, and no operator identity was supplied or
  invented.
- Warning-only checks have found incomplete resample buckets; the known ABNB
  first-240-bar window has one missing 1-minute interval. Do not treat either
  as an execution hard stop.

## Recovery

- Recovery state is `complete`: reuse the r2 catalog artifact before
  inspecting unchanged files. Start new work only from a precise active-goal
  coverage or provenance requirement.
- Stop acquisition on credential/payment/manual access, unclear rights, two
  consecutive automated failures for one source, loss of active-goal benefit,
  or projected breach of the 15% free-space floor.
- Record a genuine unresolved requirement in `Operator Help`; retain detailed
  historical lineage in Git commit `8f416f8` and external artifacts.

## Recent Evidence

- `D:\market_data\us_equities\official_symbol_directory\raw\snapshot=2026-07-18\manifest.json`:
  first immutable official-source prospective universe snapshot; all three
  recorded hashes reverified, with Nasdaq file-creation timestamps from
  `2026-07-17 14:01` through `14:03` as stated in the source files.
- `D:\thericher-v2\model-artifacts\data-agent\training-readiness-catalog\data-agent-training-readiness-20260718-r2\catalog.json`:
  canonical Research-integration artifact with deterministic catalog and
  dataset identities; zero ranking or sealed-holdout eligible files.
- `D:\thericher-v2\model-artifacts\data-agent\training-readiness-catalog\data-agent-training-readiness-20260718-r1\catalog.json`:
  preserved pre-integration field shape; superseded by r2 for new consumers.
- `data-agent-market-data-inventory-cadence-20260717-r2`: bounded metadata
  inventory confirmed 2 roots, 5 snapshots, and 5 useful files; no acquisition.
- `data-agent-post-mpwr-lane-rotation-inventory-20260717-r1`: no immediate
  data-lane follow-up or operator request; the post-MPWR evidence question was
  already answered by existing artifacts.

## Next Handoff

Hand Engine Research one fixed-instrument daily manifest with explicit parser,
development-training, ranking, and sealed-holdout eligibility. Do not broaden
the inventory or substitute symbols based on observed performance.
