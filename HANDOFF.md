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

## Current Boundaries

- KIS remains failed closed. The current Data goal reads no `.env`, makes no KIS
  API call, and accesses no account. Any later KIS re-probe needs non-secret
  pairing confirmation and separate one-time authority. Order submit/cancel,
  paper capital, `KIS_LIVE_*`, live behavior, and mode changes remain disabled.
- Existing broker-free fills keep `source: local_paper`.
- Market data stays under `D:\market_data`.
- Generated model and run artifacts stay under
  `D:\thericher-v2\model-artifacts`; Docker uses `/app/model_artifacts`.
- Do not download data or model artifacts into the Git workspace.
- Free, no-auth, lawful, license-compatible data may be acquired autonomously
  when it directly improves active work. Paid or login/manual-license sources
  require operator approval.
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

`NEXT_CODEX_GOAL.md` now consumes the verified Tiingo raw-D1 input in one
frozen local-paper source-sensitivity replay of the fixed ETF campaign. KIS
remains failed closed pending the non-secret pairing check and a separately
authorized future probe. The KIS capital envelope, paid data, order submission,
and live capital remain separate future decisions.
