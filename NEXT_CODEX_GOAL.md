# Next Codex Goal

## Objective

Complete `kis-intraday-short-session-topology-classification-v1` from the
bound `current_session_short` QQQ/SPY intraday-head terminal. This advances the
data-collection loop by classifying the missing-minute topology using only
bound, source-safe metadata; it does not select a model, claim PnL, or
authorize Paper or live execution.

## Hard Boundaries

- Do not manually invoke KIS, the installed task, a collector, a scheduler, a
  container, or any account/order/quote endpoint. Do not change triggers,
  pacing, concurrency, or task actions.
- Do not read credentials, raw M1 rows, account values, private intents, broker
  bodies, or identifiers. Never read or route `KIS_LIVE_*`.
- Reattach only from the existing source-safe terminal/capture projection and
  its declared bindings. A task exit code alone never proves a fill, PnL,
  alpha, model result, provider finality, or decision-time availability.
- Preserve the immutable 2026-08-15 terminal's
  `input_unavailable/session_coverage_incomplete/current_session_short`
  categories. Do not recompute a receipt by manually running a collector or
  service.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Consume only the bound source-safe projection and metadata categories for
   the current terminal; never read raw M1 rows or inspect private task output.
2. Establish whether the bound short-session metadata supports a bounded
   missing-topology category without exposing row offsets or counts. If it does
   not, record the exact unclassified limitation and leave the installed task
   unchanged.
3. If a classification or contract change is warranted, keep it monotonic,
   fixture-covered, and limited to this exact cumulative-coverage consumer.
4. Treat every incomplete, short, conflicting, unbound, or unclassified result as
   scoped Data evidence only. It cannot become a model input, research
   campaign, PnL claim, or Paper intent.

## Verification

Use the source-safe projection's categorical result and existing
fixture/contract coverage. Run the goal-boundary authority group only if a code
or contract change is required; a source-safe classification record alone does
not change production code.
