# TheRicher v2 Handoff

Use this file to recover current company state, not as an append-only work log.
Historical detail remains in Git and in external artifacts.

## Start Here

Repository: `C:\Users\Public\Documents\thericher-v2`

Run:

```powershell
.\scripts\start_next_codex_task.ps1
```

Then follow the single company objective in `NEXT_CODEX_GOAL.md`. The authority
order is:

```text
Operator -> Codex Orchestrator -> Role Agents
```

Codex should assign ready work to Data, Engine Research, and Execution, use a
temporary independent Validation role when needed, integrate the evidence,
verify, commit, push, refresh the next goal, and continue until a real operator
decision or external blocker is reached.

## Product Direction

The product goal is not to produce reports or prove that one favored strategy
is clever. It is to build a private US-equity trading engine that can earn a
small amount of money repeatedly, learn from live-like evidence, and improve
over time.

The engine loop is:

1. collect and qualify point-in-time market data,
2. create features and diverse model candidates,
3. backtest and walk-forward with executable targets and costs,
4. validate independently on sealed evidence,
5. paper trade through deterministic execution,
6. attribute PnL and failure causes,
7. promote only bounded candidates to small live capital.

Useful independent evidence per hour of operator attention is the practical
north star. Model count, GPU utilization, commit count, and report count are not
success metrics.

## Target-Position Engine Direction

The durable target architecture is a target-position policy graph, evaluated on
one immutable `as_of` snapshot at a time:

```text
PIT opportunity selection -> per-symbol multi-timeframe evidence
                           -> enter / hold / reduce / exit policy
current positions --------> constrained target-weight allocation
target deltas ------------> deterministic risk -> persisted broker intent
```

The graph separates which symbols deserve attention, whether to enter or leave
them, how much capital to allocate, and how to execute safely. Each node emits
timestamped evidence with an expiry and lineage; learned code never creates an
order. Initial scope is long-only. Build and validate the graph incrementally:
a simple deterministic baseline first, then one added layer at a time with
chronological cross-fitting, an untouched final holdout, and layer-level PnL
attribution. The full definition and dashboard boundary live in
`ARCHITECTURE.md`.

This replaces neither the current data requirement nor current execution
authority. No fresh model-eligible contract exists yet, and KIS submission/live
remains failed closed. The eventual Docker-local paper console is read-focused and exposes
sanitized holdings, prices, open orders, and safety state only after successful
read-only reconciliation; it does not grant submit authority by itself.

Historical-data limitations restrict what the project may claim about a model;
they do not make bounded KIS virtual-paper execution learning wait for an
otherwise perfect research dataset. KIS paper still needs its minimal execution
boundaries, a fresh reconciliation path, and a separately approved capital
envelope before any submission begins.

The immediate product path is KIS-native paper readiness. Active model inputs
must be reconstructible from KIS-compatible, completed market bars at decision
time. The first candidate is deliberately small: 90 completed `1m` bars plus
deterministic `5m`/`10m` resamples, with explicit abstention on a missing
window. `1h`/`3h`, order-book, news, corporate-action, and external-universe
features remain inactive until KIS capability evidence qualifies them. Offline
sources may develop a prototype but cannot silently supply a paper-time feature.

The broker-free foundation is now implemented: `data.kis_capability` keeps the
dated KIS capability record and completed-bar cache in memory; the raw-minute
KIS reader parses observed page fields without converting unqualified timestamps
into `Bar`; `research.kis_paper_baseline` requires a matching qualified
capability before producing a target-exposure proposal from exactly 90/18/9
completed bar views; and Execution alone maps that proposal to a local-paper
`OrderIntent`. Focused tests cover capability, missing, stale, incomplete,
duplicate, non-contiguous, and malformed-resample abstention plus replayable
`source: local_paper` fills. This is not KIS order support or an active paper
model.

## Current Boundaries

- KIS submission/live remains failed closed. The current KIS-native objective
  may read only `KIS_PAPER_*` through explicitly invoked, allowlisted
  **market-data** probes for `QQQ`/`SPY`; account, position, buying-power,
  open-order, submit, cancel, `KIS_LIVE_*`, paper capital, mode changes, and
  live behavior remain disabled. Imports, tests, local simulation, and the web
  process remain credential- and network-free. The credential-bearing client
  and direct transport also reject every non-`QQQ`/`SPY`, non-`NAS`, altered
  request shape, or fourth per-kind page before a connection opens.
- The operator-approved immediate QQQ/SPY historical capability runner was
  invoked once but stopped at its secret-safe config preflight with
  `config_missing`; it made no KIS request and wrote no reservation or summary.
  A nonsecret check found `THERICHER_MODE=off` but no configured paper app key
  or secret in the reader's approved `.env` prefix. Configure those two values
  before retrying this still-unreserved objective; never move or expose account
  or live values to make the reader pass.
- The 2026-07-19 KIS paper probes observed a `NASD` balance/position response,
  a 100-row unadjusted daily page, and two paged raw `1m` pages. Adjusted daily
  fields and several account endpoints returned `EGW00201`; those facts remain
  unavailable or unresolved rather than being inferred from another provider.
- The raw-minute client initially mistook an OAuth response without market
  `rt_cd` for an auth failure; its corrected HTTP/token-only handling passed
  fake transport tests and one bounded real `QQQ`/`NAS` paper read. It returned
  120 raw bars in descending exchange-time order from `19:59` to `18:00`, with
  a continuation indicator, and retained no raw price, token, or account value.
  A single client instance reuses its one successful token for a bounded first
  page plus continuation read; it does not refresh credentials per page.
  The first request uses `PINC=0`; the continuation uses the documented
  `PINC=1` rule and a `KEYB` one exchange-local minute before the preceding
  page's oldest bar, so the next probe expects no duplicate boundary row.
  Sanitized evidence is at
  `D:\thericher-v2\model-artifacts\execution\kis-paper-raw-minute-client-probe\20260719T060205390Z\summary.json`
  (SHA-256 `81e80a4c7a55e90cfde73e1349e83aa504f5f86589c3c5ac8e0122e4128c6f72`).
  The response does not qualify time conversion, completed-bar behavior,
  overlap/deduplication, rate, or storage rights; do not retry in a loop.
- Claude's latest falsification-first review is `uncertain`, not adverse to the
  direction. It requires a discriminating timestamp mapping, a live
  in-progress-bar completeness observation, and a repeatable overlap rule
  before the capability can become `qualified`. The KIS execution adapter is
  still code-disabled; only `local_paper` can consume the current baseline.
