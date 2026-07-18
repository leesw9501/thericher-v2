# Data Agent

## Status

Ready, no running job. The operator approved standard Tiingo EOD acquisition
for the three fixed instruments; the offline corporate-action snapshot contract
is implemented and awaits immutable source bytes.

## Engine Loop

- Data collection.
- Backtest and walk-forward validation support.

## Owns

- Provider interfaces, local caches, calendars, symbol metadata, resampling,
  and warning-only data-quality summaries.
- Inventory and license-compatible reuse/acquisition of market data.

## Must Not

- Call KIS, read any `.env` value except `TIINGO_API_TOKEN`, or modify
  broker/strategy code. Never expose or persist the token.
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

Capture standard Tiingo EOD records for `SPY`, `QQQ`, and `IWM` in one
immutable, hash-bound external snapshot without modifying r2. Derive only
`cash_distribution` from `divCash` and `split` from `splitFactor`.

## Ready Queue

1. Capture exact EOD response bytes for the fixed campaign range under
   `D:\market_data` using only the approved Tiingo token.
2. Normalize SPY/QQQ/IWM distributions and splits with request provenance.
3. Load the snapshot through the offline contract and independently verify the
   exact fixed 896-session coverage before Research consumes it.

## Running

- None.

## Operator Help Needed

- None. Standard EOD token use is approved; paid upgrades remain prohibited.

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
- No file in the r2 training-readiness catalog is model-selection training or
  sealed-holdout eligible. Intraday coverage is under the 20-session catalog
  floor and its point-in-time universe provenance is unproven.
- The fixed ETF daily r1 subset has dataset ID
  `us_equities.fixed_etf_daily.1d.snapshot=2026-07-18-r1` and hash
  `sha256:7f161319d01cfedf762d738fea98ebb9800ce3acd61ee48af7e550e85fc2fbf6`.
  It contains 21,823 ordered rows: SPY 8,405 (`1993-01-29` to `2026-06-22`),
  QQQ 6,863 (`1999-03-10` to `2026-06-22`), and IWM 6,555 (`2000-05-26` to
  `2026-06-22`). Parser and development-training eligibility are true;
  ranking and sealed-holdout eligibility are false because construction is
  post-period and historical PIT/independence evidence is unproven. Its bytes
  remain immutable, but it is superseded by r2 for campaign use because its
  canonical prices are adjusted rather than executable raw prices.
- The fixed ETF daily r2 subset has dataset ID
  `us_equities.fixed_etf_daily.1d.snapshot=2026-07-18-r2` and hash
  `sha256:3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e`.
  It preserves the same 21,823 rows and date ranges while canonical OHLC and
  volume are raw. Parser and development-training eligibility are true;
  ranking and sealed-holdout eligibility remain false.
- Daily adjustment policy
  `yahoo_adj_close_price_factor_raw_volume_v1` uses
  `factor = raw_adj_close / raw_close`, multiplies raw OHLC by that factor, and
  leaves raw volume unchanged. Yahoo's factor can combine dividend and split
  effects; this is not a split-only volume adjustment and adjusted prices are
  not executable historical fills.
- R2 factor-change diagnostics use
  `abs(current_factor / previous_factor - 1) >= 0.0001` on adjacent observed
  sessions and flag the current date. Counts are SPY 135, QQQ 89, and IWM 106.
  Exclude any campaign lookback, signal, entry, exit, feature, label, fill,
  threshold, or metric sample touching a flagged date. These flags are not
  authoritative corporate-action or dividend lineage.
- The bounded source review found no existing local corporate-action history.
  Official issuer pages support distribution ex-date semantics but did not
  establish both automated preservation rights and complete split/no-split
  coverage for all three ETFs. Absence of a split row cannot prove no split.
- The operator's standard EOD probe succeeded for SPY from `2024-03-14` through
  `2024-03-18`; `2024-03-15` returned `divCash=1.594937` and
  `splitFactor=1.0`. This is access evidence, not a durable campaign snapshot.
- The corporate-action loader is offline and fail-closed. It requires immutable
  raw and normalized hashes, exact r2 lineage, source/rights/as-of facts,
  explicit per-symbol/event-type coverage, New York session-date semantics,
  and loader-only attestation. It rejects Git paths, symlinks, tampering,
  ambiguous dates, conflicts, incomplete coverage, and forged objects.
- The strictly local daily loader treats the r2 gzip byte hash as authoritative,
  then requires the sibling UTF-8 r2 manifest to bind the caller dataset ID,
  dataset/subset hashes, mount-portable snapshot-directory/file path tail,
  parent r1, original source, and supersession lineage. It creates attested
  `CatalogedBars` only from raw canonical OHLCV; adjusted diagnostics cannot
  enter loader bars. The factor-change helper enforces the same lineage.
- During the fixed ETF daily r2 run, `D:` remained 40.61% free. R2 was derived
  only from verified r1 bytes; the 7,390,436-row original was not rescanned and
  no network, credentials, or GPU were used.
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

- Recovery state is `ready`: the loader contract and approved EOD source path
  are known, but there is no accepted event snapshot to recover. Use the fixed
  ETF daily r2 manifest for development campaigns and retain r1 as lineage.
- Recover or mount the r2 subset only together with its unchanged sibling
  `manifest.json`. A different Windows/POSIX root is allowed when the snapshot
  directory name and `ohlcv_1d.csv.gz` basename are preserved; missing,
  tampered, or trailing-identity-inconsistent evidence is rejected.
- Stop acquisition on credential/payment/manual access, unclear rights, two
  consecutive automated failures for one source, loss of active-goal benefit,
  or projected breach of the 15% free-space floor.
- Record a genuine unresolved requirement in `Operator Help`; retain detailed
  historical lineage in Git commit `8f416f8` and external artifacts.

## Recent Evidence

- `D:\market_data\us_equities\fixed_etf_daily\canonical\ohlcv_1d\snapshot=2026-07-18-r2\manifest.json`:
  raw canonical campaign subset with r2 hash
  `sha256:3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e`;
  records parent r1 and original-source hashes plus all factor-change dates.
- `D:\market_data\us_equities\fixed_etf_daily\canonical\ohlcv_1d\snapshot=2026-07-18-r1\manifest.json`:
  preserved immutable lineage, superseded for campaign use; source hash
  `sha256:1690a766a820b3e6385c76605c7e02548ab0e428148c93f85388c7a6a8b065b4`,
  subset hash
  `sha256:7f161319d01cfedf762d738fea98ebb9800ce3acd61ee48af7e550e85fc2fbf6`.
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

After operator authorization, supply Engine Research with loader-attested event
dates, event types, coverage, and provenance for a no-retraining sensitivity
replay. Research must keep r2 raw fills unchanged and may not use the event
snapshot to claim ranking, sealed-holdout independence, model selection, or
profitability.
