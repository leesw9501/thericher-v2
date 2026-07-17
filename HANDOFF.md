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

- KIS access, credentials, account queries, broker submission, and live mode are
  disabled unless a current goal carries the required operator approval.
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
none was invented. No operator data action is required for the current goal.

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

KIS is disabled, no credentials have been read, and no broker call or order has
been made.

KIS paper is an early execution milestone, not a reward for model
profitability. A later goal should first request operator authority for
read-only paper account access. After buying power is reconciled, Codex proposes
a paper capital envelope based on the smaller of actual orderable paper funds
and intended shadow live capital; the current planning reference is KRW
5,000,000. The operator approves or changes that envelope once. Routine paper
work inside it then continues without repeated approval. Live mode remains a
separate decision.

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

`NEXT_CODEX_GOAL.md` now makes Data lead the unresolved factor sensitivity:
qualify explicit corporate-action and distribution evidence for SPY, QQQ, and
IWM, then replay the existing fixed checkpoints without new training. No
operator help is currently required. Paid data, read-only KIS authority, the
paper capital envelope, and live capital remain future explicit decisions.
