# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run a longer bounded GPU feature/model validation using existing job kinds.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by giving the current feature branch a deeper but still bounded
Docker `research` run, then replaying the resulting probabilities through the
broker-free local paper path.

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
- Keep simulated fills labeled with `source: local_paper`.
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, or model best, recommended, passed,
  promoted, or production ready.

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
2. Reuse existing Docker `research` job kinds. Do not add a new
   `candidate_*` module or job kind unless the existing path is demonstrably
   insufficient.
3. Start from existing data and artifacts:
   - `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-07-09-shadow-t0-8d-probe\ohlcv_1m.csv.gz`
     for CVS, FCX, and KO,
   - `D:\thericher-v2\model-artifacts\candidate-threshold-band-rerun\bounded-candidate-threshold-band-rerun-mini-smoke\metrics.json`,
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-candidate-feature-branch-mini-smoke\metrics.json`,
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-candidate-feature-branch-replay-mini-smoke\metrics.json`.
4. Run a short Docker `research` smoke first if needed, then run one longer
   bounded feature/model validation using existing `candidate_feature_branch`
   and/or `candidate_feature_branch_replay` paths with stricter caps than the
   mini smoke but still bounded.
5. Record where artifacts were written and whether the RTX 4090 was used.
6. Verify replay evidence remains local-paper-only through the existing
   source-filtered verification.
7. Add or adjust code only if the run reveals a reproducibility or boundary
   issue; keep any fix narrowly tested.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active validation loop.
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

Report the Docker `research` smoke or validation commands used.

## Suggested Commit Message

`Run bounded GPU feature validation`

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
