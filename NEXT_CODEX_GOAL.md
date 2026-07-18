# Next Codex Goal

## Objective

Run two non-conflicting lanes in parallel:

- qualify Tiingo EOD distribution and split evidence for `SPY`, `QQQ`, and
  `IWM`, then run the frozen 36-cell explicit-event replay if accepted;
- establish the first read-only KIS paper account snapshot and reconciliation
  without submitting, cancelling, or modifying an order.

This advances data collection, feature/model validation, and paper-trading
readiness.

## Approved Authority

- Read only `TIINGO_API_TOKEN` and `KIS_PAPER_*` from the ignored root `.env`.
- Use Tiingo's standard EOD endpoint for the three fixed ETFs.
- Use KIS virtual-account endpoints only for account identity, cash, orderable
  funds, positions, and open orders.
- Keep `THERICHER_MODE=off`. Never print or persist secrets or unmasked account
  identifiers, including in Git, artifacts, logs, tests, or Claude prompts.

No paid data, KIS order submit/cancel, paper capital authority, KIS live
credential access, live behavior, or mode change is approved.

## Required Work

1. Data preserves exact Tiingo EOD responses for `2022-11-22` through
   `2026-06-22` under `D:\market_data`, then builds and validates one immutable
   snapshot from `divCash` and `splitFactor` with r2 lineage.
2. Independent Validation checks rights, full observed-session coverage, date
   semantics, hashes, event mapping, and retrospective-only limits.
3. Research runs the existing 18 baseline and 18 candidate replays only if the
   snapshot is accepted. Reuse all six checkpoint bytes and train zero models.
4. Execution adds the smallest read-only KIS paper boundary needed to fetch and
   type account, buying-power, position, and open-order evidence, then performs
   one masked snapshot and reconciliation. It must have no submit side effect.
5. Codex integrates both lanes, runs simplification review, refreshes stateboards
   and the next single goal, verifies, commits, and pushes.

A blocked Data or KIS source must not stop the other ready lane. After read-only
KIS reconciliation, propose a paper capital envelope for operator approval; do
not place the canary order in this objective.

## Boundaries

- Keep raw r2 bars, existing fills, source summaries, checkpoint bytes, and the
  parent `unsupported` verdict unchanged.
- No ranking, promotion, candidate selection, sealed-holdout use, profitability
  claim, new training, scheduler, daemon, dashboard, report/job family, durable
  role, or broad broker/data framework.
- Data stays under `D:\market_data`; generated evidence stays under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Missing, blank, rejected, stale, mismatched, or incomplete credential/account
  evidence fails closed without exposing its value.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose config --quiet`. Report source coverage, replay results, masked
KIS facts, reconciliation, GPU use, intentionally omitted work, commit hash,
and push result.

## Suggested Commit Message

`Run event replay and inspect KIS paper account`
