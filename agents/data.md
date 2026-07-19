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

The first fixed-ETF trial raw-D1 source snapshot is complete at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\snapshot=2026-07-18-norgate-trial-raw-d1-r2`.
It has 1,449 raw OHLCV rows across 483 common `SPY`/`QQQ`/`IWM` sessions from
2024-07-18 through 2026-06-22; dataset SHA-256 is
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993` and
manifest SHA-256 is
`5c8a5f06e618aaf3ec0ee7dc58ec9f545839fbfc87dc5476d52a8b4b4602458c`.
The host-only build used ephemeral `norgatedata==1.0.77`, recorded an external
deletion marker, and explicitly clipped range-padded capital-event output.
`NONE` is a requested query setting rather than verified adjustment semantics;
zero observed nonzero markers does not prove that no events occurred. Claude
returned `supported-with-limits`, so this is development-source evidence only,
not training, model, GPU, campaign, PIT, paper, ranking, or source-preference
evidence. Preserve r1 as superseded recovery evidence.

The r2 parent now has one immutable exclusion-only r3 sidecar at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\dividend_marker_exclusions\snapshot=2026-07-18-norgate-trial-raw-d1-r3-dividend-exclusions-r1`.
Its manifest SHA-256 is
`d5de2b77d02e4f7eb5b84392b8b5287b319c9218c034aa9e9613d80c57b4dd3c` and it
references the exact r2 hashes. One no-network local `Dividend` probe returned
an exact 483-session response and eight nonzero markers for each fixed ETF;
the sidecar records 24 source markers and 71 marker-plus-adjacent exclusions.
It stores no dividend amounts and does not name marker dates as event times.
Claude's `uncertain` review required exactly those nonzero, exact-session facts;
the facts held, but r3 remains exclusion metadata only with every training,
model, GPU, campaign, PIT, paper, ranking, and source-preference scope false.

The local Norgate broad development panel is complete at
`D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
It retained 523 of the fixed 541 candidates with an exact 483-session response
and recorded 18 session mismatches without repair or substitution. Dataset
SHA-256 is `3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`;
manifest SHA-256 is
`a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
Claude's `supported-with-limits` review makes its static selection and
100-symbol threshold explicitly non-coverage/non-quality evidence. The panel
is `development_training_eligible` for future engineering breadth preparation
only; PIT, ranking, holdout, campaign, model, GPU, paper, source-preference,
and profitability eligibility remain false.

The static-panel engineering loop consumed that panel through a derived feature
artifact only. Its two completed MLP jobs did not beat the fixed CPU linear
baseline, and its two TCN jobs are compute-rejected and untested rather than
negative model evidence. Data must not refill that model queue. The next ready
Data work is an offline Tiingo r2/Norgate cross-source cohort: 29 existing
Tiingo r2 symbols, 501 Tiingo sessions, a fixed 483-session overlap, and a
conservative event-window exclusion record without any provider call.

The bounded Norgate S&P 500 membership snapshot is complete at
`D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`.
It has a 541-item date-less candidate union and 266,647 sparse membership rows
covering 2024-07-18 through 2026-07-17. Its manifest, hashes, and deletion
marker are external-only. It remains explicitly non-PIT, non-campaign, and
non-model eligible.

The fixed-ETF Norgate raw-D1 alignment snapshot is also complete at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_raw_d1_alignment\snapshot=2026-07-18-norgate-raw-d1-alignment-r1`.
It is `literal_raw_ohlcv_difference`, not a source choice: Norgate returned
483 sessions per ETF from 2024-07-18 through 2026-06-22, while the pinned
Tiingo source has 896 and 413 additional earlier sessions per ETF. All-field
raw OHLCV equality occurred on only 96 `SPY`, 111 `QQQ`, and 201 `IWM` common
sessions. Its manifest and marker forbid campaign, model, paper, PIT, and
source-preference use.

The Norgate daily-history capability audit is closed as `supported`: the local
client returned zero rows for the two windows before 2024-07-18 and 483 rows
per ETF from 2024-07-18 through 2026-06-22. Its fields remained stable. The
official Norgate trial page and FAQ explicitly limit US trial daily history to
the last two years, so this is trial entitlement rather than a discovered NDU
setting issue. A longer Norgate history requires a paid subscription decision;
no configuration or download action is pending.

