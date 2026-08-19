# Next Codex Goal

## Objective

Complete `historical-kis-daily-cpu-baseline-reproduction-v1`: reproduce the
existing fixed, source-separated historical KIS D1 CPU/local-paper baseline
once for QQQ and once for SPY using the verified 4,756-bar common panel. This
advances the data-to-backtest-to-local-paper-attribution loop only; it does not
select a model, claim alpha or profitability, qualify a KIS runtime input, or
create Paper/live behavior.

## Boundaries

- Run offline only through `scripts/run_historical_kis_cpu_baseline.py` and the
  existing verified private-D1 catalog. Do not read credentials, call KIS,
  invoke Docker or a scheduler, submit a broker order, or use GPU.
- Use exactly the fixed `QQQ/NAS/MODP=0` and `SPY/AMS/MODP=0` catalog targets,
  `always_long` and `previous_bar_direction` baselines, the fixed 1-bp fee plus
  2-bp slippage assumptions, chronological descriptive holdout, and
  `source: local_paper` fills. Do not tune windows, thresholds, costs, signs,
  splits, or candidates after seeing either result.
- Write contracts, work evidence, and sanitized summaries only beneath
  `D:\thericher-v2\model-artifacts\historical-kis-daily-cpu-baseline` with
  new `20260819-historical-kis-qqq-r1` and
  `20260819-historical-kis-spy-r1` labels. Never output or commit raw rows,
  credentials, account state, or model artifacts.
- A source/hash mismatch, unavailable catalog, non-local-paper fill, missing
  fixed baseline/phase, or write outside the artifact root closes only that
  symbol attempt without retry or model promotion.

## Required Work

1. Reattest the verified two-symbol D1 catalog through its existing offline
   loader, retaining only dataset identity/hash, bar counts, and complete-bar
   facts. Run the focused campaign and runner tests first.
2. Run the two independent fixed CPU baselines with their predeclared labels.
   They may run in parallel only with isolated artifact directories. Capture
   only the runner's sanitized aggregate summaries.
3. Reattach each external contract and summary, verify the fixed two-baseline
   by two-phase cardinality and local-paper fill source, and record only
   aggregate after-cost/replay facts and artifact hashes/pointers.
4. Refresh Data, Engine Research, Execution, Research Steward, orchestration,
   `HANDOFF.md`, and `RUNBOOK.md` with the descriptive-only result. Do not
   allocate GPU or create a candidate queue from either outcome.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- Two hash-bound external contracts and sanitized summaries, each with exactly
  two fixed baselines across development and chronological descriptive holdout.
- Strongest kill test: a catalog/hash mismatch, unexpected target/cost/split,
  output outside the artifact root, a non-`local_paper` fill, or incomplete
  baseline/phase cardinality.
- The result remains descriptive local-paper accounting evidence, never a
  selected model, predictive performance, broker PnL, Paper action, or live
  claim.
