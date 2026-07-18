# Next Codex Goal

## Objective

After operator approval, capture and qualify Tiingo distribution and split
evidence for `SPY`, `QQQ`, and `IWM`. Run the frozen 36-cell explicit-event
replay with the existing six checkpoints and zero training only if Data and
independent Validation accept the snapshot as complete.

This advances data collection and feature/model validation.

## Approval Prerequisite

Do not create, request, read, or use a Tiingo credential until the operator
explicitly authorizes a free Starter account/API token for private retrieval of
these three instruments' corporate actions and any required beta activation.
No paid upgrade is authorized.

## Required Work

1. Data preserves raw responses and a normalized, loader-attested snapshot under
   `D:\market_data`, with exact campaign coverage, rights, dates, and r2 lineage.
2. Independent Validation checks completeness, event/session mapping, hashes,
   and retrospective-only limits.
3. Research prepares and runs 18 baseline plus 18 candidate replays from the
   existing checkpoints. Keep raw fills `source: local_paper` and do not train.
4. Compare the explicit-event mask with the heuristic result without ranking,
   promotion, selection, sealed-holdout use, or a profitability claim.
5. Run simplification review, refresh the stateboards and next single goal,
   verify, commit, and push.

## Boundaries

- No KIS, broker/account calls, external orders, live behavior, or paid data.
- No new model, GPU job, credential logging, report/job family, scheduler,
  daemon, dashboard, durable role, or broad data framework.
- Data stays under `D:\market_data`; generated evidence stays under
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep the r2 bars, six checkpoint bytes, source summaries, parent
  `unsupported` verdict, and fixed campaign policy unchanged.

## Verification

Run `uv run --extra dev pytest -q`, `uv run --extra dev ruff check .`, and
`docker compose config --quiet`. Report source coverage, replay results, data
gaps, GPU use, intentionally omitted work, commit hash, and push result.

## Suggested Commit Message

`Run explicit corporate-action sensitivity replay`
