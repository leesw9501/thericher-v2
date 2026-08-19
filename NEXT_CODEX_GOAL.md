# Next Codex Goal

## Objective

Complete `kis-daily-regime-tree-breadth-reproduction-v1`: reproduce one
existing frozen shallow histogram-gradient-tree control against the same
hash-pinned QQQ/SPY historical KIS D1 sequence input, then replay its frozen
validation with the fixed local-paper comparators. This tests a distinct
nonlinear bias after the failed L2 control; it does not select a winner, claim
profitability, qualify a KIS runtime input, or create Paper/live behavior.

## Boundaries

- Run offline only through `scripts/run_kis_daily_regime_tree_breadth.py` and
  the existing expected-hash private-D1 loader. Do not read credentials, call
  KIS, invoke Docker or a scheduler, submit a broker order, or use GPU.
- Use exactly the frozen QQQ/SPY pair, 20-bar sequence geometry,
  development-only fit, 96-iteration shallow histogram-gradient-tree
  specification, threshold, chronological validation, and fixed three-way
  local-paper comparators in the checked-in control. Do not tune, retrain,
  reuse validation labels for fitting, select a winner, or form an ensemble
  after seeing the result.
- Use exactly the new external label `20260819-kis-daily-regime-tree-r1` under
  `D:\thericher-v2\model-artifacts\kis-daily-regime-tree-breadth-v1`.
  It may retain deterministic local-paper replay work evidence only beneath
  that external root; never output or commit raw market rows, credentials,
  real-account state, fitted estimators, or model parameters.
- A source/hash mismatch, unavailable input, non-`local_paper` fill, missing
  model/comparator cardinality, incomplete precommit, serialized estimator, or
  output outside the artifact root closes this one run without retry or model
  promotion.

## Required Work

1. Reattest the expected two-symbol D1 catalog through its existing offline
   loader, retaining only identity/hash, count, and complete-bar facts. Run the
   focused regime-tree and daily-loader tests first.
2. Run exactly one fixed regime-tree control with the predeclared label and
   capture only its sanitized aggregate summary.
3. Reattach the external precommit and summary hashes. Verify two model replay
   cells, six fixed comparator cells, development-only fitting, validation
   labels excluded from fitting, no serialized estimator, and `local_paper`
   fill sources.
4. Refresh Data, Engine Research, Execution, Research Steward, orchestration,
   `HANDOFF.md`, and `RUNBOOK.md` with the descriptive-only result. Do not
   allocate GPU or create a candidate queue from the outcome.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One hash-bound external precommit and sanitized summary with two model
  validation replays plus six fixed comparator cells, with no serialized fitted
  estimator.
- Strongest kill test: a catalog/hash mismatch, precommit after fit, validation
  labels used for fitting, output outside the artifact root, a non-`local_paper`
  fill, serialized estimator, or incomplete model/comparator cardinality.
- Economic falsification: unless both QQQ and SPY after-cost model replays
  strictly exceed their fixed `previous_bar_direction` comparator, close this
  tree lineage as no-follow-up. A two-symbol improvement still permits no
  selection, promotion, ensemble, GPU allocation, or Paper behavior; obtain a
  Claude falsification-first review before relying on that narrow result.
- The result remains descriptive nonlinear-control evidence, never a selected
  model, predictive-performance claim, broker PnL, Paper action, or live claim.
