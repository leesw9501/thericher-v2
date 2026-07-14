# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first broker-free local paper execution foundation for TheRicher v2.

This advances the paper trading and live-risk control loops without touching
KIS, credentials, or real order submission.

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
- Do not expand the dashboard beyond what is needed to verify local state.

## Required Work

1. Inspect the current repo state and read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/README.md`
2. Ask Claude CLI for a short drift-check before architecture-changing edits.
3. Implement a small local paper execution layer:
   - order lifecycle contracts for submitted, accepted, filled, rejected, and
     canceled local paper orders,
   - deterministic local paper broker/simulator that consumes existing `Bar`
     data,
   - position and cash updates from simulated fills,
   - duplicate client order id protection,
   - emergency stop hard stop before new local paper orders.
4. Add tests proving:
   - no KIS/network call is needed,
   - no credentials or `.env` are read,
   - duplicate client order ids are rejected,
   - emergency stop blocks new local paper orders,
   - simulated fills update local positions deterministically from `Bar` data.
5. Preserve the model artifact policy:
   - research artifacts are external to Git,
   - `THERICHER_HOST_MODEL_ARTIFACT_ROOT` points to the host artifact path,
   - Docker research profile mounts it as `/app/model_artifacts`.
6. Update `DECISIONS.md` only for accepted architecture decisions.
7. Refresh `NEXT_CODEX_GOAL.md` before ending the task so the next Codex task is
   not stale.
8. Run verification:
   - `uv run --extra dev pytest -q`
   - `uv run --extra dev ruff check .`
   - `docker compose config --quiet`
9. Commit and push.

## Suggested Commit Message

`Add local paper execution foundation`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- what was intentionally not built,
- next recommended goal.
