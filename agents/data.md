# Data Agent

## Status

Ready, no running job. The approved Tiingo standard EOD acquisition produced a
loader-attested retrospective corporate-action snapshot, immutable raw-D1
comparison snapshot, strict offline raw-D1 `CatalogedBars` loader, and one
separate full-history evidence snapshot for the three fixed instruments. The
broad Yahoo daily snapshot now also has one
hash-bound, retrospective-only `SPY`/`QQQ`/`IWM` development-universe wrapper.
Its first consumer is a Data-re-attested, in-memory Engine feature materializer;
raw bars remain unavailable at the public wrapper boundary. The same bounded
module now derives future-only, next-observed-session outcomes after
re-attestation; it does not widen that raw-bar boundary.

The first Tiingo IEX 5-minute fixed-ETF snapshot is also complete and
offline-attested. It is a separate Data object, not a `CatalogedBars` provider
or a campaign/paper/model input. The provider silently returned its newest
10,000 bars per symbol rather than the requested 2017 start, so r1 preserves
only its actual 129 common-session window and that limitation remains explicit.
A nonpersistent SPY scope probe then returned a separate 10,000-bar 2024 window,
so date-window access is supported even though the observed per-response cap
remains unresolved as a provider contract.

The operator-completed Norgate US Stocks Platinum trial compatibility check is
also complete. It establishes only a local Windows/Python field-access boundary
and a D: database update path; it does not open a provider, campaign, model, or
paper-trading input.

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
- Norgate trial database: `D:\market_data\us_equities\norgate_us_platinum_trial`.
  The retained `C:\ProgramData\Norgate Data` copy is not to be deleted until a
  later, separately justified cleanup decision.
- External Data artifacts: `D:\thericher-v2\model-artifacts\data-agent`.
- Storage policy: maintain at least 15% free space; warn at 20%; do not acquire
  or expand local data when doing so would breach the 15% hard floor.
- Autonomous acquisition is allowed only when it is useful to the active goal,
  no-auth, no-cost, and license-compatible. Payment, login, manual access, or
  unclear rights require operator approval.

## Current Objective

The full-history Tiingo snapshot remains separate from the Yahoo wrapper and
all campaign `CatalogedBars` paths; its exact raw-D1 comparison is
`unsupported`. The CVS/FCX/KO intraday smoke is complete from a loader-attested
short snapshot. Tiingo IEX r1 remains 5-minute descriptive evidence only. The
pre-r1 archive attempt is closed after strict source validation failed twice;
there is no r2 snapshot or new historical-intraday research input.

The Norgate trial compatibility, first fixture, and timing checks are complete.
`PLTR` membership changed false-to-true on `2024-09-23`. For the local `SMCI`
fixture, the client-clipped `Capital Event` marker is `2024-09-30`, while the
derived `Close`/`Unadjusted Close` ratio transitions on `2024-10-01`. These are
date-scoped stored-field observations, not availability or field-semantic
claims. The next ready Data item may inspect current public adjustment-setting
documentation and classify this one ratio-change magnitude without mutating
local Norgate settings; it must not become a provider or research-data
integration.

## PIT Source Decision (2026-07-19)

**Recommendation: evaluate Norgate US Stocks Platinum through its free trial
before any purchase.** It is the only candidate in this comparison with a
current public price and published footprint that joins delisted securities,
historical index membership, major-exchange listing history, daily
price/volume, and corporate-action indicators in one local Windows product.
The 6-month subscription is USD 346.50; 12 months is USD 630.00. Platinum
includes history back to 1990, while its major-exchange listing identifier is
documented back to January 1995.

- **PIT universe and delistings:** Platinum includes delisted securities and
  historical index constituents. The historical-membership plugin answers
  whether a listed or delisted security was in an index on a day; it does not
  provide raw constituent-change lists. Major-exchange listing status is
  separately documented per trading date from 1995. This is useful daily PIT
  research evidence, not a claim of a complete all-US universe or pre-1995
  coverage.
- **Price and corporate actions:** Norgate exposes daily price/volume and a
  configurable no-price/volume-adjustment mode, plus dividend and capital-event
  indicators (splits, reverse splits, stock dividends, rights issues, and
  complex reorganizations). A trial must still prove the exact Windows-Python
  fields, raw OHLCV export, and event-lineage representation needed here.
