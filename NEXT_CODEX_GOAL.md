# Next Codex Goal

## Objective

Complete `firstrate-source-local-normalization-v1`: normalize the two
hash-bound FirstRate free SPY/QQQ 1-minute archives under `D:\market_data`
into canonical local `Bar` CSVs while preserving each decoded source timestamp
set exactly. This is source-isolated retrospective Data mechanics only, never a
KIS-equivalence, availability/finality, strategy, model, PnL, Paper, or live
claim.

## Hard Boundaries

- Do not call KIS, read credentials, invoke a broker, submit or alter an order,
  invoke Task Scheduler, or start Docker services.
- Do not read or route `KIS_LIVE_*`, print raw market rows, write market data or
  generated artifacts into Git, or change the alternate IWM collector WIP.
- Process only the staged original ZIPs identified by the existing FirstRate
  acquisition receipt. Recompute their expected archive hashes before decode;
  reject an unexpected member, header, timestamp, ordering, DST ambiguity,
  unsafe path, or compression expansion rather than improvising a repair.
- Do not reindex, fill, impute, synthesize, aggregate, or infer a missing bar.
  A zero-volume omission remains `not_present_in_source`, never a session gap
  or continuity claim.
- Keep outputs under `D:\market_data` and source-safe receipts under
  `D:\thericher-v2\model-artifacts`; do not create a KIS/Paper/model consumer.

## Required Work

1. Integrate and review the offline normalizer using only synthetic-fixture
   tests, including exact expected archive-entry names and Windows reparse-point
   rejection.
2. Reattach the two staged archive hashes and normalize SPY and QQQ into
   source-local canonical CSVs. Validate each emitted timestamp-set hash equals
   the decoded source timestamp-set hash.
3. Write one source-safe external normalization receipt with archive/output
   hashes, canonical relative paths, expected entry names, bar counts,
   timestamp-set hashes, and categorical validation results. Never retain or
   print raw rows in the receipt or Git.
4. Refresh Data and orchestration stateboards, `HANDOFF.md`, and `RUNBOOK.md`.
   Keep Engine Research and Execution non-promoting; a later campaign needs a
   distinct frozen contract and independently qualified input.

## Verification

Run focused normalizer/provider tests, the goal-boundary authority test group,
Ruff, credential-free Compose configurations, and `git diff --check`. Report
only source-safe archive/output facts and the external evidence pointer.
