# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded disjoint-evaluation feature-branch target.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by letting a feature-branch candidate train on source slices but
derive evaluation probability evidence from explicit disjoint evaluation
slices before the next replay loop.

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

3. Ask Claude CLI for a short drift-check before architecture-changing edits.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Use recent artifacts as context, not as promotion evidence:
   - `bounded-standardized-bar-pressure-feature-normalization-smoke-20260716`
   - `bounded-standardized-bar-pressure-feature-normalization-replay-cap2-20260716`
   - `bounded-standardized-probability-alignment-20260716`
3. Inspect candidate feature-branch training/evaluation data-slice flow before
   changing code.
4. Add one bounded path for feature-branch evaluation to consume explicit
   disjoint evaluation slices while training continues to consume source
   slices.
5. Keep defaults behavior-compatible. If no disjoint evaluation slices are
   provided, feature-branch evaluation must keep its current behavior.
6. Keep evaluation, replay, and probability traces artifact-driven. Do not add
   an independent preprocessing, model, threshold, or replay value to
   downstream jobs.
7. Record training source-slice lineage and evaluation source-slice lineage in
   the feature-branch artifact with descriptive-only metadata and no
   model-promotion language.
8. Add focused tests proving:
   - default feature-branch training/evaluation slice behavior is unchanged,
   - explicit disjoint evaluation slices are passed only to feature-branch
     evaluation,
   - the research job runner exposes the new bounded path only where needed,
   - generated artifacts are outside Git or mocked in tests,
   - no broker/network/credential access is needed,
   - PyTorch stays confined to Docker `research` and local tests do not import
     torch.
9. Run a bounded Docker `research` feature-branch smoke using existing local
   data:
   - source training slices: CVS, FCX, KO from
     `snapshot=2026-07-09-shadow-t0-8d-probe`,
   - disjoint evaluation slices: CVS, FCX, KO from `snapshot=2026-06-18`,
   - feature set: `core_plus_bar_pressure_v1`,
   - hidden units: `4`,
   - feature preprocessing: `feature_standardization`.
10. If the feature-branch smoke completes, run the existing cap-limited replay
    and attribution only as needed to compare source/evaluation/holdout
    probability evidence.
11. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Report any focused tests, Docker `research` commands, GPU availability, and
artifact paths used.

## Suggested Commit Message

`Add bounded disjoint evaluation feature branch`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- disjoint-evaluation feature-branch findings,
- what was intentionally not built,
- next recommended goal.