- The offline `kis_minute_qualification` harness v4 reserves one external,
  objective-specific attempt before a possible token, records
  `reserved -> network_started -> summary_written`, pins its artifact and Git
  roots, synchronizes each marker before a possible network side effect, rejects
  redirects and oversized pages, and requires a no-overlap **and exact
  one-minute boundary**. It rechecks a fresh clock after configuration,
  immediately before its network marker, and immediately before its first page.
  It accepts only the preverified 2026-07-20 Nasdaq session window and requires
  `--confirm-no-exception` after an independent official-calendar check; it
  writes sanitized metadata only from typed evidence/failure inputs. A one-shot
  result is always `observed` or `rejected`; it cannot promote a capability or
  read a bar-label anchor. No credential was read and no KIS request was made
  while preparing this v4 harness.
- A `qualified` KIS capability permits an in-memory completed-bar window only.
  Persistent raw-byte/cache storage still requires confirmed rights; otherwise
  retain only sanitized capability evidence outside Git.
- Existing broker-free fills keep `source: local_paper`.
- A sequential local-paper restart after a fill event but before its derived
  portfolio snapshot can return that one recorded fill only when the accepted
  order, both complete-bar fingerprints, price, fee, and fill timestamp still
  match. It does not append another fill or snapshot; changed bars or fee
  settings fail closed. Concurrent local-paper fill calls remain unsupported.
- Market data stays under `D:\market_data`.
- Generated model and run artifacts stay under
  `D:\thericher-v2\model-artifacts`; Docker uses `/app/model_artifacts`.
- The Docker `research` profile passed offline runtime and PyTorch CUDA compute
  smokes on 2026-07-19 (RTX 4090, 24564 MiB). Their small JSON evidence is
  external only under `gpu-runtime` and `gpu-compute`; this does not start or
  authorize a model campaign.
- Do not download data or model artifacts into the Git workspace.
- Free, no-auth, lawful, license-compatible data may be acquired autonomously
  when it directly improves active work. Paid or login/manual-license sources
  require operator approval.
- The operator's current data policy prohibits new paid market-data purchases,
  subscriptions, renewals, and upgrades. Keep the already approved Tiingo
  free-tier scope and local Norgate trial within their respective rights, but
  do not present a paid source as the required next step.
- Warn before `D:` falls below 20 percent free and stop autonomous acquisition
  before it falls below 15 percent free.
- Do not import v1 wholesale or recreate its report, gate, coordinator, or
  operator-console sprawl.

## Implemented Foundation

The repository already contains:

- immutable UTC/`Decimal` core contracts,
- append-only JSONL events with rebuildable SQLite query state,
- market-data provider interfaces, local/sample providers, and deterministic
  `1m`, `5m`, `10m`, `1h`, and `3h` resampling,
- stable training-readiness catalogs and byte-verified `CatalogedBars`,
- a static hash-bound broad-daily ETF wrapper that is intentionally not a
  campaign-ready input,
- one Data-re-attested, in-memory no-lookahead daily feature materializer for
  that separate development-only wrapper,
- one paired, future-only next-observed-session raw-close outcome materializer
  that stays outside campaigns and decisions,
- deterministic backtest and bounded validation paths,
- forward campaign contracts with target timing, purge/embargo, costs, and
  durable local-paper replay evidence,
- a fixed-instrument RAW D1 development campaign with factor sensitivity and
  bounded Docker/PyTorch CUDA training,
- a fail-closed corporate-action snapshot contract and completed no-retraining
  local-paper explicit-event replay for the fixed RAW D1 campaign,
- broker-free local paper orders, fills, cash, positions, replay, duplicate-id
  protection, and emergency state,
- broker-neutral lifecycle contracts with an atomic, restartable fake
  transport; all KIS behavior remains disabled,
- a pure pre-submit risk decision using fresh typed position, account,
  buying-power, open-order, reconciliation, and emergency evidence,
- research experiment, walk-forward, attribution, and artifact helpers,
- Docker research profiles with PyTorch CUDA smoke/training support,
- external artifact mounts and mount sanity checks,
- role stateboards and single-shot Data/Research workers,
- a local-only dashboard skeleton,
- one concise daily summary generator.

This is a substantial research codebase, not a greenfield skeleton. Prefer
consolidating existing helpers over adding another job kind or report family.

## Data Reality

Known useful intraday files are:

