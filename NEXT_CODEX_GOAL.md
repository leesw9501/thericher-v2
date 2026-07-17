# Next Codex Goal

Continue TheRicher v2 from `C:\Users\Public\Documents\thericher-v2`.

## Objective

Qualify explicit corporate-action and cash-distribution evidence for the fixed
`SPY`, `QQQ`, `IWM` RAW D1 campaign, then use it to falsify the current factor
sensitivity without retraining.

This advances data collection and feature/model validation. Data leads;
Research reuses the existing six checkpoints only after the event contract is
independently accepted.

## Start

1. Run `.\scripts\start_next_codex_task.ps1` and read its required handoffs.
2. Orchestrate Data, Engine Research, and temporary Validation in parallel where
   ownership does not conflict.
3. Ask Claude to challenge event-date semantics and leakage before integration.

## Boundaries

- No credentials, KIS, broker/account calls, external orders, paid data, or
  live behavior.
- Prefer existing data. Acquire only no-auth, no-cost, lawful, license-compatible
  evidence useful to this objective.
- Data stays under `D:\market_data`; model evidence stays under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep r2 raw bars and fills unchanged. Do not retrain, tune, rank, promote,
  open a sealed holdout, or claim profitability.
- Do not add a job/report family, scheduler, daemon, dashboard, durable role, or
  broad data framework.

## Required Work

1. Inventory bounded existing split and distribution evidence for the three
   instruments; use official issuer sources first if acquisition is necessary.
2. Preserve accepted raw bytes and normalized events in one immutable,
   hash-bound external snapshot and manifest with explicit coverage limits.
3. Test event types, dates, duplicate handling, timezone/session mapping,
   lineage, mount portability, and fail-closed tamper behavior.
4. Replay the existing baselines and six checkpoints with the explicit event
   mask. Compare it with the current heuristic mask without retraining.
5. Independently validate raw-fill integrity, sample exclusion, replay hashes,
   and the sensitivity verdict; run simplification review.
6. Refresh concise stateboards, `HANDOFF.md`, and this next single objective.

Stop acquisition on login/payment/license uncertainty, two failed automated
attempts for one source, loss of active benefit, or projected breach of the 15%
free-space floor. Report operator help only if the remaining evidence requires
it.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose config --quiet`. Report focused validation, external evidence,
data gaps, intentionally omitted work, commit hash, and push result.

## Suggested Commit Message

`Add corporate-action event evidence`
