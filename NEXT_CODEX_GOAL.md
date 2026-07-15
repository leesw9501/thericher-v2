# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded candidate model evaluation loop.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by consuming the external bounded GPU candidate-training output
and evaluating it against deterministic or explicit local market data. The goal
is to prove how a trained candidate artifact becomes replayable research
evidence before starting deeper/longer training.

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
- Keep local paper fills labeled with `source: local_paper` if local paper is
  used.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Run GPU inference/evaluation that needs PyTorch through Docker `research`.
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
2. Inventory the external candidate-training artifacts from:
   `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-training-smoke`.
3. Reuse the existing feature/dataset shape from candidate training so training
   and evaluation cannot silently diverge.
4. Add a small candidate evaluation harness or research job kind that:
   - consumes candidate metadata plus model/metrics artifacts outside Git,
   - consumes deterministic sample bars or an explicit local market-data
     snapshot,
   - runs PyTorch model loading/inference lazily and only inside the research
     path,
   - records bounded classification/decision metrics,
   - writes evaluation artifacts outside Git.
5. If local paper conversion is included, keep it broker-free and replayable;
   otherwise explicitly leave paper conversion for the next goal.
6. Compare the candidate output against a simple baseline already in the repo
   where practical, but do not create a promotion gate.
7. Add focused tests proving:
   - evaluation artifacts are outside Git,
   - missing model/GPU/backend records a non-fatal prepared state,
   - no credentials, KIS, broker submit, or network access is needed,
   - PyTorch remains research-container-only and lazy,
   - training and evaluation feature names match.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from `D:\market_data`.
- Prefer existing data and deterministic samples.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for this active evaluation loop.
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

Report any focused candidate-evaluation command, job-runner command, Docker
research command, or GPU inference/evaluation smoke used.

## Suggested Commit Message

`Add bounded candidate evaluation loop`

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
