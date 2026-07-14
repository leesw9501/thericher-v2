# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first bounded model-validation target for TheRicher v2.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by connecting existing market data, a simple model decision,
and the broker-free local paper simulator into one repeatable validation loop.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Keep local paper fills labeled with `source: local_paper`.

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
   - `agents/data.md`
   - `agents/engine-research.md`
   - `agents/execution.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Inventory the useful subset of `D:\market_data` for a small US equity model
   validation loop. Avoid expensive full recursive scans unless needed.
2. Prefer existing data. Acquire additional data only when it is no-auth,
   lawful, license-compatible, and useful for the active validation loop.
3. Build a small validation harness that consumes `Bar` data, produces model or
   ensemble decisions, converts eligible decisions into local paper
   `OrderIntent`s, and executes them through the local paper simulator.
4. Run a CPU smoke baseline first using deterministic sample or local market
   data.
5. If the CPU baseline is sound and the GPU environment is available, prepare or
   run the first bounded GPU experiment. Artifacts must go to
   `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
6. Keep two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
7. Add focused tests proving:
   - validation uses local paper only,
   - no broker/network/credential access is needed,
   - local paper fills remain replayable,
   - generated artifacts are outside Git or mocked in tests.
8. Refresh `NEXT_CODEX_GOAL.md` before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Report any focused test or GPU smoke command used.

## Suggested Commit Message

`Add bounded model validation target`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- what was intentionally not built,
- next recommended goal.
