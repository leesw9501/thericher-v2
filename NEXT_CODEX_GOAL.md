# Next Codex Goal

## Objective

Complete `kis-intraday-next-terminal-reattachment-v1`: reattach the next
task-owned QQQ/SPY intraday-head terminal through the existing source-safe
projector and compare only its bound coverage category with the completed
`current_session_short` baseline. This advances the data-collection loop
without selecting a model, claiming PnL, or authorizing Paper or live execution.

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
  categories. A later terminal may change only its own scoped evidence; do not
  recompute a receipt by manually running a collector or service.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Wait only for the existing task to write a later source-safe terminal; its
   owned due time is not a foreground wait and no duplicate task is permitted.
2. Consume only the later terminal's bound source-safe projection and metadata
   categories; never read raw M1 rows or inspect private task output.
3. Treat every incomplete, short, conflicting, unbound, or unclassified result
   as scoped Data evidence only. It cannot become a model input, research
   campaign, PnL claim, or Paper intent.

## Verification

Use the source-safe projection's categorical result and existing
fixture/contract coverage. Run the goal-boundary authority group only if a code
or contract change is required; a source-safe reattachment alone does not
change production code.
