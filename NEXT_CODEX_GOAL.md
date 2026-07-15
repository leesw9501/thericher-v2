# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Prepare the first bounded GPU candidate smoke from walk-forward research
artifacts.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by turning the latest walk-forward metrics into one explicitly
bounded candidate run plan without touching broker, credential, or live-trading
surfaces.

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
- Do not add heavy GPU dependencies to the base engine test path.

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

1. Inspect `src/thericher_v2/research/experiments.py` and the latest
   walk-forward artifacts under `D:\thericher-v2\model-artifacts\experiments`.
2. Select one candidate configuration from walk-forward summaries using a
   transparent, non-gating heuristic such as positive total PnL, lower drawdown,
   and replay consistency.
3. Add a small candidate-smoke helper or CLI path that writes candidate metadata
   outside Git. Include:
   - selected experiment id and parameters,
   - source walk-forward artifact path,
   - summary metrics,
   - GPU readiness,
   - artifact policy and output root.
4. If the available research runtime can run a tiny GPU-bound smoke without
   adding base-engine dependencies, run it and write any artifact outside Git.
   Otherwise record `prepared_not_trained` with the blocker reason.
5. Keep deterministic sample data and explicit local `D:\market_data` snapshots
   as the only data sources.
6. Update `agents/engine-research.md` so the two queues stay visible:
   - short experiments and walk-forward breadth,
   - longer candidate training for depth.
7. Add focused tests proving:
   - candidate selection is deterministic and non-gating,
   - artifact paths are outside Git,
   - no broker/network/credential access is needed,
   - base engine tests do not require GPU packages.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active validation loop.
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

Report any focused candidate smoke, GPU readiness, local-data smoke, or
artifact command used.

## Suggested Commit Message

`Prepare bounded GPU candidate smoke`

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
