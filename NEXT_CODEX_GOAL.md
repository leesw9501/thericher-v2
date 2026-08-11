# Next Codex Goal

## Objective

Reattach `kis-intraday-coverage-repair-runtime-observation-v1` only after the
existing QQQ/SPY intraday-head task publishes its next terminal. This advances
the data-collection loop by determining whether the already-built image writes
the repaired cumulative metadata; it does not select a model, claim PnL, or
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
- Preserve the current immutable
  `input_unavailable/session_coverage_incomplete` terminal unless the later
  task-owned receipt differs. Do not recompute a new receipt by manually
  running a collector or service.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. At the task-owned next due terminal, run only the existing credential-free
   projection reader and consume its categorical source-safe output.
2. If the terminal is absent, unavailable, or unchanged, retain that exact
   recovery fact and continue another ready independent package; never
   foreground-wait or create a duplicate schedule.
3. If a later terminal is available, reattest its capture and availability
   bindings, then record only its exact coverage/consumer category and limits
   in Data, Execution, HANDOFF, and orchestration projections.
4. Treat an incomplete, conflicting, or unbound result as scoped Data evidence
   only. It cannot become a model input, research campaign, PnL claim, or
   Paper intent.

## Verification

Use the offline projection reader's categorical result and its existing
fixture/contract coverage. Run the goal-boundary authority group only if a
code or contract change is required; a source-safe receipt reattachment alone
does not change production code.
