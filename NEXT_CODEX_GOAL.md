# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded multi-slice candidate training input.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by training and evaluating one small PyTorch CUDA candidate from
explicit local Yahoo intraday slices instead of deterministic sample bars only.
The goal is to create a better bounded candidate for the existing threshold
robustness replay, not to promote a model.

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
- Run model training or inference that needs PyTorch through Docker `research`.
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
   - `D:\thericher-v2\model-artifacts\candidate-threshold-sweep\bounded-candidate-threshold-sweep-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-threshold-robustness-smoke`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-threshold-robustness-smoke.json`
3. Inventory only the small useful local Yahoo subset already identified under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Prefer:
   - `snapshot=2026-07-09-shadow-t0-8d-probe` for CVS, FCX, and KO,
   - `snapshot=2026-06-18` only if an extra out-of-slice symbol is needed.
4. Add a small capped multi-slice training/evaluation source that:
   - accepts explicit `(snapshot, symbol)` slices,
   - keeps the existing feature shape unless a decision record justifies a
     change,
   - writes artifacts outside Git,
   - records source slices and row counts,
   - remains deterministic and replayable in tests.
5. Train or prepare one bounded PyTorch CUDA candidate inside Docker
   `research` using the multi-slice input. Keep caps small for this goal.
6. Evaluate the candidate and, if the candidate is usable, replay it through
   the existing threshold robustness path on CVS, FCX, and KO.
7. Keep output descriptive only. Do not emit pass/fail, promotion, deployment,
   or gate decisions.
8. Add focused tests proving:
   - multi-slice artifacts are outside Git,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing data/model/GPU/backend records a non-fatal prepared state where
     relevant,
   - generated model artifacts are outside Git or mocked in tests,
   - downstream robustness replay still uses only `source: local_paper` fills.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this active multi-slice training loop.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active goal.
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

Report any focused multi-slice training, evaluation, robustness, Docker
research, or GPU inference command used.

## Suggested Commit Message

`Add bounded multi-slice candidate training`

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
