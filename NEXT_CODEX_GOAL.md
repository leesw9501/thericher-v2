# Next Codex Goal

## Objective

Complete `firstrate-source-local-window-preflight-v1`: freeze and run one
target-free, source-local SPY/QQQ feature-window geometry matrix over the
hash-bound FirstRate 1m/5m/10m/1h/3h mechanics. The predeclared windows are
1m: `30, 60, 120, 240`; 5m: `12, 24, 48`; 10m: `6, 12, 24`; 1h: `3, 6, 12`;
3h: `2, 4, 8`. This is not a label, prediction, model, selection, backtest,
PnL, Paper, KIS-equivalence, availability/finality, or live claim.

## Hard Boundaries

- Do not call KIS, read credentials, invoke a broker, submit or alter an order,
  invoke Task Scheduler, start Docker services, train a model, or allocate GPU.
- Reattach only the external FirstRate normalization/timeframe-mechanics
  receipts and their canonical input hashes. Never print raw market rows or
  write market data or generated artifacts into Git.
- A window is eligible only when every in-memory Bar is complete and adjacent
  starts differ by exactly its declared timeframe duration. Do not bridge,
  fill, reindex, infer, or interpret a rejected window as a market/session gap.
- Persist only source-safe geometry: predeclared matrix, input/receipt hashes,
  eligible counts, end-timestamp-set hashes, and categorical limitations under
  `D:\thericher-v2\model-artifacts`. Do not persist features, labels, prices,
  predictions, weights, or resampled rows.

## Required Work

1. Add a compact offline preflight runner and synthetic tests that verify exact
   predeclared window matrix handling, strict per-timeframe continuity, hash
   reattachment, no network/credential path, and source-safe output.
2. Run the actual SPY/QQQ preflight using only existing canonical files and
   write one immutable aggregate manifest. Treat each matrix cell independently;
   do not choose a winner or create a research candidate from its counts.
3. Refresh Data, Engine Research, and orchestration stateboards, `HANDOFF.md`,
   and `RUNBOOK.md`. Keep Research Steward GPU custody free and Execution
   non-promoting.

## Verification

Run focused FirstRate/provider/resampling/preflight tests, the goal-boundary
authority test group, Ruff, credential-free Compose configurations, and
`git diff --check`. Report only source-safe aggregate facts and the external
evidence pointer.
