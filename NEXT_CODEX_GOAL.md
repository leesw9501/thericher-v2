# Next Codex Goal

## Objective

Complete `kis-daily-l2-logistic-control-reproduction-v1`: run the existing
frozen CPU L2 logistic control once against the hash-pinned QQQ/SPY historical
KIS D1 sequence input and replay its frozen validation alongside fixed
local-paper comparators. This advances one classical-ML research path only; it
does not select a winner, claim profitability, qualify a KIS runtime input, or
create Paper/live behavior.

## Boundaries

- Run offline only through `scripts/run_kis_daily_l2_logistic_control.py` and
  the existing expected-hash private-D1 loader. Do not read credentials, call
  KIS, invoke Docker or a scheduler, submit a broker order, or use GPU.
- Use exactly the frozen QQQ/SPY pair, sequence geometry, development-only fit,
  160-step L2 logistic specification, threshold, chronological validation,
  and fixed local-paper comparators in the checked-in control. Do not tune,
  retrain, reuse validation labels for fitting, select a winner, or form an
  ensemble after seeing the result.
- Use the new external label `20260819-kis-daily-l2-logistic-r1` beneath
  `D:\thericher-v2\model-artifacts\kis-daily-l2-logistic-control-v1`. Model
  parameters may exist only there; never output or commit raw rows,
  credentials, account state, or model parameters.
- A source/hash mismatch, unavailable input, non-local-paper fill, missing
  model/comparator cardinality, incomplete precommit, or output outside the
  artifact root closes this one run without retry or model promotion.

## Required Work

1. Reattest the expected two-symbol D1 catalog through its existing offline
   loader, retaining only identity/hash, count, and complete-bar facts. Run the
   focused control and runner tests first.
2. Run exactly one fixed L2 control with the predeclared label and capture only
   its sanitized aggregate summary.
3. Reattach the external precommit, summary, and model hashes without reading
   model parameters. Verify two model replay cells, six fixed comparator cells,
   development-only fitting, validation labels excluded from fitting, and
   `local_paper` fill sources.
4. Refresh Data, Engine Research, Execution, Research Steward, orchestration,
   `HANDOFF.md`, and `RUNBOOK.md` with the descriptive-only result. Do not
   allocate GPU or create a candidate queue from the outcome.
5. Run required verification, commit, push, replace this file with exactly one
   material next company objective, and continue.

## Completion Evidence

- One hash-bound external precommit, model hash, and sanitized summary with two
  model validation replays plus six fixed comparator cells.
- Strongest kill test: a catalog/hash mismatch, precommit after fit, validation
  labels used for fitting, output outside the artifact root, a non-`local_paper`
  fill, or incomplete model/comparator cardinality.
- The result remains descriptive classical-ML control evidence, never a
  selected model, predictive performance, broker PnL, Paper action, or live
  claim.
