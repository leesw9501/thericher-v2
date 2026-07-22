# Data Agent

## Working Memory

Own the current KIS-native daily cache and its future reusable loaders.

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

## Ready Queue

1. Keep the current IWM daily scope at its verified lower boundary: a KIS page
   contains an internally inconsistent OHLC row, so the strict all-row parser
   rejects it. Do not retry the identical bad page endlessly or silently accept
   its remaining rows; a new anchor, endpoint, or evidence-backed scope may
   proceed independently.
2. Keep `data.kis_paper_daily` aligned with the cache contract: re-attest
   snapshot/index/raw hashes, accept only exact overlap deduplication, reject
   conflicts, verify cursor seams, and return the completed common-session
   intersection for consumers. A bounded `end_session` may re-attest the full
   source while materializing only the permitted prefix as `Bar` objects.
3. Treat 694 sessions as the active daily research input. The former 756 target
   is source-limited and was never KIS Paper permission.
4. Seek a different official KIS historical endpoint only when it can avoid the
   documented IWM row-quality issue without source mixing or hidden repair.
5. Design the next reusable raw-minute cache lane from observed KIS behavior;
   do not resurrect terminal metadata-only probes.

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

## Recovery

Reattest the index and committed snapshots before a new network call. Recover a
matching orphan snapshot without KIS access. Classify a bad snapshot or index
as `reconcile`; do not overwrite evidence or invent a cursor.

## Next Handoff

Build the KIS-native minute-cache contract from observed Paper behavior, then
hand its provider identity, timestamps, session coverage, raw-price limitation,
and exact date range to Engine Research. Report only a concrete source-rights or
storage constraint that needs operator action.
