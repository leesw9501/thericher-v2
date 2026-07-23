# Data Agent

## Working Memory

Own the current KIS-native daily cache, prospective intraday-head observations,
and their future reusable loaders.

All private non-live data collection and retention under the current source and
disk policy is standing-authorized. A `raw_market_data_retained: false` or
historical one-shot observation remains a no-bytes fact for that observation,
not a cache, schedule, or KIS Paper permission latch. It is never a fixed
state that needs clearing before a fresh collection or another ready lane.

The local console receives only a sanitized intraday freshness projection. It
does not receive paths, raw rows, manifests, quote values, hashes, credentials,
or account data. The projection reads the historical and prospective-head
indexes independently, so a missing head cache is visible as `not_created`, not
as a failed collection or an authority hold.

- Active job: `kis-paper-private-daily-backfill-v1`
- Authoritative cursor/index:
  `D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`
- Data-bearing KIS daily mappings: `QQQ/NAS`, `SPY/AMS`, `IWM/AMS`
- The forward-only daily SPY head is at
  `D:\market_data\us_equities\kis_paper_private\daily-head\v1\index.json`.
  Its first verified generation holds 99 `SPY/AMS` prior completed sessions
  through 2026-07-21 and never retains the current US exchange date. The head
  is a distinct immutable source, not a row-level patch over the historical
  cache. The later Paper entry/exit lifecycle consumes only its hash-attested
  bars and first-local-availability semantics; it cannot turn this data source
   into a price, account, position, fill, or PnL assertion.
   `thericher-kis-paper-daily-spy-head` collects it at 22:15 KST Tuesday through
   Saturday.
- `thericher-kis-paper-daily-backfill` runs one data-only Docker chunk at
  07:00 KST Tuesday through Saturday. It mounts only `D:\market_data` and
  carries only KIS Paper market-data credentials, so it cannot access an
  account, submit an order, or read model artifacts.
- Last known clean common coverage: 694 completed sessions. QQQ now has six
  retained usable chunks plus one historical no-bytes observation, SPY six,
  and IWM three plus one validated partial chunk. IWM's unchanged 2023-10-10
  cursor is `source_limited`; inspect the index before acting.
- The latest offline re-attestation matched all 15 eligible manifest digests
  and fixed the common panel to 2023-10-10 through 2026-07-17. Its index hash
  is `sha256:343691f6ff814b0d1d0c046782fd5af26d9225f4bada021e2a7820c205ed5408`.
- Stored data is `MODP=0_unadjusted`. Treat corporate actions and adjustment
  semantics as a visible limitation, not a reason to stop collection.
- A separate Norgate trial snapshot is available at
  `D:\market_data\us_equities\norgate_trial_broad_development_panel\canonical\ohlcv_1d\snapshot=2026-07-18-norgate-trial-broad-d1-panel-r1`.
  It contains 523 symbols x 483 common D1 sessions from `2024-07-18` through
  `2026-06-22`, but is static/survivorship selected with unverified adjustment
  semantics. Its manifest permits development-training preparation only;
  `model`, `gpu`, `paper_trading`, `ranking`, and PIT scope remain false, and
  the source makes no PnL claim.
- The first KIS-native intraday cache is at
  `D:\market_data\us_equities\kis_paper_private\intraday\v1\index.json`.
  Its initial bounded cycle retained two source pages each for `QQQ/NAS` and
  `SPY/AMS`: 239 exact-deduplicated 1m rows per stream, with one page-boundary
  overlap per symbol. `data.kis_paper_intraday` verifies snapshot/index hashes
  and maps KIS's explicit Korea date/time fields to UTC without inferring an
  exchange DST calendar.
- The observed first ranges are extended-session evidence, not regular-session
  qualification: QQQ spans 20:01 through 23:59 UTC and SPY spans 19:58 through
  23:59 UTC on 2026-07-21. Both canonical loaders returned 239 complete bars
  under the conservative collection-time rule. Holiday, early-close, exchange
  timestamp open/close, and regular-session classification remain unqualified.
- A Docker-profiled continuation cycle and one further bounded chunk now give
  718 unique 1m bars per stream under the latest offline reattestation: QQQ
  spans 12:02 through 23:59 UTC and SPY 11:59 through 23:59 UTC on 2026-07-21.
  The index is authoritative for the next cursor and current coverage.