The bounded Tiingo standard-EOD coverage probe is complete. It used exactly 12
deterministic rank-quantile candidates over 2024-07-18 through 2026-07-17 and
returned 11 nonempty HTTP-200 responses plus one recorded HTTP-404, with no
retry, substitution, selected symbol, raw row, price, volume, or token
persistence. Its external summary is
`D:\thericher-v2\model-artifacts\data-agent\tiingo-eod-coverage-probe\snapshot=2026-07-18-tiingo-eod-coverage-probe-r1\summary.json`
with SHA-256
`4b2ef16520fdd530ae7cf6bbadc9dbe46cd9526670d859c2484097d3def9fce0`.
This proves only a small technical reachability sample. It does not establish a
historical universe, point-in-time membership, source completeness, or model
eligibility.

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

The Norgate trial compatibility and semantics checks are complete. `PLTR`
membership changed false-to-true on `2024-09-23`; for `SMCI`, the client-clipped
`Capital Event` marker is `2024-09-30` and the derived ratio transition is
`2024-10-01`. The query signature has a query-level adjustment option with an
observed `TOTALRETURN` default, and this one ratio transition is tenfold. These
facts are magnitude-consistent with the documented split but do not establish
field meaning, availability, or a general rule. The semantics branch is
`unsupported` and closed without a setting change.

The separately retained Norgate trial raw-D1 r2 snapshot is now the current
fixed-ETF source fact. It is host-only, raw OHLCV, hash-bound, and externally
stored, but intentionally not a `CatalogedBars` or campaign input: requested
`NONE` adjustment and no observed event markers cannot establish adjustment or
corporate-action semantics. Its explicit scope keeps training, model, GPU,
PIT, paper, ranking, and source selection false.

The r3 `Dividend` sidecar now supplies 24 nonzero source markers and 71
conservative exclusions after one exact-session local probe. The markers remain
source-returned dates rather than dividend/event timestamps; this did not
reopen the already-closed adjustment semantics branch or any research
eligibility. Its only effect is a hash-bound external exclusion record linked
to r2.

The Norgate broad panel is now complete. It re-attests the fixed membership and
r2 calendar parents, retains only the 523 of 541 candidates with exact
483-session raw-D1 responses, and records 18 session mismatches without repair
or substitution. It is a static development retrieval subset, not historical
membership, coverage, adjustment, or point-in-time evidence. Its limited
`development_training_eligible` flag opens only a future offline loader and
frozen engineering campaign contract; it does not itself start a model, GPU,
campaign, ranking, holdout, paper, or profitability path.

The narrow Windows-host-only Norgate raw-daily provider is complete. It accepts
only bounded US `1d` queries with UTC-midnight labels, asks the official client
for a query-local `NONE` adjustment and `numpy-recarray` response, and maps
only daily OHLCV into `Bar` values in memory. An ephemeral
`norgatedata==1.0.77` host smoke returned the requested `SPY` window from
`2024-09-27` through exclusive `2024-10-03` with four validated bars. The
package is not a project dependency, no trial rows were persisted, and the
adapter is not a catalog, Docker bridge, campaign, or research-data input.

The bounded historical-universe capability audit is complete and direct
date-specific enumeration is `unsupported`. Official documentation and the
local `norgatedata==1.0.77` signatures show that `watchlist_symbols` and
`database_symbols` have no as-of parameter, while
`index_constituent_timeseries` requires an already-known symbol. Its two
in-memory host probes returned a 541-item `S&P 500 Current & Past` candidate
list with no requested date, then a two-row bounded per-symbol membership
recarray with only `Date` and `Index Constituent` fields. No symbols, values,
rows, cache, artifact, or dataset were retained. That validates API shape, not
membership availability or a PIT universe.

The two Claude-reviewed Tiingo raw-daily snapshots are complete. R1 retained
29 available responses, one gap, and uneven returned histories. Hash-bound R2
excluded every R1 rank and retained 29 available responses, one gap, and 14,529
raw-field rows; all 29 R2 candidates share 501 returned sessions. The completed
offline audit re-attested exact hashes and rights markers, then wrote aggregate
facts at
`D:\thericher-v2\model-artifacts\data-agent\tiingo-daily-coverage-audit\snapshot=2026-07-18-tiingo-daily-coverage-audit-r1\summary.json`,
SHA-256 `e81ed382b9a68b0430a680c2c762a692822370a5a30cc96d21174065da0abb0c`.
Across both snapshots, 58 available candidates share only 18 sessions, while
56 candidate groups cover the R2 501-session returned window. The R1 floor is
binding, so a third Tiingo shard cannot raise the combined intersection. This
remains private-use, non-PIT, non-campaign, non-model, and non-GPU evidence.

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

The final metadata check used no setting mutation or raw values. The local
`price_timeseries` signature exposes query-level
`stock_price_adjustment_setting` and `padding_setting`; the observed default
is `StockPriceAdjustmentType.TOTALRETURN` with `CAPITAL`, `CAPITALSPECIAL`,
`NONE`, and `TOTALRETURN` enum members. Under that unchanged default call, the
four-row ratio transition category was tenfold on `2024-10-01`.

