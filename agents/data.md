# Data Agent Stateboard

`AGENTS.md` owns policy and `NEXT_CODEX_GOAL.md` owns the company objective.
This is the Data lane's current projection, not a historical ledger. Git,
`HANDOFF.md`, `DECISIONS.md`, `D:\market_data`, and the external artifact ledger
retain detailed history and raw evidence.

## Ownership

Own market-data correctness, provider behavior, provenance, canonical storage,
calendar/session selection, resampling, dataset manifests, and temporal input
boundaries. Do not select strategies, promote models, or make execution
decisions.

## Current Objective

Accumulate the prospective `QQQ/NAS/1m` head cache through the existing single
scheduled collector until five exact 390-minute regular sessions exist. The
collector owns the post-durable metadata-only preparation attempt; do not create
a second scheduler or manually duplicate a due collection.

## Current Facts

- The safe head baseline is index generation `8`, metadata identity
  `sha256:9d8e88209293f3aeabd48311d705c4e1a7e9a325b8726ea0d878a01ec8d1949c`,
  four retained chunks, and `0 / 5` complete QQQ regular sessions.
- Candidate completeness is `239 / 390` on 2026-07-22, `39 / 390` on
  2026-07-23, and `238 / 390` on 2026-07-24. Continuation is `mixed`; exact
  and conflicting overlap are both `none`; the scoped last reason is
  `minute_duplicate_conflict`.
- `thericher-kis-paper-intraday-head` is `Ready`, has KST triggers at `00:35`,
  `02:35`, `04:35`, and `06:20`, has no missed run, and next runs at
  2026-07-28 00:35 KST. It retains one Docker service, the four-page-per-target
  cap, source pacing, strict conflict rejection, and exact session selection.
- A source-safe static and synthetic review confirms that
  `minute_duplicate_conflict` can describe a rejected candidate page as well as
  a retained-row collision. The current short-session metadata therefore does
  not identify a local cursor, cap, or conflict-rule defect; retain the current
  collector contract until a new source or test fact identifies one exact change.
- Daily KIS caches remain source-separated. `QQQ/NAS` and `SPY/AMS` are complete
  at their established historical boundaries; `IWM/AMS` remains `source_limited`
  at its qualified bad-row boundary. Do not repair, mix, or silently extend a
  source-limited target.
- The data-only daily backfill task completed at 07:00 KST on 2026-07-25 with
  task result `0`. Its current index is generation `65`; QQQ and SPY remain
  complete while IWM retains the same scoped `daily_response_invalid` limit.
- All KIS market-data workers share the measured request-start and token-start
  controls under `D:\market_data`. These controls are transport facts, not
  permission or scheduler latches.

## Binding Contracts

- A usable prospective session is exactly one declared regular US session with
  all 390 completed minutes. Short, gapped, conflicting, or unqualified
  timestamp data never reaches Research.
- Write and hash a data-bearing snapshot before advancing its cursor. Accept
  only exact overlap deduplication and reject conflicting prior rows.
- Preserve provider identity and unknown source semantics. Do not fill,
  relabel, or repair minute rows from another source.
- A future `minute_duplicate_conflict` records only the closed safe origin
  `candidate_batch` or `retained_cache`; a legacy missing field is
  `not_recorded`. This is recovery diagnosis only and never changes session
  selection, preparation status, pacing, or scheduler behavior.
- The head-index SHA-256 is exact persisted-byte preparation provenance; do not
  hash decoded text because newline translation can change a valid record.
  Offline verification instead binds the frozen first-five QQQ dates and their
  selected-row fingerprint digest, so later append-only or independent-SPY
  metadata updates do not invalidate the usable pair.
- The automatic preparer is metadata-only and isolated after durable collection.
  It cannot alter cache bytes, cursors, or collector freshness facts. Its first
  usable pair binds exactly the first five selected session dates and row
  fingerprints.
- Preparation depends on the exact QQQ target result, not the independent SPY
  outcome: one QQQ `collected` or `recovered` result may run the QQQ-only
  preparer while a scoped SPY failure keeps the overall collection result
  `incomplete`. The preparer still validates the full expected index shape.
- The collector preserves safe JSON/freshness behavior while returning a
  nonzero process result for outer worker failures and `locked`, `partial`, or
  `rejected` collection outcomes. Existing Task Scheduler state therefore
  exposes that exact failed run without a second worker or retry latch.

## Ready Queue

1. After the next scheduled result, compare metadata-only coverage with the
   generation-8 baseline: complete counts, missing offset ranges,
   continuation/overlap/conflict categories, last reason, and preparation state.
2. If exactly five complete sessions first exist, let the existing collector
   produce its first-five-bound preparation pair and hand only that verified
   pair to Engine Research.
3. If coverage remains short, retain the collector contract unless one bounded
   source observation or synthetic test identifies an exact recovery change.
   Do not infer a page, timestamp, cap, or duplicate defect from varied gaps.

## Operator Help

None. Escalate only a paid source, unclear rights, an applicable retention
restriction, or a storage-floor conflict that changes the approved data scope.

## Recovery

Current class: `resume`. Reattest index and committed snapshots before a new
network call. Recover a matching orphan snapshot without KIS access; classify a
bad snapshot or index as `reconcile` without overwriting evidence or inventing a
cursor. A pending preparation pair is ordinary source evidence, not a scheduler,
Research, or Paper permission hold.

## Evidence

- `scripts\inspect_kis_intraday_head_coverage.py` is the safe read-only
  coverage inspector.
- The scheduled worker owns the prospective head cache under `D:\market_data`.
  The external artifact root holds only its preparation pair and sanitized
  downstream receipts.

## Next Handoff

Consume the next due head outcome through the safe inspector. Hand off only a
verified first-five pair; otherwise keep this lane in `resume` and continue the
installed cadence without a foreground wait or duplicate worker.
