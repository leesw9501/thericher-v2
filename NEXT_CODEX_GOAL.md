# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded multi-slice probability calibration probe.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by deriving a small descriptive threshold grid from the
multi-slice candidate's observed probability traces, then replaying that grid
through the existing local-paper robustness path. The goal is to learn why the
first multi-slice candidate produced zero fills under the previous static
threshold grid, not to promote a model.

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
   - `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-multislice-training-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-evaluation\bounded-candidate-multislice-evaluation-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\bounded-candidate-multislice-robustness-smoke`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-multislice-training-smoke.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-multislice-evaluation-smoke.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-multislice-robustness-smoke.json`
3. Inventory only the small useful local Yahoo subset already identified under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Prefer `snapshot=2026-07-09-shadow-t0-8d-probe` for CVS, FCX, and KO.
4. Add a small calibration helper or research job option that:
   - consumes candidate probability traces or runs bounded trace inference once
     per selected slice,
   - derives a capped threshold grid from observed probability quantiles or
     ranges,
   - records the probability ranges and selected threshold pairs,
   - replays the grid through the existing threshold robustness/local-paper path,
   - writes calibration artifacts outside Git.
5. Keep calibration output descriptive only. Do not emit pass/fail, promotion,
   deployment, or gate decisions.
6. Add focused tests proving:
   - calibration artifacts are outside Git,
   - generated thresholds are capped, deterministic, and derived from trace
     probabilities,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing traces/model/GPU/backend records a non-fatal prepared state where
     relevant,
   - downstream robustness replay still uses only `source: local_paper` fills.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this active calibration loop.
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

Report any focused calibration, trace, robustness, Docker research, or GPU
inference command used.

## Suggested Commit Message

`Add bounded probability calibration probe`

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
