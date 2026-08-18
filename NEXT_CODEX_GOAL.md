# Next Codex Goal

## Objective

Complete `firstrate-source-local-timeframe-mechanics-v1`: consume the two
hash-bound canonical FirstRate SPY/QQQ M1 CSVs through the existing local
provider and resampler, then retain a source-safe aggregate manifest for 1m,
5m, 10m, 1h, and 3h geometry. This is source-isolated retrospective mechanics
only, never a KIS-equivalence, availability/finality, strategy, model, PnL,
Paper, or live claim.

## Hard Boundaries

- Do not call KIS, read credentials, invoke a broker, submit or alter an order,
  invoke Task Scheduler, or start Docker services.
- Reattach only the external FirstRate normalization receipt and its two
  canonical CSV hashes. Never print raw market rows or write market data or
  generated artifacts into Git.
- Do not add, infer, reindex, fill, or synthesize a source minute or a target
  bucket. A missing source minute remains `not_present_in_source`, never a
  session-gap, continuity, finality, or availability claim.
- Retain resampled Bars only in process for the aggregate validation. Store
  only hashes, counts, ordering/completion categories, and relative paths under
  `D:\thericher-v2\model-artifacts`; do not create a model or Paper consumer.

## Required Work

1. Add a small offline runner and focused synthetic tests that reattest the
   canonical input hashes from the normalization receipt, read them through
   `LocalCsvBarProvider`, and exercise existing resampling at all five required
   timeframes.
2. Validate source-safe invariants for every symbol/timeframe: canonical input
   hash match, strictly ordered unique timestamps, all emitted Bars complete,
   and no output timestamp set attributed to a filled or inferred bucket.
3. Run the bounded actual-data mechanics job and write one external aggregate
   manifest with input/output hashes, counts, timestamp-set hashes, and the
   exact non-promoting limitations.
4. Refresh Data and orchestration stateboards, `HANDOFF.md`, and `RUNBOOK.md`.
   Keep Engine Research and Execution non-promoting.

## Verification

Run focused provider/resampling tests, the goal-boundary authority test group,
Ruff, credential-free Compose configurations, and `git diff --check`. Report
only source-safe aggregate facts and the external evidence pointer.