- The separate `intraday-head` root receives fresh source-page observations
  without advancing the historical backfill cursor. The Windows Scheduled Task
  `thericher-kis-paper-intraday-head` runs Tuesday through Saturday at 06:20
  KST with four pages per target; its schedule is never evidence that a full
  session was stored.
- `data.kis_paper_intraday_index_metadata` is the shared, metadata-only v1
  cache contract for the writer and prospective observer. It validates index
  structure and retained-chunk lineage without opening raw files; the existing
  offline loader remains responsible for raw-byte attestation.
- `us_equity_2026_session` supplies explicit 2026 regular and early-close UTC
  windows from published Nasdaq/NYSE calendars. The first QQQ regular-session
  slice for 2026-07-21 contained 390 complete 1m bars. This qualifies a bounded
  cache/replay baseline only; it does not settle KIS field open/close semantics
  or create a multi-session research dataset.
- The cursor cache now reattests 21 complete regular sessions for both QQQ/NAS
  and SPY/AMS, from 2026-06-22 through 2026-07-21. The first Engine input used
  the latest 20 QQQ sessions, 2026-06-23 through 2026-07-21, with 2026-07-08
  retained as an unused purge session. This is a hash-bound descriptive input,
  not a source-semantic or model-quality conclusion.
- A local credential-free verifier reselected those exact 20 QQQ sessions on
  2026-07-22: 7,800 complete 1m bars with dataset hash
  `sha256:38ccc55e1ade26a11562ebedcb482ace718ccbdb7d4d0cdc78a7d11f874a1c0a`.
  This reattests the frozen research input; it does not alter the cache or make
  a regular-session semantic claim.
- The receipt writer reattested that same frozen input on 2026-07-22 and wrote
  only its safe hash-bound receipt outside Git. The current observed capability
  remains unqualified for the fixed 90-bar baseline, so no raw row was exposed
  and no KIS/order action followed. This data fact does not pause the cache,
  scheduler, canary, or another candidate input.
- `select_complete_kis_paper_private_intraday_sessions` derives a new immutable
  KIS-only `CatalogedBars` identity from an explicit ordered tuple of complete
  regular sessions. It is offline/credential-free and rejects duplicate,
  unordered, closed, early-close, incomplete, or non-KIS inputs.
- `prepare_kis_paper_intraday_feature_input` binds that selected source to one
  hash, ordered dates, and explicit session windows for Research. The Docker
  research mount at `/app/market_data` is the same external D: cache, not Git
  storage, and is accepted only in that named container path.
- The 2026-07-23 Data Agent metadata-only inspection found the prospective
  `intraday-head/v1` index available and structurally readable. The local
  preparer returned `pending`, with zero complete QQQ regular sessions out of
  five required and no artifact writes. Its metadata hash was
  `sha256:a9d8361b96dd92cae918c69202fdb1dc1ed2861a4050b5964041be407ff00f43`.
  This inspection did not read credentials, raw rows, account data, canary
  state, or broker evidence, and made no network call.
- Windows task metadata on 2026-07-23 showed
  `thericher-kis-paper-intraday-head` as `Ready`, with its historical 02:35
  KST run returning task result `0`. After the post-close coverage correction,
  its next run is 2026-07-24 06:20 KST with four pages per target. The separate
  `thericher-kis-paper-quote-session` task was also `Ready`, with task result
  `0`; its execution semantics belong to Execution, not Data.
- A bounded metadata-only inventory on 2026-07-23 reattested the active
  source choices without opening any raw rows. The KIS daily index has QQQ/NAS
  and SPY/AMS `ready` through 2026-07-17; IWM/AMS is `source_limited` at its
  unchanged `daily_response_invalid` cursor. The last verified common D1 panel
  remains 694 sessions from 2023-10-10 through 2026-07-17. The historical KIS
  1m index has QQQ/NAS and SPY/AMS only, each with 21 complete regular sessions from
  2026-06-22 through 2026-07-21; IWM has no KIS 1m stream. The independent
  head index has one QQQ and one SPY chunk but zero of five complete QQQ
  regular sessions, so it is unavailable as a current input. For the active
  fixed baseline receipt, use the existing frozen QQQ/NAS 1m KIS-only 20
  session tuple (2026-06-23 through 2026-07-21), not a daily/head/SPY/IWM
  join. It supports offline replay only, not a current-market claim.

## Ready Queue