1. `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   - 572,894 rows, 250 symbols
   - sessions from 2026-06-09 through 2026-06-16
2. `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0\ohlcv_1m.csv.gz`
   - 7,103 rows, symbols CVS/FCX/KO
   - sessions from 2026-06-30 through 2026-07-09
3. `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0-8d-probe\ohlcv_1m.csv.gz`
   - 8,276 rows, symbols CVS/FCX/KO
   - sessions from 2026-06-29 through 2026-07-09

A larger daily universe exists at
`D:\market_data\us_equities\yahoo_daily_universe\canonical\ohlcv_daily`. Five
snapshots were inventoried and the newest 7,390,436-row file was fully scanned,
but adjustment, corporate-action, and point-in-time limitations still prevent
ranking or sealed-holdout use.

The newest broad snapshot now has one static development-only reference for
predeclared `SPY`, `QQQ`, and `IWM`. It pins the `2026-06-23` canonical gzip
hash `1690a766a820b3e6385c76605c7e02548ab0e428148c93f85388c7a6a8b065b4`
and manifest hash
`642eff01919da260b388a66303db1954c68d7cd6ceb9685cac3c923d348b9a03`.
It returns the common 6,555-session window from `2000-05-26` through
`2026-06-22` behind a development-only wrapper, not a campaign input. The
reference is inception-truncated and survivor-selected; point-in-time
membership, delisting coverage, and raw corporate-action semantics remain
unproven.

The wrapper's first consumer is a small in-memory feature/outcome module. For
each completed session it emits five-session and one-session raw-close returns,
same-session high/low range, and one-session volume change only after Data
re-attests the fixed gzip and manifest. It then re-attests again before pairing
each canonical feature at `t` with
`raw_close(next observed session) / raw_close(t) - 1`; the future outcome
session and calendar-day gap are explicit, and terminal features have no padded
outcome. Real-data smoke created 19,650 feature rows and 19,647 outcome rows;
the first pair is `2000-06-05 -> 2000-06-06` and the last is
`2026-06-18 -> 2026-06-22`. It preserves the original source hash and
limitations; it has no decision, artifact, campaign adapter, or trading use.

The campaign-ready fixed ETF subset is:

- `D:\market_data\us_equities\fixed_etf_daily\canonical\ohlcv_1d\snapshot=2026-07-18-r2`
- 21,823 raw OHLCV rows: SPY 8,405, QQQ 6,863, IWM 6,555
- dataset SHA-256
  `3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e`
- manifest SHA-256
  `909937ca2031eaf3b90e84974d3809b377f22abcf8214a3fe1695303a2e2ae6a`

The sibling manifest, dataset identity, bytes, mount-portable path tail, and
parent lineage are verified together. Development training is eligible;
ranking and sealed holdout are not. Adjusted fields are diagnostics only and
cannot enter campaign bars, fills, features, labels, thresholds, or metrics.
The current factor-change flags are useful diagnostics but are not
authoritative dividend or split lineage.

Current intraday data is suitable for parser, feature, replay, and development
smokes. It is not broad or independent enough for credible model ranking or a
final profitability claim.

One new fixed-ETF Tiingo IEX 5-minute snapshot is now available at
`D:\market_data\us_equities\fixed_etf_intraday\canonical\tiingo_iex_5m\snapshot=2026-07-19-tiingo-iex-5m-r1`.
It has dataset ID
`us_equities.fixed_etf_tiingo_iex_intraday.5m.snapshot=2026-07-19-tiingo-iex-5m-r1`,
dataset hash
`sha256:1531d803fb259c5f2233cc1b5f94441eb52bab9f31938232644879cc4aa1fcb6`, and
manifest hash
`sha256:a1dee1cddf12e22b9448806094ce6fbbcc6aa16ed13719ab720f3e9fbd1d3ab8`.
It preserves raw per-symbol IEX responses and reattested 5-minute canonical
OHLCV for SPY/QQQ/IWM. The request named 2017-08-01 through 2026-07-10, but the
provider returned only the newest 10,000 bars per symbol: 129 common sessions
from 2026-01-13 through 2026-07-10. Treat that response cap as a source fact,
not hidden historical coverage. It is IEX-only rather than consolidated, its
volume is IEX-only, and it has no adjustment/corporate-action, point-in-time,
timestamp-boundary, execution, ranking, campaign, paper, or profitability
claim. Its offline Data loader remains intentionally outside `CatalogedBars`,
provider, campaign, and paper APIs.

The one nonpersistent SPY query for 2024-01-02 through 2024-06-28 returned
HTTP 200 with 10,000 bars, `date/open/high/low/close/volume`, first timestamp
`2024-01-02T19:40:00Z`, and last timestamp `2024-06-28T19:55:00Z`. It retained
no bytes, hash, cache, artifact, or snapshot. That supports date-window access
and a bounded pre-r1 archive attempt; it does not prove a documented cap,
complete requested-window coverage, source independence, or research use.

The approved, fixed pre-r1 Tiingo IEX archive plan then stopped with no r2
snapshot. Its first strict validation attempt rejected an unreproducible SPY
OHLCV row in the 2017-08-01 through 2017-12-31 window. One nonpersistent exact
window probe returned 8,502/8,501/8,502 rows for SPY/QQQ/IWM with no simple
OHLC violation and retained no bytes. The final permitted archive attempt later
rejected SPY `2018-04-25T15:25:00Z` because high/low did not contain open and
close. No raw bytes, cache, hash, external r2 directory, or staging directory
was retained; D: remained 40.6% free. This proves neither a provider defect nor
complete history, reliability, independence, validation, campaign, paper, or
profitability eligibility. Retain the strict r2 contract, but do not repair or
fill invalid bars or retry this plan automatically.

Current canonical evidence:

- `D:\thericher-v2\model-artifacts\data-agent\training-readiness-catalog\data-agent-training-readiness-20260718-r2\catalog.json`
  has stable catalog/dataset hashes and marks zero files ranking or sealed-
  holdout eligible.
- `D:\market_data\us_equities\official_symbol_directory\raw\snapshot=2026-07-18\manifest.json`
  records the first immutable Nasdaq current-directory snapshot. It is
  prospective-only and does not repair historical survivorship or delistings.

`D:` has about 40.6 percent free. SEC current mappings were not
collected because compliant automation needs an honest identifying contact;
none was invented.

The newest Tiingo standard-EOD probe made exactly 12 deterministic requests
against the external Norgate candidate union for 2024-07-18 through 2026-07-17.
It recorded 11 nonempty HTTP-200 responses and one HTTP-404 without retry or
substitution. Its symbol-private, metadata-only external summary is
`D:\thericher-v2\model-artifacts\data-agent\tiingo-eod-coverage-probe\snapshot=2026-07-18-tiingo-eod-coverage-probe-r1\summary.json`, SHA-256
`4b2ef16520fdd530ae7cf6bbadc9dbe46cd9526670d859c2484097d3def9fce0`.
This is technical reachability only, not point-in-time, universe, campaign,
model, GPU, or paper evidence.

Official [Tiingo terms](https://app.tiingo.com/tos/) and
[API documentation](https://www.tiingo.com/documentation/general) allow the
operator's internal personal use but prohibit redistribution. Public Starter
pricing lists a 500-unique-symbol monthly cap, so no 541-symbol automatic pull
is authorized by this evidence. The first 30-symbol raw-daily acquisition pilot
is complete at
`D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r1`.
It made 30 requests with 29 available responses, one unavailable response, and
13,724 canonical raw-field rows. Dataset SHA-256 is
`ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56`; manifest
SHA-256 is `69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f`.
The 29 available candidates have only 18 common sessions and histories from 18
to 501 rows. This is private-use source evidence, not a point-in-time universe,
common panel, campaign, model, GPU, or paper input. The disjoint r2 shard is
also complete at
`D:\market_data\us_equities\tiingo_standard_eod_pilot\canonical\snapshot=2026-07-18-tiingo-standard-eod-pilot-r2`.
It made 30 requests with 29 available responses, one unavailable response, and
14,529 canonical raw-field rows. Dataset SHA-256 is
`6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`; manifest
SHA-256 is `76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
The completed offline coverage audit re-attested both snapshots and their
rights markers at
`D:\thericher-v2\model-artifacts\data-agent\tiingo-daily-coverage-audit\snapshot=2026-07-18-tiingo-daily-coverage-audit-r1\summary.json`,
SHA-256 `e81ed382b9a68b0430a680c2c762a692822370a5a30cc96d21174065da0abb0c`.
It confirms R2 alone has 501 common returned sessions, R1/R2 combined has 18,
and 56 existing candidate groups cover the R2 501-session returned window.
The combined floor is bound by R1. Do not acquire a third Tiingo shard merely
to increase it; the source remains non-PIT, non-campaign, non-model, non-GPU,
and non-paper evidence.

