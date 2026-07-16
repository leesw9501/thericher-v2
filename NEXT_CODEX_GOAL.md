# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add the first bounded feature-branch local-paper replay attribution target.

This advances backtest validation and PnL attribution by taking the changed
probability evidence from `core_plus_bar_position_v1` and replaying it through
the broker-free local paper simulator. This is not a threshold-only rerun of the
old compressed candidate; it is the next check for the newly trained feature
branch.

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
2. Inventory only the current useful external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-candidate-feature-branch-mini-smoke\metrics.json`
   - `D:\thericher-v2\model-artifacts\research-jobs\bounded-candidate-feature-branch-mini-smoke.json`
   - `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-feature-branch-mini-smoke-training\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-evaluation\bounded-candidate-feature-branch-mini-smoke-evaluation\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-training\bounded-candidate-feature-branch-mini-smoke-training\model.pt`
   - the referenced threshold band context artifact.
3. Reuse existing local Yahoo subsets under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m`.
   Avoid expensive full recursive scans and do not acquire new data unless the
   feature-branch replay cannot proceed without it.
4. Add one small feature-branch replay target that:
   - consumes the feature-branch training/evaluation/model artifacts as context,
   - runs a bounded probability trace or equivalent probability feed for the
     feature branch,
   - converts eligible feature-branch decisions into local paper `OrderIntent`s,
   - executes them only through the local paper simulator,
   - records PnL, drawdown, fill count, and probability-distribution evidence
     descriptively,
   - writes all generated artifacts outside Git,
   - does not select a production winner, promotion threshold, or pass/fail
     result.
5. Keep the two research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
6. Add focused tests proving:
   - the replay uses local paper only,
   - context artifacts can be missing and result in a prepared state,
   - no broker/network/credential access is needed,
   - PyTorch remains research-container-only and lazy,
   - generated artifacts remain outside Git or mocked in tests,
   - output stays descriptive and non-promotional.
7. Run a CPU/injected smoke first. If Docker `research` dispatch is added, run
   a bounded Docker smoke using existing local data and external artifacts.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Start from existing `D:\market_data` and external model artifacts.
- Prefer existing Yahoo intraday snapshots before acquiring anything new.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active replay loop.
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

Report any focused feature-branch replay, local-paper, Docker research, or GPU
command used.

## Suggested Commit Message

`Add bounded feature branch replay attribution`

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
