# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded depth-training candidate target.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by consuming the breadth holdout evidence and scheduling at
most one candidate for a longer but still capped Docker `research` PyTorch CUDA
training/evaluation/holdout loop. This is a GPU research scheduling decision,
not a production winner, promotion rule, scheduler framework, or dashboard.

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
- Do not call the selected depth target a production winner or recommendation.

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
   - `D:\thericher-v2\model-artifacts\candidate-breadth-holdout\bounded-candidate-breadth-holdout-mini-smoke\metrics.json`
   - the three variant calibration artifacts referenced by that bridge,
   - the three variant holdout artifacts referenced by that bridge,
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-breadth-holdout-mini-smoke.json`
3. Reuse existing local Yahoo subsets under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`:
   - depth training/evaluation source:
     `snapshot=2026-07-09-shadow-t0-8d-probe`,
   - holdout replay:
     `snapshot=2026-06-18`.
   Avoid expensive full recursive scans unless needed.
4. Add a small depth target helper or research job path that:
   - consumes the breadth holdout artifact instead of redefining candidates,
   - selects at most one candidate for deeper research scheduling using a
     deterministic descriptive heuristic such as completed holdout first, then
     fewer local-paper fills, lower max drawdown, higher PnL floor, and
     variant id order,
   - records the heuristic as `research_scheduling_only`,
   - trains the chosen candidate with stricter-than-unbounded but deeper caps
     than the breadth queue,
   - evaluates and holdout-replays the depth artifact through existing
     primitives,
   - records probability summaries, local-paper fill counts, PnL, drawdown,
     source verification, and artifact paths,
   - records no best/recommended candidate and no promotion/pass/fail decision.
5. Prefer reusing existing candidate training/evaluation/calibration/holdout
   primitives. Add a new job kind only if it keeps Docker dispatch materially
   simpler and remains a thin leaf.
6. Run a CPU/injected smoke baseline first. If sound, run the bounded depth
   target in Docker `research` with PyTorch CUDA and external artifacts.
7. Add focused tests proving:
   - breadth holdout artifacts are read from outside Git,
   - at most one candidate is scheduled for depth training,
   - the scheduling heuristic is deterministic and non-promotional,
   - existing training/evaluation/holdout/local-paper primitives are reused,
   - local-paper fills remain replayable and labeled `source: local_paper`,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing breadth holdout/training/evaluation/model/data/GPU/backend states
     are non-fatal prepared states where relevant.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots and symbols if they are useful for
  this active depth-training loop.
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

Report any focused depth target, training, evaluation, holdout, Docker
research, or GPU command used.

## Suggested Commit Message

`Add bounded depth candidate target`

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