The approved Tiingo standard EOD collection produced one immutable private-use
snapshot at
`D:\market_data\us_equities\fixed_etf_corporate_actions\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-corporate-actions-r1`.
It binds exact raw SPY/QQQ/IWM responses to r2 sessions, 46 cash-distribution
events, zero split events, and the replay-only normalized dataset hash
`3587beb050cabd9b3be0d68a66395b9a1a369010f2515fb22d7287d7b87d06f8`.
Its manifest hash is
`89fdc4717f3b3a596a58afe1242ad1680f141a6abf92f4a92115b603df77ccf4`.
It proves returned-session coverage, not that a future source re-pull cannot
restate data; any later comparison must create a new immutable snapshot.

One separate, full-history Tiingo EOD evidence snapshot now lives at
`D:\market_data\us_equities\fixed_etf_full_history\canonical\tiingo_standard_eod\snapshot=2026-07-18-tiingo-eod-full-history-r1`.
It queried `1900-01-01` through the confirmed `2026-07-10` session and contains
21,862 raw-field rows: SPY 8,418 (`1993-01-29`), QQQ 6,876 (`1999-03-10`), and
IWM 6,568 (`2000-05-26`), all ending `2026-07-10`. Its normalized dataset hash
is `9ee21b6d955320b3855955b2072749e239b4b15e382dfbb6521e18f6f41a0016` and its
manifest hash is `7d16513ec3acdd746ae3f2402ba7e8e09d3d43f7c8e033cdd2feea0bd639a99c`.
The loader preserves raw OHLCV, `divCash`, and `splitFactor`, excludes adjusted
fields, re-attests raw and normalized bytes offline, rejects redirects, and
requires confirmed final/common listed-session coverage. It remains development
evidence only: not a PIT universe, independent validation, ranking, holdout,
campaign, paper-trading, or profitability input.

The bounded r2 Yahoo-lineage versus full-history Tiingo raw-D1 diagnostic is
complete and `unsupported`. It re-attested r2 dataset hash
`3deaf812461d8d2619db3657f100521c293c5d5e7b460e82959b00c6e2a9875e` and
Tiingo dataset hash
`9ee21b6d955320b3855955b2072749e239b4b15e382dfbb6521e18f6f41a0016`, then
used the predeclared latest 60 common Tiingo sessions with no Tiingo cash
distribution or split. Every symbol had at least one raw OHLCV difference on
all 60 sessions; exact `Decimal` matches in `open/high/low/close/volume` were
IWM `1/2/3/2/1`, QQQ `1/2/4/2/0`, and SPY `6/1/4/2/0`. Do not introduce a
tolerance, normalization, rescale, source preference, helper, test family, or
external artifact from this result. It says nothing about source correctness,
adjustment semantics, interchangeability, independence, PIT, execution, or
profitability.

The offline intraday multi-timeframe local-paper baseline is complete. It
re-attested the existing CVS/FCX/KO 1-minute snapshot
`us_equities.yahoo_intraday_starter.1m.snapshot=2026-07-09-shadow-t0-8d-probe`
with hash
`sha256:8a21be83e26ffad950a0b8a37a37c349d4c57de5526f52ff13103cf26c659bd6`.
For each symbol it used a completed `1m`/`5m`/`10m`/`1h`/`3h` resampled bar as
the decision input, then exactly the next two contiguous 1-minute bars for
local-paper entry and flattening. All 15 cells had two `source: local_paper`
fills and replayed flat. The result carries no PnL, ranking, model, campaign,
holdout, execution-quality, or profitability claim. Default smoke evidence was
intentionally temporary; specify an external work root only when durable event
evidence is genuinely needed.

A prior Claude CLI attempt was unavailable. The earlier role checks remain
valid historical evidence. The Norgate trial
compatibility decision later received a concise Claude `supported-with-limits`
verdict; it covers connector availability only, not PIT correctness, event
semantics, or a research decision.

A bounded no-auth triage acquired no new data. `D:\market_data\pit_sources`
has only empty raw/template workspaces for paid Sharadar and Norgate source
paths. Stooq requested browser verification and was not bypassed; the existing
official Nasdaq directory is current/prospective only and cannot repair
historical universe or price provenance. The existing Tiingo bytes now also
have one derived raw-D1 snapshot at
`D:\market_data\us_equities\fixed_etf_daily\canonical\tiingo_raw_d1\snapshot=2026-07-18-tiingo-raw-d1-r1`.
It has 2,688 rows (896 exact r2 sessions per SPY/QQQ/IWM), dataset hash
`9056112167ab920335cb8a5f3c2f45d540a04e1132ee6eb231bac16ee11d7a3d`, and
manifest hash `44a6316e9821694886fa3f791ddb19ec56a435dbaf765417a9568b4a3e57f421`.
It keeps only raw OHLCV plus `div_cash` and `split_factor`, copies no raw source
file, and binds the parent Tiingo hashes and r2 calendar lineage. It is a
separate-provider representation conditioned on r2's session calendar, not an
independent validation, holdout, selection, or profitability result. The
offline loader now re-attests r2 from disk, parent Tiingo raw evidence, snapshot
hashes, exact canonical raw-D1 bytes, and 896 sessions before returning a
`CatalogedBars` stream. One frozen no-retraining sensitivity replay is the next
bounded step.

The Data stateboard owns exact catalog status and operator data requests.

