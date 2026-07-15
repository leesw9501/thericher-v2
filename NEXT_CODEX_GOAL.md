# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build the first bounded research experiment queue on top of the local validation
harness.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by turning the current one-off validation smoke into repeatable
short experiments, while preparing one longer GPU candidate without storing
artifacts in Git.

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
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Inspect the new validation harness and the latest artifacts under
   `D:\thericher-v2\model-artifacts\validation`.
2. Add a small experiment runner that can execute a bounded queue of short CPU
   experiments against deterministic sample data and explicit local
   `D:\market_data` snapshots.
3. Keep the first short queue simple: momentum threshold or timeframe
   confirmation sweeps are enough. Prefer existing bars and local resampling.
4. Write concise metrics artifacts outside Git. Include run id, data source,
   parameters, local-paper trades, ending equity, PnL, and replay metadata.
5. If GPU is available, prepare or run one longer candidate smoke job only after
   the CPU queue is repeatable. Artifacts must stay under the configured model
   artifact root.
6. Update `agents/engine-research.md` so the two queues stay visible:
   - short experiments for breadth,
   - longer candidate training for depth.
7. Add focused tests proving:
   - experiments remain broker-free and credential-free,
   - metrics are reproducible from local paper replay,
   - artifact paths are outside Git,
   - external market data use is explicit.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active experiment loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact symbols, markets, date ranges,
  formats, and blocker reasons in `agents/data.md` and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Report any focused experiment, CPU smoke, local-data smoke, or GPU smoke command
used.

## Suggested Commit Message

`Add bounded research experiment queue`

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
