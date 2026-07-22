# Data Agent

## Working Memory

Own the current KIS-native daily cache and its future reusable loaders.

The local console receives only a sanitized intraday freshness projection. It
does not receive paths, raw rows, manifests, quote values, hashes, credentials,
or account data. The projection reads the historical and prospective-head
indexes independently, so a missing head cache is visible as `not_created`, not
as a failed collection or an authority hold.

- Active job: `kis-paper-private-daily-backfill-v1`
- Authoritative cursor/index:
  `D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`
- Data-bearing KIS daily mappings: `QQQ/NAS`, `SPY/AMS`, `IWM/AMS`
- Last known clean common coverage: 694 completed sessions. QQQ has five
  committed chunks, SPY six, and IWM three plus one validated partial chunk.
  Inspect the index before acting.
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
  `thericher-kis-paper-intraday-head` runs Tuesday through Saturday at 02:35
  KST; its schedule is never evidence that a full session was stored.
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
- `select_complete_kis_paper_private_intraday_sessions` derives a new immutable
  KIS-only `CatalogedBars` identity from an explicit ordered tuple of complete
  regular sessions. It is offline/credential-free and rejects duplicate,
  unordered, closed, early-close, incomplete, or non-KIS inputs.
- `prepare_kis_paper_intraday_feature_input` binds that selected source to one
  hash, ordered dates, and explicit session windows for Research. The Docker
  research mount at `/app/market_data` is the same external D: cache, not Git
  storage, and is accepted only in that named container path.

## Ready Queue

1. Keep the current IWM daily scope at its verified lower boundary: the latest
   authorized bounded retry on 2026-07-22 again returned `daily_response_invalid`
   with zero retained rows. A KIS page contains an internally inconsistent OHLC
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
8. The prospective `intraday-head` root is currently not created. Its installed
   Tuesday-Saturday task is `Ready` for 02:35 KST and uses `--build`. After its
   first run, reattest each QQQ/SPY stream's retained count, observed time, safe
   outcome, and complete-session coverage before handing any head bars to
   Research. The current backfill partial metadata is not a hold on that work.

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

## Recovery

Reattest the index and committed snapshots before a new network call. Recover a
matching orphan snapshot without KIS access. Classify a bad snapshot or index
as `reconcile`; do not overwrite evidence or invent a cursor.

## Next Handoff

Continue KIS-native minute accumulation and preserve the exact provider identity,
timestamp basis, session classification, coverage, and limitations for the next
feature/candidate input. Report only a concrete source-rights or storage
constraint that needs operator action.
