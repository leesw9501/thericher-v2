# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded real-data candidate breadth queue.

This advances feature/model research and backtest/walk-forward validation by
running a very small set of short candidate training/evaluation variants on the
existing CVS, FCX, and KO local Yahoo slices. The goal is breadth: learn whether
nearby candidate definitions produce materially different probability behavior
before spending GPU time on longer training. This is not a model promotion,
winner selection, scheduler, or autonomous agent framework.

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
- Keep any simulated fills labeled with `source: local_paper`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Run model training/inference that needs PyTorch through Docker `research`.
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
   - `D:\thericher-v2\model-artifacts\candidate-threshold-calibration\bounded-candidate-multislice-calibration-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-threshold-holdout\bounded-candidate-calibration-holdout-smoke`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-calibration-holdout-smoke.json`
3. Reuse only the useful local Yahoo subsets already identified under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`:
   - training/evaluation: `snapshot=2026-07-09-shadow-t0-8d-probe`,
   - holdout reference: `snapshot=2026-06-18`.
   Avoid expensive full recursive scans unless needed.
4. Add a small candidate breadth helper or research job option that:
   - defines a capped queue of at most three short candidate variants around
     the current `m1_lb3_b10_s10` family,
   - writes candidate metadata and queue artifacts outside Git,
   - reuses existing candidate training and evaluation primitives,
   - runs each variant under strict `max_bars`, `max_epochs`, and `max_steps`
     caps,
   - records probability/evaluation summaries and artifact paths,
   - records no best/recommended candidate and no promotion/pass/fail decision.
5. Run a CPU/injected smoke baseline first. If sound, run the bounded queue in
   Docker `research` with PyTorch CUDA and external artifacts.
6. Keep the queue descriptive only. If queue results are too weak or mixed,
   record that as research evidence, not as a gate.
7. Add focused tests proving:
   - queue artifacts are outside Git,
   - candidate count and training caps are enforced,
   - existing training/evaluation primitives are reused,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing candidate artifacts/data/model/GPU/backend record non-fatal
     prepared states where relevant.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this active breadth loop.
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

Report any focused breadth queue, training, evaluation, Docker research, or GPU
command used.

## Suggested Commit Message

`Add bounded candidate breadth queue`

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
