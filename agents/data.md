# Data Agent

## Working Memory

Own the current KIS-native daily cache and its future reusable loaders.

- Active job: `kis-paper-private-daily-backfill-v1`
- Authoritative cursor/index:
  `D:\market_data\us_equities\kis_paper_private\daily\backfill-v1\index.json`
- Data-bearing KIS daily mappings: `QQQ/NAS`, `SPY/AMS`, `IWM/AMS`
- Last known coverage: QQQ two chunks, SPY two chunks, IWM one chunk; 199
  common completed sessions. Inspect the index before acting.
- Stored data is `MODP=0_unadjusted`. Treat corporate actions and adjustment
  semantics as a visible limitation, not a reason to stop collection.

## Ready Queue

1. Continue one paced two-page daily backfill chunk per worker invocation.
2. Build a strict cache loader that re-attests snapshot and manifest hashes,
   accepts only exact overlap deduplication, rejects conflicts, and returns the
   completed common-session intersection.
3. Continue until three ETFs share 756 completed sessions or the endpoint has
   a documented source exhaustion. This threshold is for daily research quality,
   not KIS Paper permission.
4. Design the next reusable raw-minute cache lane from observed KIS behavior;
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

## Recovery

Reattest the index and committed snapshots before a new network call. Recover a
matching orphan snapshot without KIS access. Classify a bad snapshot or index
as `reconcile`; do not overwrite evidence or invent a cursor.

## Next Handoff

Hand the loader's dataset identity, shared-session count, raw-price limitation,
and exact date range to Engine Research. Report only a concrete missing data
source or storage constraint that needs operator action.
