# Data Agent

## Status

Ready, no running job. The approved Tiingo standard EOD acquisition produced a
loader-attested retrospective corporate-action snapshot, immutable raw-D1
comparison snapshot, and strict offline raw-D1 `CatalogedBars` loader for the
three fixed instruments. The one permitted source-sensitivity replay completed
outside Git; the bounded no-auth source triage found no eligible new pilot.

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

The Tiingo raw-D1 comparison is complete. Its loader re-attests r2 and parent
Tiingo evidence before Research receives bars, and its completed replay used no
new request or credential read. It remains a separate-provider representation
bound to r2's exact session calendar, not independent validation or ranking
evidence.

## Ready Queue

1. Inventory the existing broad daily snapshot for a small, explicitly
   development-only US-equity universe candidate without acquiring data or
   implying point-in-time membership.
2. If future work needs historical point-in-time universe membership, prepare a
   concrete paid-data request for Sharadar or Norgate with product, cost,
   coverage, and rights; templates are not evidence.

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
- Daily/PIT: `D:\market_data\pit_sources` contains only template workspaces for
  `nasdaq_data_link_sharadar_sep_sfp` and `norgate_us_platinum_or_diamond`.
  Both raw directories are empty and neither has `membership.csv`; do not run
  the legacy intake/gate instructions in their README files or treat templates
  as source evidence.
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
- Tiingo standard EOD acquisition completed at `2026-07-18T07:38:24.283185Z`.
  The immutable private-use snapshot is
  `D:\market_data\us_equities\fixed_etf_corporate_actions\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-corporate-actions-r1`.
  It is loader-attested to r2's exact 896 observed sessions per symbol and has
  normalized dataset hash
  `sha256:3587beb050cabd9b3be0d68a66395b9a1a369010f2515fb22d7287d7b87d06f8`,
  manifest hash
  `sha256:89fdc4717f3b3a596a58afe1242ad1680f141a6abf92f4a92115b603df77ccf4`,
  and raw response hashes SPY
  `sha256:3d51ed9fb21d3e51734425fe1deebd284bdb181558152869bb4d2ffeb242a28d`,
  QQQ
  `sha256:8cb772bafa4cb7cbe90f3db916ba56c6198785e99854db2b16265ab2a0a16956`,
  and IWM
  `sha256:fb53eac5a06c8963e485e16bc30c46c05a69c43fdf2ee3904cf577afe6b0ddf0`.
  Derived evidence has 15 SPY cash distributions, 16 QQQ cash distributions,
  15 IWM cash distributions, and zero splits. It passed the seven-calendar-day
  post-campaign retrieval lag. This proves returned-session coverage, not that
  Tiingo can never later restate an event; a future immutable re-pull comparison
  is the falsifier.
- The derived raw-D1 comparison snapshot is
  `D:\market_data\us_equities\fixed_etf_daily\canonical\tiingo_raw_d1\snapshot=2026-07-18-tiingo-raw-d1-r1`.
  Its 2,688 rows are exactly 896 SPY, 896 QQQ, and 896 IWM sessions; dataset
  hash is `sha256:9056112167ab920335cb8a5f3c2f45d540a04e1132ee6eb231bac16ee11d7a3d`
  and manifest hash is
  `sha256:44a6316e9821694886fa3f791ddb19ec56a435dbaf765417a9568b4a3e57f421`.
  It has only raw OHLCV, `div_cash`, and `split_factor`, no copied raw response,
  and no adjusted output field. It is replay-only and cannot establish an
  independent validation, rank a model, open a holdout, or support a
  profitability claim.
- The completed source-sensitivity replay is at
  `D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-tiingo-source-sensitivity-20260718-r1\summary.json`
  with SHA-256
  `2e91c133fd12e0e28a7011eb0c1d3f661fe0fffab094ab00b679d3a566a14ff3`.
  Its loader pins the gzip dataset hash and compares the decompressed canonical
  CSV to attested Tiingo raw responses, so the Windows snapshot re-attests in
  Docker without accepting altered content.
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

- Recovery state is `complete`: do not overwrite either Tiingo snapshot. A
  later source comparison must create a new disjoint snapshot and retain these
  inputs as original evidence. Use the fixed ETF daily r2 manifest for
  development campaigns and retain r1 as lineage.
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
- `D:\market_data\us_equities\fixed_etf_corporate_actions\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-corporate-actions-r1\manifest.json`:
  exact raw per-symbol Tiingo EOD bytes bound to normalized evidence and r2
  lineage; replay-only, not ranking or sealed-holdout eligible.
- `D:\market_data\us_equities\fixed_etf_daily\canonical\tiingo_raw_d1\snapshot=2026-07-18-tiingo-raw-d1-r1\manifest.json`:
  raw OHLCV and explicit corporate-action fields derived from the exact Tiingo
  source bytes; replay-only, not independent validation or ranking evidence.
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

Data derived and rechecked the Tiingo raw-D1 snapshot outside Git without a
credential read, network request, or raw response copy. The completed replay
used its strict loader and produced no data acquisition request. Do not rewrite
either snapshot, interpret the replay as independent validation, or use
adjusted fields. The next useful data question is whether the existing broad
daily snapshot can support a narrowly labeled development-only universe; no
paid upgrade or operator data action is needed yet.
