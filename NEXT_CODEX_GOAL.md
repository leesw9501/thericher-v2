# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse feature-input concentration diagnostic target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by explaining whether the surviving regularized AMAT entries,
hidden4 negative/non-negative entries, and batch2 near-threshold rows occupy
different `core_plus_entry_adverse_v1` feature regions.

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
- Keep diagnostic overlay outcomes labeled separately from local-paper fills.
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, dashboard
  expansion, threshold optimizer, preprocessing search, regularization sweep,
  or model search.
- Do not call any threshold, candidate, feature set, preprocessing branch, or
  model best, recommended, passed, promoted, or production ready.

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

3. Ask Claude CLI for a short drift-check before adding code, changing feature
   builders, adding a new research job kind, or changing agent governance. If
   existing code, local bars, and artifact-only scripts are enough, do not add
   code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume the completed trace-collapse diagnostic:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-regularization-trace-collapse-20260716\metrics.json`
3. Reuse existing probability traces, opportunity/trade-path artifacts, and
   selected local Yahoo rows from `snapshot=2026-06-18`. Do not acquire data.
4. Reconstruct or read only the `core_plus_entry_adverse_v1` feature inputs
   needed for:
   - regularized AMAT buy-opportunity rows that became local-paper entries,
   - hidden4 negative and non-negative entered rows from the wider sample,
   - batch2 rows near the buy thresholds that still produced zero buys.
5. Compare compact distributions for the entry-adverse features and nearby
   context features, including:
   - `upper_wick_share`,
   - `low_vs_prior_low_return`,
   - `close_position_in_bar`,
   - `range_expansion`,
   - `bar_body_return`,
   - probability margin versus buy threshold.
6. Produce one compact external diagnostic artifact that explains whether the
   surviving regularized entries are concentrated in a narrow feature pattern.
7. Keep all results descriptive only. Do not rank branches, select a branch,
   define promotion criteria, or produce a pass/fail field.
8. Do not retrain, rerun replay, add features, threshold search, preprocessing
   search, model search, scheduler, dashboard, broker behavior, or new job
   kinds.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Report any focused tests, artifact-only commands, Docker `research` commands,
GPU availability, and artifact paths used.

## Suggested Commit Message

`Add bounded entry-adverse feature-input diagnostic`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- feature-input concentration findings,
- what was intentionally not built,
- next goal.