The operator-created Norgate US Stocks Platinum trial now has a bounded local
compatibility result and two date-scoped fixture observations. Its configured D: path is
`D:\market_data\us_equities\norgate_us_platinum_trial`; after an operator
location switch and update it contained 429 files / 6.12 GiB, with a newer file
time than the retained C: copy. Windows `norgatedata==1.0.77` exposed daily
OHLCV, Turnover, Unadjusted Close, Dividend, Index Constituent, Major Exchange
Listed, and Capital Event fields. Membership/listing queries honored a short
range, while `capital_event_timeseries` returned the wider trial horizon. The
trial is about two years; explicit client-side clipping is therefore a future
consumer requirement, not an implemented provider feature. In the observed
fixtures, `PLTR` changed membership false-to-true on `2024-09-23`, matching the
public S&P effective-before-open date; clipped `SMCI` Capital Event marked
`2024-09-30`, matching the issuer's split-effective date while split-adjusted
trading began `2024-10-01`. Claude supports those literal observations only.
Do not use the capital-event date as a price-adjustment, ex-date, or
availability timestamp; the next check compares it with the
`Close`/`Unadjusted Close` ratio transition.
Subsequent `SMCI` timing evidence used `2024-09-27` through `2024-10-02`: four
ordered daily price rows had a `Close`/`Unadjusted Close` ratio transition only
on `2024-10-01`; the 501-row capital-event response clipped to four rows with
one marker on `2024-09-30`. This is consistent with the issuer's after-close
effective time and next-session split-adjusted trading, but only as a literal
stored-field observation. It prohibits treating a marker as same-session
actionable or as the price-ratio date; it does not establish population time,
a general lag, or that the ratio isolates split adjustment. The final bounded
metadata check found query-level `stock_price_adjustment_setting` and
`padding_setting`, with an observed `TOTALRETURN` default and a tenfold ratio
transition on `2024-10-01`. Official Norgate material makes that magnitude
consistent with the split, but does not bind the Python setting to UI semantics
or show that the ratio isolates splits. Claude supports the literal observation
only; the semantic branch is `unsupported` for provider/campaign field meaning
and is closed without a setting change. A future load-bearing use must reopen
under its own data contract.
A Docker `engine`
runtime probe listed 166 top-level files through the `/app/market_data` `ro`
mount, but no proprietary Docker query or export bridge is licensed or
implemented. This is compatibility
only, not PIT, data-correctness, provider, campaign, model, paper, or purchase
evidence. Keep the C: copy and all Norgate data outside Git.

The repository now has `NorgateRawDailyBarProvider`, a Windows-host-only raw
US-D1 adapter. It lazy-loads the optional official package, requires bounded
UTC-midnight `BarQuery` dates, explicitly requests query-local `NONE` and a
`numpy-recarray`, and keeps response rows in memory. A host smoke with
ephemeral `norgatedata==1.0.77` returned four validated `SPY` bars for
`2024-09-27` through exclusive `2024-10-03`; it recorded no rows, prices,
artifact, cache, or project dependency. The UTC-midnight date is an engine
label convention, not a Norgate source-timestamp claim. This creates neither a
catalog nor campaign/model/paper eligibility, and does not reopen the closed
field-semantics branch.

The next bounded Norgate audit closed direct historical-universe enumeration as
`unsupported`. The official Python API documents
`index_constituent_timeseries(symbol, indexname, ...)` as a per-symbol boolean
series; `watchlist_symbols` and `database_symbols` have no as-of-date argument.
Two in-memory host probes matched that shape: `S&P 500 Current & Past` returned
a 541-item candidate list without an as-of input, while one bounded PLTR
membership call returned a two-row `Date`/`Index Constituent` recarray within
its requested two-day window. No symbols, values, rows, cache, artifact, or
dataset were retained. A later matrix may combine these documented source facts
only under a new explicit contract; it must not be described as a direct
historical-list API or as publication-time/PIT proof.

## Research Reality

The fixed RAW D1 campaign uses the latest 896 common sessions from 2022-11-22
through 2026-06-22. Its disjoint split is
`252 development / 2 purge / 63 validation / 2 embargo / 512 development /
2 purge / 63 validation`. Completed session `t` enters at the adjacent observed
`t+1` raw open and exits at `t+2` raw open, with 10 bps fee and 5 bps adverse
slippage per fill. All replay evidence is external, monotonic, flat at the end,
and labeled `source: local_paper`.

The complete CPU preflight is:

- `D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-development-20260718-cpu-r2\cpu-summary.json`
- SHA-256 `9ee93a8bf4ecfff92bd71d7c49c613dd8fe567e5ab7f70e23feffed4c4462c95`
- 36 replay cells and 108 verified replay-state hashes
- both trading baselines lost after costs; factor sensitivity was
  `supported-with-limits`

The bounded Docker/PyTorch CUDA result is:

- `D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-development-20260718-cuda-r1\summary.json`
- SHA-256 `5db680e1ba72a17b089a5c44372443289b2411c690f6372b6c6f2e3e35ac1d89`
- six fixed checkpoints, 72 replay cells, and 216 verified replay-state hashes
- PyTorch `2.7.0+cu128` on RTX 4090; maximum recorded allocation 18,129,408 bytes

The CUDA evidence is structurally valid but the research verdict is
`unsupported`. `d1-pressure-lb20` changed sign for IWM/fold-1 and QQQ/fold-1
under factor exclusion, and aggregate item order reversed. No candidate was
selected or promoted, and no profitability claim is permitted. The interrupted
`cpu-r1` attempt has no summary and is non-authoritative.

The explicit-event replay `raw-d1-explicit-events-20260718-r3` is complete at
`D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-explicit-events-20260718-r3\summary.json`
with SHA-256
`3cac5f0b14e602c6a0043bb141fa7d6add1ca02b8ab4e214145443a1d8711609`.
It reused the six fixed checkpoints on CPU, trained zero models, executed 18
baseline plus 18 candidate cells, kept every fill `source: local_paper`, and
finished every cell flat. Its development-only labels and sticky parent
`unsupported` verdict remain unchanged. The r1 interruption and r2
summary-write failure are incomplete, non-authoritative external artifacts.

Its compact read-only attribution is
`D:\thericher-v2\model-artifacts\attribution\raw-d1-explicit-events-20260718-r3-attribution-r1\summary.json`
with SHA-256
`3de06a073b50f4b3b548a14a2d6040ebcb713b78b9a69a08b4add5f129b86e70`.
It independently rechecked r3 and 144 referenced cell evidence hashes, records
36 fixed cells and 300 local-paper fills, and confirms every cell finishes
flat. It deliberately omits cross-cell PnL sums because the cells overlap and
are not independent. Its scope is arithmetic consistency of shared local-paper
evidence, not independent execution quality, strategy selection, or
profitability.

The bounded Tiingo raw-D1 source-sensitivity replay is complete at
`D:\thericher-v2\model-artifacts\daily-campaign\raw-d1-tiingo-source-sensitivity-20260718-r1\summary.json`
with SHA-256
`2e91c133fd12e0e28a7011eb0c1d3f661fe0fffab094ab00b679d3a566a14ff3`.
It reused the six r2 source checkpoints on CPU, trained zero models, executed
18 baseline plus 18 candidate cells with `source: local_paper`, and finished
every cell flat. The strict loader verified the pinned raw-D1 gzip hash plus
decompressed canonical CSV content against the parent Tiingo bytes, allowing the
Windows snapshot to re-attest in Docker. Across matching r2 explicit-event
cells, decision count, trade count, and after-cost-PnL sign did not change.
That is descriptive, non-independent evidence only because the r2 session
calendar remains shared; the parent `unsupported` verdict stays sticky and no
selection, promotion, or profitability claim is permitted.

