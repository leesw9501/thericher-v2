# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse signal-hygiene diagnostic target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by checking whether zero-range, very low-volume-change, or similar
signal-shape patterns recur across existing entry-adverse loss-bearing entries,
non-negative entries, and near-threshold zero-fill rows before another
feature/model or threshold axis is tried.

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
   existing artifacts and one-off artifact-only scripts are enough, do not add
   code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-sourcebreadth-amgn-loss-attribution-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-feature-input-concentration-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-signal-quality-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-summary-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-sourcebreadth-weightdecay001-summary-20260716\metrics.json`
3. Read only the local Yahoo rows needed to validate signal-shape context from
   existing `snapshot=2026-06-18` data.
4. Compare loss-bearing, non-negative, and near-threshold zero-fill signal rows
   across existing entry-adverse artifacts for:
   - zero-range bars,
   - `range_expansion=-1`,
   - very low `volume_change`,
   - `close_position_in_bar=0.5` zero-span rows,
   - immediate forward marks and adverse/favorable movement.
5. Write one compact descriptive artifact outside Git under
   `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
6. Keep all results descriptive only. Do not rank data sources, select a
   branch, define promotion criteria, or produce a pass/fail field.
7. Do not train, rerun replay, add features, search thresholds, change
   preprocessing, start a model search, add a scheduler, expand the dashboard,
   touch broker behavior, or add a new job kind unless a referenced artifact is
   missing or corrupt.
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

Report any focused tests, artifact-only commands, Docker `research` commands,
GPU availability, and artifact paths used.

## Suggested Commit Message

`Add bounded entry-adverse signal-hygiene diagnostic`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- signal-hygiene diagnostic findings,
- what was intentionally not built,
- next goal.
