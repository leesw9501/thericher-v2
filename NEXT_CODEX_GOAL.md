# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

This is an overnight-style long task. Work autonomously through the phases below
until the foundation is complete, verification fails in a way you cannot repair,
or a hard boundary would be crossed.

## Objective

Build the first broker-free local paper execution foundation for TheRicher v2.

This advances the paper trading and live-risk control loops without touching
KIS, credentials, real broker sessions, or real order submission. It also gives
future GPU/model research a local execution target for validation.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Keep research warnings separate from execution hard stops.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Do not expand the dashboard beyond what is needed to verify local state.
- Do not start GPU training in this goal; prepare the execution target first.

## Required First Reads

1. Run:

   ```powershell
   .\scripts\start_next_codex_task.ps1
   ```

2. Then read:
   - `HANDOFF.md`
   - `VISION.md`
   - `ARCHITECTURE.md`
   - `AGENTS.md`
   - `DECISIONS.md`
   - `RUNBOOK.md`
   - `agents/README.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.
   Judge the response against the local docs; do not let Claude own
   implementation.

## Overnight Work Phases

### Phase 1 - Inspect Existing Execution and State

- Inspect `src/thericher_v2/contracts.py`, `execution/`, `state/`, `data/`,
  `backtest/`, and the existing tests.
- Identify the smallest local-only execution surface that can reuse existing
  `Bar`, `EmergencyState`, and event-log contracts.
- Prefer extending existing modules over creating new framework layers.

### Phase 2 - Local Paper Execution Contracts

Implement small immutable/local contracts as needed for:

- submitted local paper order intent,
- accepted/rejected local paper order result,
- deterministic simulated fill,
- canceled local paper order state,
- local paper portfolio or account snapshot if needed.

Use `Decimal`, UTC-aware timestamps, and `schema_version` consistently with
existing contracts.

### Phase 3 - Deterministic Simulator

Implement a broker-free local paper simulator that:

- consumes existing `Bar` data,
- fills accepted orders deterministically from bar open/close or a documented
  local-only rule,
- updates cash, positions, and realized events deterministically,
- rejects duplicate client order ids,
- blocks new orders when local emergency stop is active,
- never reads credentials or `.env`,
- never imports network or KIS client code.

Keep the simulator small. Avoid venue-specific taxes, margin, complex order
types, partial fills, shorting, and live broker semantics unless the current
tests require a minimal local placeholder.

### Phase 4 - Event Log Integration

Connect local paper execution to the existing append-only event flow:

- persist local order accepted/rejected/canceled/fill events,
- ensure replay can recover enough position state for tests,
- keep JSONL as source of truth and SQLite as rebuildable query view.

Do not create a second state system.

### Phase 5 - Focused Tests

Add tests proving:

- no KIS/network call is needed,
- no credentials or `.env` are read,
- duplicate client order ids are rejected,
- emergency stop blocks new local paper orders,
- simulated fills update local positions and cash deterministically from
  `Bar` data,
- order/fill events are persisted and replayable through the existing event
  store or a small extension of it.

Run narrower tests while developing, then the full verification below.

### Phase 6 - Stateboard and Handoff Updates

Before ending:

- update `agents/execution.md` with what was completed and the next execution
  handoff,
- update `agents/engine-research.md` only if the local paper target is ready
  enough to change GPU research readiness,
- keep future GPU research planned as two queues: short experiments for fast
  breadth and longer candidate training for depth, scheduled so the single GPU
  is not idle once research starts,
- refresh `NEXT_CODEX_GOAL.md` with the next single objective,
- keep all stateboard entries short.

## Optional Stretch Work

Only if the core local paper foundation is complete and verified:

- add a tiny backtest-to-local-paper adapter or example test showing a model
  decision can become a local simulated order without broker authority,
- add local paper state to the dashboard snapshot read path without adding new
  dashboard write controls,
- add data-quality warnings that help paper simulation but do not block
  research.

Skip stretch work if it risks crossing boundaries or delaying a clean verified
commit.

## Verification

Required before commit:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also run any focused test command you used while developing and report it.

## Git

- Keep commits small and purposeful.
- Commit and push completed work.
- Suggested commit message:

  ```text
  Add local paper execution foundation
  ```

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- what was intentionally not built,
- next recommended goal,
- whether local paper execution is ready for the first bounded GPU/model
  validation target.
