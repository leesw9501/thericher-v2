# Next Codex Goal

## Objective

Complete `kis-intraday-causal-attestation-writer-integration-v1`: after the
required drift check, implement and verify the smallest networkless future
attester/writer boundary that binds only fully observed source-safe causal facts
to a later intraday terminal. This advances the data-collection loop without
collecting data, selecting a model, claiming PnL, or authorizing Paper or live
execution.

## Hard Boundaries

- Do not manually invoke KIS, the installed task, a collector, a scheduler, a
  container, or any account/order/quote endpoint. Do not change triggers,
  pacing, concurrency, task actions, or the installed task definition.
- Do not read credentials, raw M1 rows, account values, private intents, broker
  bodies, or identifiers. Never read or route `KIS_LIVE_*`.
- A task exit code alone never proves a fill, PnL, alpha, model result, provider
  finality, or decision-time availability. A task timestamp cannot satisfy an
  independent-clock or decision-time-observation requirement.
- Preserve the immutable 2026-08-15 and 2026-08-17 terminals' scoped
  `input_unavailable/session_coverage_incomplete/current_session_short`
  categories. Do not create, attach, or backfill an attestation for either.
- Do not touch, stage, invoke, or reconcile the alternate IWM collector WIP.

## Required Work

1. Obtain the concise Claude falsification-first drift check before relying on
   an integration decision. It must challenge the independent-clock,
   decision-time-availability, provider-finality, and task/Paper blast-radius
   assumptions.
2. Implement only a networkless, default-deny attester and terminal-hash
   binding: any missing, task-derived, invalid, or mismatched field omits the
   binding and preserves `input_unavailable`.
3. Keep the new stage separate from the QQQ prospective/Paper route, with no
   collector, broker, credential, task-registration, or installed-schedule
   update. Freeze the strongest kill test and focused contract coverage.

## Verification

Run focused contract tests and the goal-boundary authority group, Ruff, and both
Compose configurations. An installed-task update remains a separate decision
after verification and the required drift check.
