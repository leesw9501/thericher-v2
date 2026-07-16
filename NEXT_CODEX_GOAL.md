# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse source-breadth training contrast target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by testing whether a wider symbol source context reduces the
AMAT-only concentration seen in the `weight_decay=0.001` entry-adverse branch
without changing feature set, model size, preprocessing, or replay machinery.

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
   existing Docker `research` jobs and artifact-only scripts are enough, do not
   add code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume the completed feature-input concentration diagnostic:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-feature-input-concentration-20260716\metrics.json`
3. Use existing Docker `research` feature-branch code only:
   - `--candidate-feature-set core_plus_entry_adverse_v1`
   - `--hidden-units 4`
   - `--weight-decay 0.001`
   - `--feature-preprocessing feature_standardization`
   - strict caps no larger than `max-bars 240`, `max-epochs 4`, and
     `max-steps 128`.
4. Train on ADBE, ADI, ADP, AEM, AGG, and AMAT from
   `snapshot=2026-06-18`.
5. Evaluate and replay symbol-disjoint AMD, AMGN, AMT, and AMZN from
   `snapshot=2026-06-18`.
6. Run cap-2 local-paper replay through the existing
   `candidate_feature_branch_replay` path. If fills occur, produce
   artifact-only opportunity and trade-path attribution; if zero fills occur,
   produce compact zero-fill attribution.
7. Compare the result descriptively against:
   - the feature-input concentration diagnostic,
   - the previous `weight_decay=0.001` CVS/FCX/KO-source 10-symbol summary,
   - the hidden4 wider-sample context.
8. Keep all results descriptive only. Do not rank data sources, select a
   branch, define promotion criteria, or produce a pass/fail field.
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

`Add bounded entry-adverse source-breadth contrast`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- source-breadth contrast findings,
- what was intentionally not built,
- next goal.
