# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded breadth holdout replay bridge.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by consuming the existing real-data candidate breadth queue and
replaying each candidate on disjoint holdout data through the existing
broker-free local-paper path. The goal is descriptive evidence across nearby
candidate definitions, not a production winner, promotion rule, scheduler, or
dashboard.

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
2. Inventory only the current useful external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-breadth-queue\bounded-candidate-breadth-queue-smoke\metrics.json`
   - the three variant training artifacts referenced by that queue,
   - the three variant evaluation artifacts referenced by that queue,
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-breadth-queue-smoke.json`
3. Reuse existing local Yahoo subsets under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`:
   - breadth source reference:
     `snapshot=2026-07-09-shadow-t0-8d-probe`,
   - holdout replay:
     `snapshot=2026-06-18`.
   Avoid expensive full recursive scans unless needed.
4. Add a small breadth holdout helper or research job path that:
   - consumes the breadth queue artifact instead of redefining candidates,
   - processes at most the three queued variants,
   - reuses existing probability trace, threshold calibration/robustness, and
     local-paper replay primitives where practical,
   - runs bounded holdout replay for CVS, FCX, and KO from `snapshot=2026-06-18`,
   - records per-candidate probability summaries, local-paper fill counts, PnL,
     drawdown, and source verification,
   - records no best/recommended candidate and no promotion/pass/fail decision.
5. Prefer reusing the existing `candidate_breadth_queue` job shape or a small
   artifact consumer over adding yet another broad job kind. Add a new kind only
   if it keeps the CLI materially simpler and remains a thin leaf.
6. Run a CPU/injected smoke baseline first. If sound, run the bounded holdout
   bridge in Docker `research` with PyTorch CUDA and external artifacts.
7. Add focused tests proving:
   - breadth queue artifacts are read from outside Git,
   - no more than three variants are processed,
   - existing trace/replay/local-paper primitives are reused,
   - local-paper fills remain replayable and labeled `source: local_paper`,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing queue/training/evaluation/model/data/GPU/backend states are
     non-fatal prepared states where relevant.
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

Report any focused breadth holdout, replay, Docker research, or GPU command
used.

## Suggested Commit Message

`Add bounded breadth holdout bridge`

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