Official Norgate material says adjustment settings are configurable, capital
reconstructions include splits, and a selected split adjustment applies the
previous/new share ratio to prices before the ex-date. This makes the one
tenfold observation magnitude-consistent with the issuer's 10-for-1 split.
Claude returned `supported-with-limits` only for that literal consistency:
the evidence does not bind Python `TOTALRETURN` to UI semantics, show that the
ratio isolates splits from other adjustments, establish a source timestamp, or
justify a general rule. The field-meaning semantic branch is therefore
`unsupported` and closed. Reopen it only under a future load-bearing data
contract, not by changing settings or expanding this fixture.

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

1. Build one compact, offline Tiingo r2 cross-source validation cohort against
   the Norgate broad panel. Reattest both parents, retain rank linkage and
   conservative event-window exclusions, keep the later 18 Tiingo sessions
   forward-only, and do not create a model input or mix source price fields.
2. Do not acquire a third Tiingo raw-daily shard merely to increase common
   coverage; the existing r2 cohort is the bounded source validation input.

## Historical Queue Context

1. Supply the completed Norgate broad panel only through a future offline,
   hash-reattesting loader and frozen development-only Engine campaign contract.
   Do not use membership rows as selection facts or bypass the external parent
   lineage.
2. Do not acquire a third Tiingo raw-daily shard merely to increase the R1/R2
   common-session count. The audit found the R1 floor binding and 56 existing
   groups already cover R2's descriptive window.
3. Do not automatically retry the exhausted Tiingo IEX pre-r1 archive plan,
   relax its Bar invariants, repair/fill bad rows, or create a provider from r1.
4. If an operator later approves a source, collect only the specifically
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
- Norgate fixed-ETF trial raw-D1 r2 is the authoritative retained development
  source fact. It contains 1,449 raw OHLCV rows / 483 common sessions from
  2024-07-18 through 2026-06-22 with dataset SHA-256
  `a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993` and
  manifest SHA-256
  `5c8a5f06e618aaf3ec0ee7dc58ec9f545839fbfc87dc5476d52a8b4b4602458c`.
  The r2 manifest has an external deletion marker, a requested `NONE` setting
  with unverified semantics, and a clipped padded-event response. It observed
  zero nonzero markers, which is not absence-of-events evidence. Its scope
  explicitly forbids training, model/GPU, campaign, PIT, paper, ranking, and
  source-preference use. The older r1 is superseded recovery evidence only.
- The r2-linked Norgate `Dividend` sidecar is
  `D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\dividend_marker_exclusions\snapshot=2026-07-18-norgate-trial-raw-d1-r3-dividend-exclusions-r1`.
  Its manifest SHA-256 is
  `d5de2b77d02e4f7eb5b84392b8b5287b319c9218c034aa9e9613d80c57b4dd3c`.
  A single exact-session local probe observed eight nonzero markers for each
  fixed ETF, 24 total, yielding 71 conservative source-marker exclusions. It
  retains no dividend amounts, treats the marker dates as non-actionable, and
  cannot change r2's non-training, non-model/GPU, non-campaign, non-PIT,
  non-paper, non-ranking, or non-source-preference scope.
- The Norgate broad development panel is
  `D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
  It preserves 523 exact-session raw-D1 candidates from the fixed 541-item
  retrieval union across the 483-session 2024-07-18 through 2026-06-22 window;
  18 candidates are retained only as session-mismatch availability evidence.
  Dataset SHA-256 is
  `3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d` and
  manifest SHA-256 is
  `a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
  Claude returned `supported-with-limits`: the static filter and 100-symbol
  threshold are neither coverage/quality nor membership/PIT evidence. This is
  development-training preparation only; all campaign, model, GPU, ranking,
  holdout, paper, source-preference, and profitability claims remain false.
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

- The Norgate static validation r2/r3 TCN directories contain no final artifact
  and are recovery evidence only. Do not delete, overwrite, or reinterpret
  them as failed model metrics; r3's compact compute-rejection JSON names the
  exact restart boundary.

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
- `D:\thericher-v2\model-artifacts\data-agent\tiingo-eod-coverage-probe\snapshot=2026-07-18-tiingo-eod-coverage-probe-r1\summary.json`:
  12-request, symbol-private Tiingo standard-EOD reachability summary with 11
  available responses, one unavailable response, no retry, and no raw data.
- `D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r1\manifest.json`:
  completed 30-request private-use raw-daily pilot with 29 available responses,
  one unavailable response, 13,724 canonical raw-field rows, dataset SHA-256
  `ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56`,
  manifest SHA-256
  `69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f`, and
  a hash-attested Tiingo private-internal-use marker. Its returned histories
  are uneven and share only 18 sessions; it is not a model or GPU input.
