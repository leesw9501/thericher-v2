# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse weight-decay wider-sample completion target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by finishing the same `core_plus_entry_adverse_v1` + hidden-units
`4` + `weight_decay=0.01` branch on the remaining wider-sample symbols, so the
regularization evidence can be summarized against the existing 10-symbol
entry-adverse reference without adding another model or feature axis.

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
  expansion, threshold optimizer, preprocessing search, or model search.
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
   builders, or adding a new research job kind. If existing Docker `research`
   jobs and artifact-only scripts are enough, do not add code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume the completed first-six weight-decay context:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-weightdecay-feature-branch-smoke-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-weightdecay-replay-cap2-240bars-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-weightdecay-opportunity-attribution-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-weightdecay-trade-path-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-weightdecay-contrast-summary-20260716\metrics.json`
3. Use existing Docker `research` feature-branch replay code only. Do not
   retrain the model, add features, change preprocessing, or derive a new
   threshold rule.
4. Replay the existing weight-decay feature-branch artifact with cap-2 local
   paper on the remaining selected `snapshot=2026-06-18` symbols:
   - AMD
   - AMGN
   - AMT
   - AMZN
5. If fills occur, produce artifact-only opportunity and trade-path
   attribution; if zero fills occur, produce compact zero-fill attribution.
6. Combine the first-six and remaining-symbol evidence into one descriptive
   10-symbol weight-decay summary, including local-paper verification and
   scope notes for comparison against the existing hidden4 wider sample and
   hidden8 same-sample context.
7. Keep all results descriptive only. Do not rank regularization values, select
   a branch, define promotion criteria, or produce a pass/fail field.
8. Do not add training, features, threshold search, preprocessing search, model
   search, scheduler, dashboard, broker behavior, or new job kinds.
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

`Complete bounded entry-adverse weight-decay wider sample`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- entry-adverse weight-decay wider-sample findings,
- what was intentionally not built,
- next recommended goal.
