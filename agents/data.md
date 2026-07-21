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
- Stored data is `MODP=0_unadjusted`. Treat corporate actions and adjustment
  semantics as a visible limitation, not a reason to stop collection.

## Ready Queue

1. Keep IWM daily backfill stopped at its current lower boundary: a KIS page
   contains an internally inconsistent OHLC row, so the strict all-row parser
   rejects it. Do not retry it endlessly or silently accept the remaining rows.
2. Keep `data.kis_paper_daily` aligned with the cache contract: re-attest
   snapshot/index/raw hashes, accept only exact overlap deduplication, reject
   conflicts, verify cursor seams, and return the completed common-session
   intersection.
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
- A hash-attested partial chunk may advance only after a fully validated first
  page; a wholly invalid page never advances its cursor.

## Recovery

Reattest the index and committed snapshots before a new network call. Recover a
matching orphan snapshot without KIS access. Classify a bad snapshot or index
as `reconcile`; do not overwrite evidence or invent a cursor.

## Next Handoff

Hand the loader's dataset identity, shared-session count, raw-price limitation,
and exact date range to Engine Research. Report only a concrete missing data
source or storage constraint that needs operator action.
