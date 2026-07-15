# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded calibration holdout replay.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by taking the threshold grid derived by the multi-slice
calibration probe and replaying that same grid on a disjoint local Yahoo
snapshot if usable holdout data exists. The goal is to detect same-slice
calibration circularity before deeper training, not to select a winning
threshold or promote a model.

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
2. Inventory the latest external calibration artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-threshold-calibration\bounded-candidate-multislice-calibration-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-multislice-calibration-smoke-robustness`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-multislice-calibration-smoke.json`
   - `D:\thericher-v2\model-artifacts\candidate-probability-trace\bounded-candidate-multislice-calibration-smoke-cvs`
   - `D:\thericher-v2\model-artifacts\candidate-probability-trace\bounded-candidate-multislice-calibration-smoke-fcx`
   - `D:\thericher-v2\model-artifacts\candidate-probability-trace\bounded-candidate-multislice-calibration-smoke-ko`
3. Inventory only the useful local Yahoo holdout subset under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Start with `snapshot=2026-06-18` and check whether CVS, FCX, and KO are
   present. Avoid expensive full recursive scans unless needed.
4. Add a thin calibration-holdout helper or research job option that:
   - consumes the existing calibration artifact's threshold pairs unchanged,
   - records the source calibration artifact and holdout snapshot/symbols,
   - runs or consumes bounded holdout probability traces once per selected
     slice,
   - replays the unchanged threshold grid through the existing threshold
     robustness/local-paper path,
   - writes holdout artifacts outside Git,
   - records probability ranges, fill counts, PnL/drawdown, and local-paper
     source verification descriptively.
5. If the requested holdout symbols are absent from existing local data, create
   a non-fatal prepared artifact and record the exact data needed in
   `agents/data.md` and the completion report.
6. Keep holdout output descriptive only. Do not emit best/recommended threshold,
   pass/fail, promotion, deployment, or gate decisions.
7. Add focused tests proving:
   - holdout artifacts are outside Git,
   - threshold pairs are consumed from the calibration artifact unchanged,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing calibration artifact, missing holdout data, missing model/GPU, and
     missing backend record non-fatal prepared states where relevant,
   - downstream robustness replay still uses only `source: local_paper` fills.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this active holdout loop.
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

Report any focused holdout, trace, robustness, Docker research, or GPU
inference command used.

## Suggested Commit Message

`Add bounded calibration holdout replay`

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