1. Keep the current IWM daily scope at its verified lower boundary. The
   2026-07-23 bounded retry confirmed the fourth exact zero-row
   `daily_response_invalid` result at its unchanged cursor, and the index now
   marks only that target `source_limited`; QQQ immediately continued with a
   committed 199-row chunk. A KIS page contains an internally inconsistent OHLC
   row, so the strict all-row parser rejects it. Do not retry the identical bad
   page endlessly or silently accept its remaining rows; a new anchor, endpoint,
   or evidence-backed scope may proceed independently.
2. Keep `data.kis_paper_daily` aligned with the cache contract: re-attest
   snapshot/index/raw hashes, accept only exact overlap deduplication, reject
   conflicts, verify cursor seams, and return the completed common-session
   intersection for consumers. A bounded `end_session` may re-attest the full
   source while materializing only the permitted prefix as `Bar` objects.
3. Treat 694 sessions as the active daily research input. The former 756 target
   is source-limited and was never KIS Paper permission.
4. Seek a different official KIS historical endpoint only when it can avoid the
   documented IWM row-quality issue without source mixing or hidden repair.
5. Continue the KIS-native minute cache from its persisted cursor at useful
   regular-session observations. Collect fresh data rather than reviving
   terminal metadata-only probes; an old failed or unretained result cannot
   disable this work.
6. Keep the head cache accumulating prospective sessions while preserving its
   independent root and safe coverage evidence. Reattest any candidate complete
   session before handing it to Engine Research.
7. Preserve raw provider rows and label unknown KIS field semantics; do not
   repair, fill, or relabel a session from another provider.
8. The first due `intraday-head` task completed at 2026-07-23 02:35 KST. Its
   independent v1 index is generation 2 with one committed retained chunk for
   each QQQ/NAS and SPY/AMS stream, and the console freshness projection is
   current. The metadata-only prospective preparation remains `pending` with
   zero complete QQQ sessions and five still required; it wrote no artifact.
   The next task remains `Ready` and this factual pending result is not a hold
   on collection, Paper work, or another data candidate.
9. The current head-bar contract is not yet an execution-price contract: it
   has no verified tick/decimal-scale field, no proven `NAS` to `NASD` order
   mapping, unqualified provider timestamp edge semantics, and no latest-bar
   freshness predicate. Keep those gaps visible while continuing Data work;
   they do not disable the head cache, KIS Paper, or an independently verified
   price source.
10. Resume the independent prospective-head accumulation on its normal
    scheduler cadence. The current metadata-only preparation has zero of five
    required complete QQQ sessions, so it has no research handoff yet; this is
    ordinary evidence accumulation, not a permission or scheduling latch.
    The first 02:35 KST head proved that two pages ended at US mid-session, so
    the installed task now runs at 06:20 KST with four pages per target. Its
    next run must be reattested for one exact 390-minute QQQ regular session;
    a short, duplicate, or source-delayed result is a scoped source fact, not
    a Paper or Research hold.

## Authority And Boundaries

KIS Paper market-data access, private raw retention, and goal-owned scheduling
are standing-authorized. Retain raw snapshots under `D:\market_data`, never
Git. Do not read `KIS_LIVE_*`, publish or redistribute source data, buy data,
or accept unclear rights. Warn at 20% free disk and do not begin new large work
that would cross the 15% floor.

## Durable Knowledge

- A successful data-bearing snapshot is written and hashed before its index
  cursor advances.
- Exact boundary overlap is normal; different values for the same date are a
  conflict and must defer that target for reconciliation.
- Source-adaptive pacing is a transport fact. It must not be described as an
  approval, capital, or model gate.
- A raw-retention field records what was actually stored for one result. It is
  not a collection permission switch.
- A failed, empty, or unretained job is a recovery fact for that job only; it
  must not create a one-shot latch for later correctly scoped collection.
- The standing forward-progress directive applies equally to cache evidence:
  a missing or unqualified input may request fresh data or yield a scoped
  unavailable result, but cannot act as Paper, scheduler, or research authority.
- The intraday collector and offline loader ignore an unretained historical
  marker without a cache snapshot before validation, deduplication, cursor
  handling, or bar consumption.
- When ordinary retry pacing has elapsed, the next correctly scoped collection
  proceeds without an operator question even if an older result retained no
  raw bytes.
- `slice_kis_paper_private_daily_catalog` creates a derived, hash-bound session
  range without reopening the source cache. Research uses it to keep phase
  consumers away from excluded sessions.
