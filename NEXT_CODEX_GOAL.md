# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse lighter weight-decay contrast target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by testing exactly one lighter regularization point for the current
`core_plus_entry_adverse_v1` branch after `weight_decay=0.01` reduced negative
segments but collapsed buy opportunities to a sparse AMAT-only path.

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
   builders, or adding a new research job kind. If existing Docker `research`
   jobs and artifact-only scripts are enough, do not add code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume the completed regularization context:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-weightdecay-wide-sample-summary-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-weightdecay-contrast-summary-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-summary-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-hidden8-loss-attribution-20260716\metrics.json`
3. Use existing Docker `research` feature-branch code only:
   - `--candidate-feature-set core_plus_entry_adverse_v1`
   - `--hidden-units 4`
   - `--weight-decay 0.001`
   - `--feature-preprocessing feature_standardization`
   - strict caps no larger than `max-bars 240`, `max-epochs 4`, and
     `max-steps 128` unless an input artifact proves a smaller cap is required.
4. Train on existing CVS, FCX, and KO source slices from
   `snapshot=2026-07-09-shadow-t0-8d-probe`.
5. Evaluate and replay on ADBE, ADI, ADP, AEM, AGG, and AMAT from
   `snapshot=2026-06-18` first. If the first-six replay is valid, replay the
   remaining AMD, AMGN, AMT, and AMZN slices without retraining.
6. Run cap-2 local-paper replay through the existing
   `candidate_feature_branch_replay` path. If fills occur, produce
   artifact-only opportunity and trade-path attribution; if zero fills occur,
   produce compact zero-fill attribution.
7. Combine first-six and remaining-symbol evidence into one descriptive
   10-symbol lighter weight-decay summary, with scope notes against
   `weight_decay=0.01`, the hidden4 wider sample, and hidden8 same-sample
   context.
8. Keep all results descriptive only. Do not rank regularization values, select
   a branch, define promotion criteria, or produce a pass/fail field.
9. Do not add features, threshold search, preprocessing search, model search,
   scheduler, dashboard, broker behavior, or new job kinds.
10. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Add bounded entry-adverse lighter weight-decay contrast`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- entry-adverse lighter weight-decay contrast findings,
- what was intentionally not built,
- next recommended goal.