GPU research is eligibility-driven rather than utilization-driven. A finite
predeclared breadth batch may start only from a hash-bound dataset explicitly
eligible for development training and a contract with fixed target, costs,
temporal split, metrics, and stop rules. It then uses CPU baselines plus two
fixed-seed MLP/TCN candidates, followed only by sensitivity/Claude-cleared
depth and out-of-fold-only ensemble work. No scheduler or automatic refill is
allowed, and idle is correct when the contract is absent. No remaining dataset
currently meets those conditions for a new model batch.

The static Norgate panel has now completed its one permitted engineering-only
validation loop. Derived feature artifact
`D:\thericher-v2\model-artifacts\norgate-broad-development-features\r2-3c1b21bde92e4623`
re-attests the raw parent and has artifact hash
`sha256:3f03d6cdc669e174c7cc1c79edb0921d1781f79e364302df88a38d6a314e72e7`.
The r3 CPU/MLP evidence uses the same contract hash
`sha256:29fca05b61c9702967b59c66ac60a8b8a06de73b309b9e292b64a544b059779a`.
Date-mean accuracy was `0.50269` for the fixed linear baseline, `0.49865` for
MLP seed 71, and `0.50028` for MLP seed 113. Both MLP checkpoints safe-reload
and neither result is strong, selected, or ensemble-eligible.

The compact TCN is untested, not negative evidence: two bounded attempts wrote
no checkpoint, prediction, or summary before manual stop after observed lower
bounds of 904 and 1,252 seconds. A representative CUDA preflight measured
`0.5538` seconds per TCN step versus `0.0281` for MLP. The external r3
`cuda/temporal-conv-compute-rejection.json` records this resource decision;
it must not be described as a completed four-model breadth comparison. Claude
returned `supported-with-limits` for closing this static-panel work with two
completed MLP jobs and two compute-rejected, untested TCN jobs. No static-panel
retry, model extension, ranking, ensemble, PnL, paper, or live use is open.

## Execution Reality

The broker-free simulator is the only enabled execution path. The broker-
neutral fake requires an intent to be atomically persisted before submit,
survives JSON restart, handles partial/full fills and cancellation, and blocks
retry while an outcome is unknown until authoritative resolution and clean
reconciliation. Fake fills use `source: in_memory_broker`; broker-free simulator
fills remain `source: local_paper`.

The pure pre-submit risk decision consumes a fresh matching
`PositionSnapshot` and proves sell safety by quantity rather than notional.
Verified long reductions may bypass entry-only emergency, loss, and order-count
caps, while missing/stale/mismatched position, incomplete open orders, unsafe
reconciliation, unknown outcomes, and non-durable intents still fail closed.
It does not submit. Generic D1 local paper accepts a later caller-supplied
observed bar; the daily campaign separately proves exact `+1/+2` adjacency.

One scoped KIS virtual-paper read-only discovery was attempted while
`THERICHER_MODE=off` remained unchanged. The corrected open-order-first request
was rejected, so the boundary failed closed and wrote only redacted failure
evidence under `D:\thericher-v2\model-artifacts\execution\kis-paper-readonly`.
No account snapshot, cash, position, open-order record, order action, capital
allocation, or live behavior was produced.

An offline comparison against the current official
[inquire-nccs sample](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_nccs/inquire_nccs.py)
and its shared
[virtual-environment helper](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/kis_auth.py)
confirmed the pinned host, GET path, virtual `VTTS3018R`, 8-2 account shape,
query fields, and `M`/`F` to `N` continuation. It also documented that one
`NASD` query is US-wide. The reader now issues that single query, accepts its
`NASD`/`NYSE`/`AMEX` rows, and sends the documented empty initial `tr_cont` for
every fixed read-only GET. It records only fixed endpoint/TR ID and HTTP status
on a future rejection, never response text or response-derived codes. The prior
generic failure cannot prove a root cause.

The one approved post-diagnosis retry is complete and failed closed at the
balance stage. Its external evidence is
`D:\thericher-v2\model-artifacts\execution\kis-paper-readonly\20260718T095422248003Z-failed_closed.json`
with SHA-256
`9ee43196ee53305cb62eee5ba582d8f56bce17b2c9f297094abe5f482b4738d8`.
Its only diagnostic fields are fixed `balance` / `VTTS3012R` and HTTP `500`;
there is no account snapshot, response text, or response-derived code. The
later failure means open orders did not block this one run, not that the earlier
open-order issue is resolved. Do not retry automatically or infer a cause from
the HTTP status alone.

The current official
[inquire-balance sample](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_balance/inquire_balance.py)
confirms the virtual host, GET path, `VTTS3012R`, 8-2 account split,
`NASD`/`NYSE`/`AMEX` mock coverage, query fields, and `M`/`F` to `N`
continuation. The shared official helper sends `tr_cont`, including `""` on an
initial GET. The client had omitted that header for balance and orderable-funds
reads; it now emits it for every fixed read-only GET and has fake-transport
coverage. This removes one documented deviation; it does not explain, resolve,
or establish a cause for the HTTP `500`, and no post-change probe was run.

The remaining first discriminator is non-secret operator confirmation that the
separate virtual app, virtual securities account, and its 8-2 account/product
pair are active and matched. If that is confirmed, a separately authorized
one-time read-only probe can distinguish the corrected request from an
unavailable or unsupported virtual service. Keep only fixed endpoint/TR ID/HTTP
status metadata on any future failure, never response text or response-derived
codes.

KIS paper is an early execution milestone, not a reward for model profitability.
After the approved read-only discovery reconciles buying power, Codex proposes a
paper capital envelope based on the smaller of actual orderable paper funds and
intended shadow live capital; the current planning reference is KRW 5,000,000.
The operator approves or changes that envelope once. Routine paper work inside
it then continues without repeated approval. Submit/cancel and live mode remain
separate decisions.

## Agent State

- `agents/data.md`: owns source inventory, quality, acquisition, and manifests.
- `agents/engine-research.md`: owns campaign contracts, features, models,
  walk-forward evidence, attribution, and GPU queues.
- `agents/execution.md`: owns deterministic lifecycle, accounting, risk,
  reconciliation, and later KIS adapters.
- Validation is temporary and cannot tune the candidate it evaluates.
- Infra and Review are invoked capabilities, not durable queues.

Stateboards are current projections, not the only memory. The planned shared
memory substrate is an append-only external ledger plus a rebuildable catalog:

