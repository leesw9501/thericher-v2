# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded candidate probability trace and threshold sweep.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by preserving one bounded candidate probability trace outside
Git, then replaying a small buy/sell threshold grid against the momentum
baseline comparison evidence. The goal is to learn whether the candidate can
trade often enough without rerunning model inference for every threshold pair.

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
   - `D:\thericher-v2\model-artifacts\candidate-replay\bounded-candidate-replay-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-replay-comparison\bounded-candidate-replay-comparison-smoke`
3. Reuse the explicit local Yahoo intraday snapshot first:
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0-8d-probe\ohlcv_1m.csv.gz`.
4. Add a small probability trace artifact or job path that records, outside Git:
   - candidate metadata and model artifact lineage,
   - ordered symbol/market/timeframe and bounded bar count,
   - per-example probability with signal and execution bar timestamps,
   - source data path and artifact policy,
   - enough alignment data to replay thresholds without another inference pass.
5. Add a small threshold sweep harness or research job kind that:
   - consumes the probability trace when available,
   - otherwise can run one bounded candidate inference through Docker
     `research`,
   - replays a small buy/sell threshold grid through broker-free local paper,
   - compares each candidate threshold result with the existing momentum
     baseline comparison metrics,
   - writes sweep artifacts outside Git.
6. Keep sweep output descriptive only. Do not emit pass/fail, promotion,
   deployment, or gate decisions.
7. Add focused tests proving:
   - probability trace and sweep artifacts are outside Git,
   - fills remain `source: local_paper`,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing trace/model/GPU/backend records a non-fatal prepared state where
     relevant,
   - the sweep is deterministic/replayable from one trace.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots if they are useful for this sweep.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active sweep loop.
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

Report any focused trace, sweep, job-runner, Docker research, or GPU inference
command used.

## Suggested Commit Message

`Add bounded candidate threshold sweep`

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
