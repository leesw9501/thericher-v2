# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first walk-forward and PnL-attribution layer to the bounded research
experiment queue.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by splitting current short experiments into repeatable
train/evaluation windows before spending longer GPU time on a candidate.

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

1. Inspect `src/thericher_v2/research/experiments.py` and the latest experiment
   artifacts under `D:\thericher-v2\model-artifacts\experiments`.
2. Add a bounded walk-forward runner that reuses the experiment queue and local
   validation harness. Start with simple chronological windows; do not add a
   promotion gate.
3. Add concise attribution metrics per experiment and per window:
   - trade count,
   - ending equity,
   - PnL,
   - max drawdown or worst equity dip,
   - replay fill count and final replay position.
4. Keep deterministic sample data and explicit local `D:\market_data` snapshots
   as the only data sources. Prefer existing bars and local resampling.
5. Write walk-forward metrics artifacts outside Git under the configured model
   artifact root.
6. If GPU is available, keep it in prepared state only unless the walk-forward
   metrics are strong enough to justify one bounded candidate smoke. Artifacts
   must stay under `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
7. Update `agents/engine-research.md` so the two queues stay visible:
   - short experiments and walk-forward breadth,
   - longer candidate training for depth.
8. Add focused tests proving:
   - walk-forward remains broker-free and credential-free,
   - per-window metrics are reproducible from local paper replay,
   - artifact paths are outside Git,
   - external market data use is explicit.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Report any focused experiment, walk-forward smoke, local-data smoke, or GPU
smoke command used.

## Suggested Commit Message

`Add walk-forward research attribution`

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