- `D:\thericher-v2\model-artifacts\_control\ledger\YYYY-MM.jsonl`
- `D:\thericher-v2\model-artifacts\_control\catalog.sqlite`

Do not build a daemon or general agent platform around this. Add the smallest
shared schema only when an active engine loop needs cross-role lineage or crash
recovery.

## Claude Review

Claude is a falsification-first challenger, not an approver. Invoke it before a
decision relies on leakage/survivorship-sensitive data construction,
breadth-to-depth promotion, sealed holdout use, unexpectedly strong claims,
correlated ensembles, KIS capital/risk changes, incident recovery, or major
architecture/runtime growth.

Ask for `unsupported`, `uncertain`, or `supported-with-limits`. A negative
verdict pauses only that boundary. Safe parallel work and emergency containment
continue. Never send credentials, account identifiers, raw sealed labels, or
unnecessary row-level data.

## Recovery And History

- Pre-compaction historical state is available at commit `8f416f8` and earlier.
- Generated evidence belongs under the external artifact root and should be
  referenced by stable path or run id, not copied into Markdown.
- A role reports recovery using its active work, last durable evidence, held
  resources, and exact next action.
- Codex checks cross-role dependencies and recovery claims before resuming.

## Next Objective

**Latest state, superseding the older target statement below:** the first
source-separated research-contract preflight and its CPU-only batch are complete.
Its immutable external contract is
`D:\thericher-v2\model-artifacts\norgate-tii-source-separated-contract\norgate-tii-source-separated-contract-r4\contract.json`,
SHA-256 `ddba0d578bf5ddaefe10c0c72b63ad8873a27c2243787e504d3c4e8fac0bf76e`.
It reattests the completed Tiingo/Norgate cohort and the Norgate feature
artifact, fixes 29 exact rank/symbol pairs, and keeps Norgate as the sole
price, feature, and label source. Tiingo contributes only attested
rank/session/returned-marker metadata; its 18 forward-only sessions never
enter the slice.

The contract has 10,053 rank-decision pairs after the Tiingo conservative mask
and 9,904 after the explicitly attested Norgate raw-discontinuity conditioning:
6,434 development, 50 purge, and 3,420 validation rows. The 149-row difference
is explicit and checks Norgate `t-20..t+2` dependencies at a 20 percent raw
discontinuity threshold; it is not a corporate-action assertion and is not
point-in-time safe. Claude and the independent Validation Agent both returned
`supported-with-limits`. This remains static survivor/availability-conditioned
engineering evidence only, with raw-adjustment and action semantics unverified.

CPU evidence is at
`D:\thericher-v2\model-artifacts\norgate-tii-source-separated-batch\norgate-tii-source-separated-batch-r1\cpu-baseline.json`,
SHA-256 `a6f181b504aa9cb6c6b55af59096c3d5c7e4363dc69978b82bb5a4239a80c4ad`.
It is inconclusive engineering evidence only. The first predeclared CUDA MLP
stopped before prediction/checkpoint creation because deterministic CUDA mode
lacked `CUBLAS_WORKSPACE_CONFIG`; its immutable failure is SHA-256
`0f93bec411c74aad8980d68af524f046f47051be8230295d48c518808a47217c`.
The second MLP was deliberately not started. Do not retry either r4 MLP or reuse
its validation slice. Commit `ae0d3ec` fixes the Docker research workspace and a
network-disabled synthetic CUDA smoke passed, but that is infra-only evidence.
Claude's recovery verdict was `supported-with-limits`.

Data's manifest-first local replacement inventory is now complete at
`D:\thericher-v2\model-artifacts\data-agent\local-replacement-inventory\local-replacement-inventory-r2\summary.json`,
SHA-256 `c7c1de08e33b3ea2a70688a9ec71903ba39ea00531c38bacf43bd053a5c1cf8d`.
It found no fresh local daily candidate for a new training contract: the
Norgate window is r4's closed parent, Tiingo r2 only adds 18 forward sessions
with a static non-PIT union, the fixed ETF paths are exhausted or unsupported,
and the short intraday source remains descriptive. Broad Yahoo is
`data_preflight_only`, never a model, GPU, paper, or profitability input.

The next bounded action is one prospective standard-Tiingo-EOD refresh for the
already authorized `SPY`/`QQQ`/`IWM` scope after `2026-07-10`. It starts clean
forward data lineage only; it does not create a model contract, train, reopen
r4, or use GPU merely to avoid idle time. A genuine new model batch needs
point-in-time universe and adjustment provenance. Norgate US Stocks Platinum or
an equivalent paid PIT source remains an operator purchase decision; verify its
current official price before asking for approval or buying anything.

**Current target, superseding the older historical context below:** the offline
Tiingo r2/Norgate cross-source cohort is complete at
`D:\thericher-v2\model-artifacts\tiingo-norgate-cross-source-cohort\tiingo-norgate-cross-source-cohort-r1`.
Its sole `manifest.json` is 79,969 bytes with SHA-256
`dbc2b25ca514262355c9e4e2bf834889f16358058315b21eb24556b2ccdb1213`.
It reattests the fixed Tiingo r2 and Norgate parents, retains 29 linked ranks,
501 Tiingo sessions, 483 overlap sessions, 18 forward-only sessions, 153
Tiingo action markers, and 3,316 conservative `t-20..t+2` rank-decision
exclusions. Host and Docker reattestation agree. It is metadata-only,
cross-source engineering evidence: non-PIT, non-training, non-model,
non-ranking, non-paper, and non-profitability evidence.

The first fixed-ETF Norgate trial raw-D1 source snapshot is now complete at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\snapshot=2026-07-18-norgate-trial-raw-d1-r2`.
It retains 1,449 raw OHLCV rows across 483 common sessions for `SPY`, `QQQ`,
and `IWM`, from 2024-07-18 through 2026-06-22. Its dataset SHA-256 is
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993`; its
manifest SHA-256 is
`5c8a5f06e618aaf3ec0ee7dc58ec9f545839fbfc87dc5476d52a8b4b4602458c`.
The local source build used ephemeral `norgatedata==1.0.77` through the
already-installed Windows trial, explicitly clipped a range-padded capital-event
response, and retained a rights/deletion marker. Claude's final verdict was
`supported-with-limits`: `NONE` is only the requested query setting, and zero
observed markers does not establish that no corporate events occurred. The r2
snapshot is development-source evidence only; it is not eligible for training,
model/GPU work, PIT, paper, ranking, or a source-preference claim. Preserve the
earlier r1 directory as superseded recovery evidence; do not reuse it.