- **Delivery:** NDU stores a proprietary local relational database and supports
  Python on Windows plus historical-price CSV/TXT export. It does not promise
  direct Linux/Docker access, so a trial must test a licensed host-to-Docker
  research boundary before any integration code is proposed.
- **Rights and retention:** the current EULA permits personal investment or
  trading use on two personal computers and a database backup, but prohibits
  redistribution and commercial use. On subscription lapse it requires deletion
  of Data and Derived Data. Norgate-originated data and affected artifacts must
  therefore stay out of Git and have a documented deletion path; this is a
  material constraint, not a paper-trading or live authority.
- **Storage:** Norgate publishes a 2 GB download and 9.1 GB on-disk estimate
  for US Platinum, with 500 MB free required on `C:` even when its database is
  located elsewhere. The current `D:` free space is 40.60 percent, so the
  published 9.1 GB footprint remains above the 20 percent warning and 15
  percent stop thresholds. `C:` has more than the required 500 MB free.

Official evidence: [packages](https://norgatedata.com/stockmarketpackages.php),
[content tables](https://norgatedata.com/data-content-tables.php),
[historical-membership FAQ](https://norgatedata.com/data-package-faq.php),
[delivery and adjustment](https://norgatedata.com/ndu-overview.php),
[installation and storage](https://norgatedata.com/ndu-installation.php), and
[EULA](https://norgatedata.com/subscribe/eula.php).

## Norgate Trial Compatibility (2026-07-19)

The operator-created US Stocks Platinum trial is installed at
`D:\market_data\us_equities\norgate_us_platinum_trial`. After the operator
selected that location and ran an update, it contained 429 files and 6.12 GiB;
its newest file time was later than the retained C: copy. This is evidence of a
successful D: update path, not proof that D: is the only active database or that
the C: copy can be deleted. D: remained 40.44 percent free.

Windows `norgatedata==1.0.77` bounded local queries exposed daily `Open`,
`High`, `Low`, `Close`, `Volume`, `Turnover`, `Unadjusted Close`, and `Dividend`
fields, plus `Index Constituent`, `Major Exchange Listed`, and `Capital Event`
series. Listing and membership honored the requested short range. In contrast,
`capital_event_timeseries` returned the wider trial horizon for a short-range
request, so its date-filter contract is unproven and any later consumer must
clip output explicitly before use. The observed trial horizon is about two
years.

A Docker `engine` runtime probe listed 166 top-level files in the named D:
directory through the existing `/app/market_data` mount, whose runtime options
were `ro`. That proves only a technical read-only mount boundary; it does not
establish that the proprietary database may be queried in Docker or that a
licensed export bridge is appropriate.

Claude's falsification-first review returned `supported-with-limits` for
Windows/Python compatibility only. Point-in-time universe correctness, source
correctness, event timestamps and lineage, long-history availability, Docker
rights, provider integration, research eligibility, and paper-trading use remain
unproven.

## Norgate Fixture Observations (2026-07-19)

The first bounded semantics check used original public sources and retained no
raw Norgate rows. A `PLTR` S&P 500 membership query requested and returned
`2024-09-18` through `2024-09-27` (eight rows); its `Index Constituent`
transition was false-to-true on `2024-09-23`, matching S&P DJI's
effective-before-open date. A `SMCI` capital-event query requested
`2024-09-26` through `2024-10-04` but returned `2024-07-18` through
`2026-07-17`; explicit in-memory clipping yielded seven rows and one
nonzero `Capital Event` date, `2024-09-30`. The issuer records the 10-for-1
split as effective after the close that day, with split-adjusted trading from
`2024-10-01`.

Claude returned `supported-with-limits`: the observations support only those
literal date matches. The membership fixture cannot separate before-open
effectiveness from first-trading-session convention. The capital-event marker
must not be interpreted as price-adjustment, ex-date, or usable same-session
availability. The next test must compare it with the local
`Close`/`Unadjusted Close` ratio transition before any broader statement.

Official fixtures: [S&P DJI notice](https://press.spglobal.com/2024-09-06-Palantir-Technologies%2C-Dell-Technologies%2C-and-Erie-Indemnity-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600),
[SMCI Form 8-K](https://www.sec.gov/Archives/edgar/data/1375365/000137536524000028/smci-20240806.htm),
and [SMCI Form 10-Q](https://www.sec.gov/Archives/edgar/data/1375365/000137536525000005/smci-20240930.htm).

## Norgate Capital-Event Timing (2026-07-19)

A second bounded `SMCI` query retained no raw rows or values. The requested
`2024-09-27` through `2024-10-02` daily price result had four ordered,
non-duplicate rows. Its derived `Close`/`Unadjusted Close` ratio changed only
on `2024-10-01`. The matching capital-event request returned 501 rows from
`2024-07-18` through `2026-07-17`; after explicit in-memory clipping it had
four rows and one `Capital Event` marker, on `2024-09-30`.

The issuer records the 10-for-1 split as effective after the close on
`2024-09-30` and split-adjusted trading from `2024-10-01`. Claude returned
`supported-with-limits` for the literal one-session ordering. It supports only
the conservative prohibition against treating this marker as a price-ratio date
or same-session actionable input without a source-timestamp contract. It does
not show a general provider lag, marker population time, event semantics, or
that `Close`/`Unadjusted Close` isolates split adjustment.

The remaining bounded question is whether the observed ratio-change magnitude
is consistent with this issuer's 10-for-1 split under the current documented
local adjustment setting. If documentation or a no-side-effect query cannot
establish that field meaning, record `unsupported` and end this semantics
branch rather than add a workaround.

**Sharadar comparison:** the official `SEP` product page documents daily US
listed and delisted equities from 1998, adjusted and unadjusted OHLCV, and
corporate-action, delisting-reason, and ticker-change fields. It also documents
two daily update times plus Tables API and bulk-export delivery. However, its
current price is login-gated, and the public material reviewed does not prove
historical index constituent membership or per-date major-exchange universe
membership, a storage footprint, or personal-use rights. Nasdaq's public
license refers to an executed order form and internal-business use. SEP can
therefore address raw daily price, corporate-action, and delisting evidence,
but is not a complete or decision-ready answer to this project's PIT-universe
requirement from the public evidence alone.

Official evidence: [Sharadar SEP](https://data.nasdaq.com/databases/SEP),
[Nasdaq Data Link product documentation](https://docs.data.nasdaq.com/docs/data-organization),
and [Nasdaq license terms](https://data.nasdaq.com/terms).

## Ready Queue

1. Inspect the existing `SMCI` ratio-change magnitude against current public
   adjustment-setting documentation without mutating local Norgate settings.
   Do not purchase, export, or integrate the trial database into a provider or
   `CatalogedBars` path.
2. Do not automatically retry the exhausted Tiingo IEX pre-r1 archive plan,
   relax its Bar invariants, repair/fill bad rows, or create a provider from r1.
3. If an operator later approves a source, collect only the specifically
   approved product under a new bounded goal; templates are not evidence.

## Running

- None.

## Operator Help Needed

- None. Do not delete the retained C: copy or purchase/renew Norgate from this
  compatibility result.

## Durable Knowledge

- Known inventory: 2 top-level roots, 5 snapshots, and 5 useful files under
  `D:\market_data` in the 2026-07-17 bounded inventories.
- Norgate US Stocks Platinum trial compatibility is `supported-with-limits`:
  D: held 429 files / 6.12 GiB after the operator location switch and update;
  Windows package `norgatedata==1.0.77` exposed daily OHLCV, Turnover,
  Unadjusted Close, Dividend, Index Constituent, Major Exchange Listed, and
  Capital Event access. Short listing/membership requests clipped correctly,
  but `capital_event_timeseries` returned the full trial horizon. No raw rows,
  export, reusable trial artifact, provider, campaign, or Docker query path was
  created. This does not prove PIT, event lineage, long-history, or research
  eligibility.
- Intraday: Yahoo 1-minute canonical data at
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
  `snapshot=2026-06-18\ohlcv_1m.csv.gz` contains 572,894 rows, 250 symbols,
  and spans `2026-06-09T13:30:00Z` through `2026-06-16T19:59:00Z`.
- The target ETF subset in that Yahoo 1-minute snapshot is exactly 2,340 rows
  each for SPY/QQQ/IWM: six complete regular sessions from 2026-06-09 through
  2026-06-16 with no in-session gaps. It is still unofficial short-window
  evidence, not historical model-quality evidence.
- Tiingo IEX r1 is
  `D:\market_data\us_equities\fixed_etf_intraday\canonical\tiingo_iex_5m\snapshot=2026-07-19-tiingo-iex-5m-r1`.
  Its dataset ID is
  `us_equities.fixed_etf_tiingo_iex_intraday.5m.snapshot=2026-07-19-tiingo-iex-5m-r1`,
  dataset hash is
  `sha256:1531d803fb259c5f2233cc1b5f94441eb52bab9f31938232644879cc4aa1fcb6`,
  and manifest hash is
  `sha256:a1dee1cddf12e22b9448806094ce6fbbcc6aa16ed13719ab720f3e9fbd1d3ab8`.
  It retains exact raw IEX responses plus hash-bound 5-minute canonical bars:
  10,000 bars and 129 common New York sessions per symbol, from 2026-01-13 to
  2026-07-10. The request asked for 2017-08-01 through 2026-07-10 but the
  provider returned the trailing 10,000 bars without an explicit truncation
  signal. IEX-only volume is not consolidated volume. No adjusted fields,
  corporate-action lineage, timestamp-boundary claim, PIT membership,
  campaign, paper, ranking, training, or profitability use is allowed.
- The nonpersistent SPY IEX scope probe used 2024-01-02 through 2024-06-28,
  5-minute explicit OHLCV fields, `afterHours=false`, and `forceFill=false`.
  It returned HTTP 200, 10,000 rows, schema
  `date/open/high/low/close/volume`, first timestamp
  `2024-01-02T19:40:00Z`, and last timestamp `2024-06-28T19:55:00Z`. No raw
  bytes, hash, cache, artifact, or snapshot was retained. This proves a
  non-overlapping historical window is reachable, not full-window completeness
  or a documented response-cap contract.
- The approved pre-r1 Tiingo IEX archive plan stopped without publication after
  two strict validation failures. The first attempt rejected an unreproducible
  SPY OHLCV row in the 2017-08-01 through 2017-12-31 window. A nonpersistent
  exact-window probe returned 8,502/8,501/8,502 rows for SPY/QQQ/IWM with no
  simple OHLC violation and retained no bytes. The final permitted attempt
  later rejected SPY `2018-04-25T15:25:00Z` because its high/low did not contain
  open and close. No raw response, cache, hash, r2 directory, or staging
  directory was retained. This does not establish a provider defect,
  completeness, source reliability, or research eligibility.
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
- The broad Yahoo development reference is fixed to
  `us_equities.yahoo_daily_universe.1d.snapshot=2026-06-23`, gzip hash
  `sha256:1690a766a820b3e6385c76605c7e02548ab0e428148c93f85388c7a6a8b065b4`,
  and manifest hash
  `sha256:642eff01919da260b388a66303db1954c68d7cd6ceb9685cac3c923d348b9a03`.
  It returns 6,555 common daily sessions for predeclared `SPY`, `QQQ`, and
  `IWM` from `2000-05-26` through `2026-06-22`. It is inception-truncated and
  survivor-selected, has unproven PIT/delisting coverage and unverified raw
  corporate-action history, and is not a market proxy or campaign input.
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
- Tiingo full-history standard-EOD evidence was acquired once at
  `2026-07-18T14:29:04.184884Z` into
  `D:\market_data\us_equities\fixed_etf_full_history\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-full-history-r1`.
  It queried `1900-01-01` through confirmed session `2026-07-10`, passed an
  eight-calendar-day retrieval lag, and has dataset hash
  `sha256:9ee21b6d955320b3855955b2072749e239b4b15e382dfbb6521e18f6f41a0016`
  and manifest hash
  `sha256:7d16513ec3acdd746ae3f2402ba7e8e09d3d43f7c8e033cdd2feea0bd639a99c`.
  It contains 8,418 SPY sessions (`1993-01-29` to `2026-07-10`), 6,876 QQQ
  sessions (`1999-03-10` to `2026-07-10`), and 6,568 IWM sessions
  (`2000-05-26` to `2026-07-10`), totaling 21,862 rows. The normalized data
  keeps raw OHLCV plus `div_cash` and `split_factor`, excluding adjusted fields.
  The offline loader rehashes raw and normalized bytes, rejects redirects before
  a token can be forwarded, requires every response to reach `source_as_of`,
  and requires common listed-session coverage. It is development evidence only,
  not PIT, ranking, holdout, campaign, paper-trading, or profitability evidence.
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

## Recent Diagnostic

- The exact r2 Yahoo-lineage versus full-history Tiingo raw-D1 check is
  `unsupported`. With both dataset hashes re-attested, the predeclared latest
  60 common Tiingo sessions with `divCash=0` and `splitFactor=1` had at least
  one OHLCV difference for every session and symbol. Exact `Decimal`
  `open/high/low/close/volume` matches were IWM `1/2/3/2/1`, QQQ
  `1/2/4/2/0`, and SPY `6/1/4/2/0`. Do not add a tolerance, normalization,
  rescale, helper, or data-quality gate from it.
- The short intraday smoke re-attested
  `us_equities.yahoo_intraday_starter.1m.snapshot=2026-07-09-shadow-t0-8d-probe`
  with hash `sha256:8a21be83e26ffad950a0b8a37a37c349d4c57de5526f52ff13103cf26c659bd6`.
  CVS had 2,758 loaded 1-minute bars; FCX and KO had 2,759 each. All three
  completed the `1m`/`5m`/`10m`/`1h`/`3h` local-paper smoke cells with two
  local-paper fills and flat replay. CVS's known missing minute and irregular
  tail remain warnings; neither was repaired or used as a quality gate.

## Recovery

- Recovery state is `complete`: do not overwrite any Tiingo snapshot. A later
  source re-pull comparison must create a new disjoint snapshot and retain these
  inputs as original evidence. Use the fixed ETF daily r2 manifest for
  development campaigns and retain r1 as lineage.
- Recover or mount the r2 subset only together with its unchanged sibling
  `manifest.json`. A different Windows/POSIX root is allowed when the snapshot
  directory name and `ohlcv_1d.csv.gz` basename are preserved; missing,
  tampered, or trailing-identity-inconsistent evidence is rejected.
- Stop acquisition on credential/payment/manual access, unclear rights, two
  consecutive automated failures for one source, loss of active-goal benefit,
  or projected breach of the 15% free-space floor.
- The exact Tiingo IEX pre-r1 archive plan is exhausted. Do not rerun it without
  a new operator-approved plan; retain the strict r2 contract and do not repair,
  normalize, or fill rejected source bars.
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
- `D:\market_data\us_equities\fixed_etf_full_history\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-full-history-r1\manifest.json`:
  one immutable raw-response and normalized-field record of the returned full
  Tiingo window; it is not a replacement for the short campaign snapshot.
- `D:\market_data\us_equities\yahoo_daily_universe\manifests\yahoo_daily_universe_snapshot=2026-06-23.json`:
  manifest for the fixed development-only ETF wrapper; its one canonical gzip
  is byte-pinned and no derived subset or artifact was written.
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

The broad Yahoo snapshot remains usable only as the pinned, static
development-only ETF wrapper. Its feature/outcome module re-attests the gzip
and manifest and accepts only `SPY`/`QQQ`/`IWM` raw bars internally; external
callers cannot retrieve the parser result. The new Tiingo full-history snapshot
is a separate read-only source; its exact raw-D1 comparison is closed as
`unsupported` and must not widen symbols, alter the `2000-05-26`
common-session start, or unwrap either source into a campaign/local-paper path.
The next local-paper smoke may use only the existing short intraday snapshot;
it is not a performance dataset. That smoke is complete; do not treat it as
historical coverage. The next source expansion must retain a manifest and
loader-attested lineage. The strict Tiingo IEX archive contract is retained as
an unexecuted publication path, but its fixed retrieval plan is closed after
two validation failures and must not be retried automatically. A future
universe-wide research claim still needs PIT membership and delistings.
The Norgate trial now supplies a local compatibility signal only. Keep its data
outside Git, preserve the retained C: copy, and do not interpret the D: mount as
a licensed Docker database path. The next Norgate work is one known-fixture
semantics check, not a provider implementation or a purchase recommendation.
