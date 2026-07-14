# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first real market-data foundation for TheRicher v2 while preserving
the engine-first architecture and all hard boundaries.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders.
- Do not read credentials or `.env`.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Keep research warnings separate from execution hard stops.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.

## Required Work

1. Inspect the current repo state and read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
2. Ask Claude CLI for a short drift-check before architecture-changing edits.
3. Implement a small market-data layer:
   - provider protocol/interface,
   - local file/sample provider,
   - `Bar` serialization/deserialization helpers if needed,
   - timeframe resampling for `1m`, `5m`, `10m`, `1h`, `3h`,
   - deterministic sample data fixtures.
4. Add tests proving:
   - resampling is deterministic,
   - generated bars are UTC-aware and complete,
   - no KIS/network call is needed,
   - the backtest harness can consume resampled bars.
5. Preserve the model artifact policy:
   - research artifacts are external to Git,
   - `THERICHER_HOST_MODEL_ARTIFACT_ROOT` points to the host artifact path,
   - Docker research profile mounts it as `/app/model_artifacts`.
6. Update `DECISIONS.md` only for accepted architecture decisions.
7. Keep docs minimal.
8. Run verification:
   - `uv run --extra dev pytest -q`
   - `uv run --extra dev ruff check .`
   - `docker compose config --quiet`
9. Commit and push.

## Suggested Commit Message

`Add market data foundation`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- what was intentionally not built,
- next recommended goal.
