# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first broker-free candidate local-paper replay loop.

This advances feature/model research, paper trading preparation, and PnL
attribution by taking bounded candidate evaluation output and converting model
probabilities into replayable local-paper decisions. The goal is to learn
whether a trained candidate can produce tradable behavior before deeper GPU
training or model registry work.

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
2. Inventory the latest external candidate artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-training-smoke`
   - `D:\thericher-v2\model-artifacts\candidate-evaluation\bounded-candidate-evaluation-smoke`
3. Prefer an explicit local Yahoo intraday snapshot under `D:\market_data` for
   replay input. Use deterministic sample bars only as a fallback smoke path.
4. Add a small local-paper replay harness or research job kind that:
   - consumes candidate training/evaluation artifacts outside Git,
   - reuses the candidate evaluation feature path and lazy PyTorch inference,
   - maps probabilities into bounded buy/sell/hold decisions,
   - submits only to the broker-free local paper simulator,
   - records trades, PnL, drawdown or simple equity attribution, and replay
     fill counts,
   - writes replay artifacts outside Git.
5. Keep replay thresholds descriptive and configurable, but do not make them a
   promotion gate.
6. Add focused tests proving:
   - replay artifacts are outside Git,
   - fills are `source: local_paper`,
   - no credentials, KIS, broker submit, live mode, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - missing model/GPU/backend records a non-fatal prepared state,
   - local paper replay is deterministic/replayable.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing Yahoo intraday snapshots if they are useful for this replay.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active replay loop.
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

Report any focused candidate-replay command, job-runner command, Docker
research command, or GPU inference/replay smoke used.

## Suggested Commit Message

`Add bounded candidate local-paper replay`

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
