# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded feature-normalization branch for saturated candidate outputs.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by testing whether one artifact-driven input normalization
selector can reduce source-side probability saturation before the next replay
loop.

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
  expansion, preprocessing search, or optimizer search.
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
   - `bounded-weightdecay-bar-pressure-regularization-smoke-20260716`
   - `bounded-weightdecay-bar-pressure-regularization-replay-cap2-20260716`
   - `bounded-weightdecay-opportunity-attribution-20260716`
   - `bounded-hidden4-opportunity-attribution-20260716`
3. Inspect candidate training, evaluation, and probability inference feature
   tensor flow before adding code.
4. Add exactly one bounded preprocessing selector, preferably
   `feature_standardization`, to candidate training and candidate
   feature-branch jobs only.
5. Keep defaults behavior-compatible. Evaluation, replay, attribution, and
   broker-facing code must remain checkpoint/artifact-driven rather than
   accepting an independent preprocessing value.
6. Persist any feature normalization statistics in external model/training
   artifacts and make evaluation/probability inference consume them from the
   artifact lineage.
7. Record the preprocessing axis in training and feature-branch artifacts with
   descriptive-only metadata and no model-promotion language.
8. Add focused tests proving:
   - default feature tensors remain unchanged,
   - invalid preprocessing selectors are rejected,
   - the research job runner passes the selector only to training and
     feature-branch jobs,
   - evaluation/probability paths use artifact-carried normalization metadata,
   - generated artifacts are outside Git or mocked in tests,
   - PyTorch stays confined to Docker `research` and local tests do not import
     torch.
9. Run a bounded Docker `research` feature-branch smoke on existing CVS, FCX,
   and KO local data if the code change is sound. Prefer
   `core_plus_bar_pressure_v1`, `hidden_units=4`, and the new normalization
   selector.
10. If the feature-branch smoke completes, run the existing cap-limited
    feature-branch replay or opportunity attribution path only as needed to
    compare source saturation and holdout opportunity evidence.
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

`Add bounded feature normalization branch`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- feature-normalization branch findings,
- what was intentionally not built,
- next recommended goal.