- The optional loader session ceiling still verifies every retained raw file,
  complete row-fingerprint map, and committed row count. It merely omits later
  `Bar` construction, so a frozen consumer cannot accidentally carry a burned
  suffix into its process.
- `load_verified_norgate_trial_development_panel_catalog` exposes the existing
  static Norgate trial snapshot as immutable per-symbol D1 `CatalogedBars` with
  original candidate ranks, exact source scope, lineage identity, and
  limitations. It validates and parses the same hash-attested panel bytes; it
  neither imports the Norgate SDK nor writes artifacts/data. Its actual local
  smoke found 523 symbols, 483 sessions, 252,609 bars, and rank range 1..541.
- A hash-attested partial chunk may advance only after a fully validated first
  page; a wholly invalid page never advances its cursor.
- KIS execution canary evidence and KIS market-data cache bytes are separate:
  a canary does not duplicate raw broker payloads into `D:\market_data`.
- The existing Tiingo IEX 5m SPY/QQQ/IWM snapshot covers 129 sessions but is
  descriptive replay evidence only. Its manifest prohibits training, campaign,
  paper-trading, and ranking use, so it must not become an intraday signal
  input; build the KIS-native minute cache for that loop instead.
- KIS minute pagination resumes with `NEXT=1` plus a 14-digit `KEYB` derived
  from the oldest retained exchange timestamp. The first actual QQQ and SPY
  page pairs each had one exact boundary overlap; conflicts reject cursor
  advance rather than silently replacing a cached minute.
- The intraday loader uses the explicit KIS Korea fields (`kymd`/`khms`) as its
  UTC basis. It labels a bar incomplete when its end is later than the rounded
  collection minute, so an in-flight minute cannot become a completed feature.
- The 2026 session adapter gives only the exchange calendar window. It does not
  assert whether a KIS minute's timestamp is its open, close, or vendor stamp.
- The first immutable v1 snapshots predate the explicit
  `canonical_start_policy` field. `data.kis_paper_intraday` accepts only their
  exact equivalent completed-bar-rule spelling; it never rewrites source bytes
  or relaxes the timestamp contract for another form.
- Session selection does not join overnight gaps. It preserves them as explicit
  ordered session boundaries for a Research consumer to validate, while any
  missing minute inside a selected session remains invalid input.
- KIS Paper's current same-day `inquire-ccnl` use is a narrow order-ID history
  fact only. It can say that one raw ID was seen in its current ET query, but
  its present parser does not establish a fill, cancellation, price, quantity,
  realized PnL, or receipt-attributed aggregate position. Those raw facts stay
  private and out of `D:\market_data`.
- The official virtual `VTTS3035R` sample documents per-row quantity, fill
  price/amount, processing-status, revision/cancel, and order-time field names,
  but not terminal enum, amendment ordering, or net-PnL semantics. The first
  post-validation probe found that the legacy cancelled SPY/AMEX state lacked a
  durable acknowledged submission time, so it emitted
  `submission_time_missing` without a KIS call. New states persist that time
  write-once. This is source-contract evidence only; it does not change
  collection, retention, scheduling, or Paper authority.
- The daily session handoff needs only the opaque receipt digest, its matching
  `receipt-<digest>` run ID, and safe timestamps/provenance. After that exact
  check, the same state may contribute the terminal probe's categorical
  field-presence payload and an opaque artifact-content hash. Raw daily bars,
  prices, account values, and order IDs never cross either boundary.

## Recovery

Current recovery class: `resume`. The historical QQQ/NAS 1m baseline input is
intact. The prospective-head index is readable but has zero of five required
complete QQQ sessions, so it is pending only as a future current-input source.
The historical QQQ cursor's `minute_cursor_invalid` is scoped to its next
collection recovery and does not invalidate already verified sessions or pause
the fixed receipt. Resume the next scheduled collection normally. Reattest the
index and committed snapshots before a new network call. Recover a matching
orphan snapshot without KIS access. Classify a bad snapshot or index as
`reconcile`; do not overwrite evidence or invent a cursor.

## Next Handoff

The exact-order source probe now confirms that the present documented KIS
history contract remains insufficient for terminal/PnL interpretation. Continue
KIS-native minute accumulation and preserve provider identity, timestamp basis,
session classification, coverage, and limitations. Re-run the metadata-only
prospective preparer after future head collections; report only a concrete
source-rights or storage constraint that needs operator action.