One bounded local `Dividend` field probe then returned an exact 483-session
response for every fixed ETF, with eight nonzero source markers per symbol. It
produced the immutable, exclusion-only r3 sidecar at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_trial_raw_d1\dividend_marker_exclusions\snapshot=2026-07-18-norgate-trial-raw-d1-r3-dividend-exclusions-r1`.
Its parent data/manifest hashes are r2's hashes above; sidecar manifest SHA-256
is `d5de2b77d02e4f7eb5b84392b8b5287b319c9218c034aa9e9613d80c57b4dd3c`.
It records 24 source markers and 71 adjacent-session exclusions, not dividend
amounts or event timestamps. Claude's pre-probe verdict was `uncertain` and
required an exact, nonzero marker response for all three symbols; that bounded
condition was met. This refines exclusion metadata only: adjustment semantics,
PIT, campaign, model, GPU, paper, ranking, and source preference remain false.

That panel is now complete at
`D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
It preserves raw OHLCV only for the 523 of 541 fixed candidates whose one local
response exactly matched the 483-session r2 calendar; 18 session-mismatch
candidates were recorded but excluded without repair. Dataset SHA-256 is
`3d0841b90ddfd8d861f2432e404617ec0fc6e1afb8c902a81972df518720402d`; manifest
SHA-256 is `a7ff3e700e3f53f48851982e1431b8a6647dda0bbfab8129faf32962604cfb2e`.
Claude's `supported-with-limits` review requires the static selection and its
100-symbol operational threshold to remain explicitly non-coverage,
non-membership, non-PIT, and non-adjustment evidence. The manifest therefore
opens only `development_training_eligible` for engineering breadth preparation;
model, GPU, campaign, ranking, holdout, paper, and profitability eligibility
remain false until a separate bounded research contract is verified.

The next single target is a source-separated research-contract preflight. It
must use the completed cohort only as a falsification/mask input, keep provider
prices unmerged, and establish or reject one frozen development-only candidate
contract before any new CPU/GPU model batch. It must retain the static-panel
limitations, use no broker or credential, and produce external-only evidence.
It is research infrastructure and engineering evidence only, not a
strategy-selection, paper, or profit claim.

The Norgate trial's bounded semantic branch remains `unsupported` for
provider/campaign field meaning, and direct historical-universe enumeration is
also `unsupported`. The distinct membership-matrix construction completed at
`D:\market_data\us_equities\norgate_membership\canonical\sp500_current_past\snapshot=2026-07-18-norgate-sp500-membership-r1`.
It records a 541-item candidate union and 266,647 sparse per-symbol/date rows
for 2024-07-18 through 2026-07-17, with matrix SHA-256
`d28060bfa5d81f913edc6d3500a46b7fdbc6bd00c8746e39068894b036758b55` and an
external deletion marker. Claude's construction review was
`supported-with-limits`: the union is a tripwire, sparse absence is not false
membership, and nothing proves publication-time availability. The snapshot is
therefore not a direct historical list, PIT/campaign/model input, or GPU work.

The separate bounded Windows-host-only raw-D1 alignment is now complete at
`D:\market_data\us_equities\fixed_etf_daily\canonical\norgate_raw_d1_alignment\snapshot=2026-07-18-norgate-raw-d1-alignment-r1`.
The requested 2022-11-22 through 2026-06-22 window returned 483 Norgate
sessions per fixed ETF, all from 2024-07-18 onward, while the pinned Tiingo
source has 896 sessions and 413 additional earlier sessions per ETF. It is
`literal_raw_ohlcv_difference`: all-field raw OHLCV equality counts are 96 for
`SPY`, 111 for `QQQ`, and 201 for `IWM`. The snapshot has no Norgate-only
sessions, does not choose a source, and remains PIT/campaign/model/paper
ineligible. Its dataset SHA-256 is
`a283e60cf9a28eb3e1f1a37b35abc575bc99c0e0971a8b226af445888fd6c993`; manifest
SHA-256 is `c37ca34c02df84ebd3f7d684ad87f27c62e36607d8f7ca3751504115205c6a91`.

The bounded Norgate daily-history coverage audit is complete. Across
`2000-01-03` through `2022-07-17`, `2022-07-18` through `2024-07-17`, and
`2024-07-18` through `2026-06-22`, the fixed ETFs returned 0, 0, and 483 rows
per symbol respectively. Fields were stable and no request failed. This matches
the official [Norgate free-trial terms](https://norgatedata.com/freetrial.php)
and [FAQ](https://norgatedata.com/faq.php): US trial daily history is limited to
the last two years. It is an entitlement limit, not a NDU setting to alter. A
paid subscription is the only known longer-history route and remains an
operator approval decision; no action is requested now.

The Tiingo coverage probe is complete: 11 of 12 fixed deterministic requests
were available and one was a recorded HTTP-404, with no selected symbols or raw
rows persisted. The external summary hash is
`sha256:4b2ef16520fdd530ae7cf6bbadc9dbe46cd9526670d859c2484097d3def9fce0`.
The first Claude-reviewed 30-symbol raw-daily pilot is also complete. It
recorded 29 available responses, one unavailable response, 13,724 raw-field
rows, and only 18 common sessions across the available candidates. Dataset
SHA-256 is `ecc5bf5c34ea1606fcea80ade658d4b95964033387149a7c273de7858652af56`;
manifest SHA-256 is
`69493180e553af940810d3a07afe248d77febd2aee5105304dc777985ea7901f`.
The r1-bound disjoint shard also completed after its enforced one-hour pacing
interval: 29 available responses, one unavailable response, 14,529 rows,
dataset SHA-256 `6decf91002aa0029d7cda1cb0b5131d1f440129624c84db2cca0d98579e4ccc1`,
and manifest SHA-256
`76234da1951bccb54d74ab0f07358d138e861331914405cae6b91538f25ddb9e`.
The completed offline audit hash-re-attested both source snapshots and wrote
only aggregate facts at
`D:\thericher-v2\model-artifacts\data-agent\tiingo-daily-coverage-audit\snapshot=2026-07-18-tiingo-daily-coverage-audit-r1\summary.json`,
SHA-256 `e81ed382b9a68b0430a680c2c762a692822370a5a30cc96d21174065da0abb0c`.
R2 has 501 common returned sessions, R1/R2 has 18, and 56 existing candidate
groups fully cover the R2 window. Claude's `supported-with-limits` verdict
therefore supports deferring a third shard for coverage alone; nothing opens
PIT, campaign, model, GPU, or paper eligibility.