- `D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r2\manifest.json`:
  completed r1-bound disjoint 30-request shard with 29 available responses, one
  unavailable response, 14,529 canonical raw-field rows, dataset SHA-256
  `6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`, and
  manifest SHA-256
  `76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
  Its 29 available candidates each returned 501 sessions, but no PIT or model
  eligibility opens from this date-less union.
- `D:\thericher-v2\model-artifacts\data-agent\tiingo-daily-coverage-audit\snapshot=2026-07-18-tiingo-daily-coverage-audit-r1\summary.json`:
  hash-attested aggregate-only audit summary, SHA-256
  `e81ed382b9a68b0430a680c2c762a692822370a5a30cc96d21174065da0abb0c`.
  It reports R1/R2 common coverage of 18, R2 common coverage of 501, and 56
  existing candidate groups covering the R2 window. It has no symbols, prices,
  PIT, campaign, model, GPU, or paper claim.
- `data-agent-market-data-inventory-cadence-20260717-r2`: bounded metadata
  inventory confirmed 2 roots, 5 snapshots, and 5 useful files; no acquisition.
- `data-agent-post-mpwr-lane-rotation-inventory-20260717-r1`: no immediate
  data-lane follow-up or operator request; the post-MPWR evidence question was
  already answered by existing artifacts.

## Next Handoff

The immediate next Data objective is the offline Tiingo r2 cross-source cohort,
not a third shard or another download. It must reattest the existing 29-symbol,
501-session r2 source and the 523-symbol, 483-session Norgate panel, reserve
the 483 shared sessions for later falsification only, retain the last 18 Tiingo
sessions as forward-only, and record event-window exclusions without making a
PIT, campaign, model, GPU, paper, or profitability claim.

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
The Norgate trial now supplies a narrow host-only raw-D1 adapter as well as
local compatibility evidence. Keep its data outside Git, preserve the retained
C: copy, and do not interpret the D: mount as a licensed Docker database path.
The adapter's UTC-midnight session label is an engine convention, not a source
timestamp claim; it does not resolve provider-field semantics or open a data
snapshot, campaign, model, or purchase recommendation. Direct historical
universe enumeration is closed as `unsupported`: a future snapshot must retain
the candidate union and per-symbol membership matrix as separate source facts.
That snapshot is now complete at
`D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`:
541 candidates, 266,647 sparse rows, 2024-07-18 through 2026-07-17,
`norgatedata==1.0.77`, matrix SHA-256
`d28060bfa5d81f913edc6d3500a46b7fdbc6bd00c8746e39068894b036758b55`.
It has a deletion marker and no staging residue, but is not a direct historical
list, publication-time evidence, PIT data, or an Engine input. The first
30-symbol Tiingo raw-daily pilot is complete at
`D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r1`:
29 available responses, one unavailable response, 13,724 raw-field rows,
dataset SHA-256 `ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56`,
and manifest SHA-256
`69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f`.
The 29 available candidates have only 18 common sessions and must not enter
model/GPU work. The disjoint r2 shard is now also complete at
`D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r2`:
29 available responses, one unavailable response, 14,529 raw-field rows,
dataset SHA-256 `6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`,
and manifest SHA-256
`76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
R2 alone has 501 common returned sessions, but the 58-candidate combined set
still has only 18. The completed aggregate audit confirms that 56 existing
groups cover R2's window and that R1 binds the combined floor, so do not pull a
third shard merely for more common sessions. The first Norgate fixed-ETF raw-D1
source contract is now r2 at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\snapshot=2026-07-18-norgate-trial-raw-d1-r2`;
it is source evidence only. Its r3 `Dividend` exclusion sidecar is complete:
24 source markers, 71 conservative exclusions, no stored amounts or event-time
claim, and no model input. The completed broad development panel is at
`D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`:
523 of 541 fixed candidates have exact 483-session responses, while 18
mismatches remain explicit availability evidence. Its data and manifest hashes
are `3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d` and
`a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
It can be consumed only by a future offline, hash-reattesting,
development-only loader and frozen research contract; it does not establish
PIT, adjustment, coverage, campaign, model, GPU, ranking, holdout, paper, or
profitability eligibility.
Tiingo's current
[terms](https://app.tiingo.com/tos/) and
[general documentation](https://www.tiingo.com/documentation/general) permit
the operator's private internal use but prohibit redistribution. Public Starter
pricing also lists 500 unique symbols per month, so the date-less 541-item
union must not be requested as one automatic batch. The pilot must preserve
that bound, write data only under `D:\market_data`, and create no model, GPU,
campaign, or source-selection claim.
