# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded threshold robustness replay.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by replaying the same candidate threshold variants across a
small capped set of additional local Yahoo intraday windows or symbols. The
goal is to learn whether the threshold sweep result is robust beyond the first
CVS slice before starting deeper GPU training.

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
- Keep all simulated fills labeled with `source: local_paper`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Run model inference that needs PyTorch through Docker `research`.
- Do not create a broad agent framework, scheduler, promotion gate, or dashboard
  expansion.
- Do not start an unbounded or overnight training run yet.

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

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Inventory the latest external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-training-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-evaluation\bounded-candidate-evaluation-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-replay-comparison\bounded-candidate-replay-comparison-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-probability-trace\bounded-candidate-threshold-sweep-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-sweep\bounded-candidate-threshold-sweep-smoke`
3. Inventory only a small useful subset of `D:\market_data` for additional US
   equity Yahoo intraday snapshots or symbols. Avoid expensive full recursive
   scans unless needed.
4. Add a small robustness harness or research job kind that:
   - uses the same candidate model and bounded threshold pairs,
   - runs or consumes one probability trace per selected slice,
   - replays threshold variants through broker-free local paper,
   - records per-slice PnL, drawdown, fill count, final position, and
     threshold metadata,
   - writes robustness artifacts outside Git.
5. Keep robustness output descriptive only. Do not emit pass/fail, promotion,
   deployment, or gate decisions.
6. Add focused tests proving:
   - robustness artifacts are outside Git,
   - fills remain `source: local_paper`,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing data/model/GPU/backend records a non-fatal prepared state where
     relevant,
   - robustness replay is deterministic/replayable from traces.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this robustness loop.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active robustness loop.
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

Report any focused robustness, trace, sweep, job-runner, Docker research, or GPU
inference command used.

## Suggested Commit Message

`Add bounded threshold robustness replay`

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
