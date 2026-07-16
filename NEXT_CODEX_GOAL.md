# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded source-context entry-adverse GPU contrast.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by checking whether the second-holdout zero-fill behavior came
from the completed short/depth artifacts' narrow source context. Keep the model
and feature axes fixed; change only the training/evaluation data context once.

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
- Keep diagnostic overlay outcomes labeled separately from local-paper fills
  with `source: diagnostic_overlay`.
- Keep disabled broker outcomes labeled separately from local paper, for
  example `source: broker_disabled`.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Do not add PyTorch or other heavy ML dependencies to `pyproject.toml`, the
  base engine image, runtime image, or local dev/test path.
- Do not start a broad scheduler, agent framework, promotion gate, dashboard
  expansion, threshold optimizer, preprocessing search, regularization sweep,
  hidden-units sweep, training-depth sweep, or model search.
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

3. Ask Claude CLI for a short drift-check before code edits. If this contrast
   can run through existing Docker `research` job kinds and artifact-only
   scripts, no Claude check is needed.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts:
   - second-holdout contrast:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-depth-vs-short-second-holdout-20260716\metrics.json`
   - APH signal/path attribution:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-depth-vs-short-aph-signal-path-20260716\metrics.json`
   - short feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-20260716\metrics.json`
   - depth feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-depth-gpu-validation-anet-avgo-20260716\metrics.json`
3. Reuse only the existing
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   Yahoo 1m file. Do not acquire data for this task.
4. Keep the candidate fixed:
   - feature set: `core_plus_entry_adverse_v1`,
   - hidden units: `4`,
   - weight decay: `0.001`,
   - feature preprocessing: `feature_standardization`,
   - `max-bars=240`,
   - short bounded caps: `max-epochs=8`, `max-steps=256`.
5. Change only the data context:
   - training/source slices: ADBE, ADI, ADP, AEM, AGG, AMAT, ANET, APH, APO,
     APP, ASML, AVGO from `snapshot=2026-06-18`,
   - direct evaluation and replay slices: AAPL, ABBV, ABNB, ABT, ACN, AMD from
     the same snapshot.
6. Confirm Docker `research` can see PyTorch CUDA/GPU before launching
   training.
7. Run the existing Docker `research` feature-branch job once with the fixed
   candidate settings and changed source context.
8. Run the existing Docker `research` feature-branch replay job once on the
   six second-holdout symbols with threshold-pair cap `2`.
9. Record compact artifact-only attribution:
   - training/evaluation symbols and row counts,
   - probability range/ceiling changes versus the consumed short/depth and
     second-holdout artifacts,
   - threshold pairs and buy/sell opportunity counts,
   - local-paper fill counts and fill-source verification,
   - PnL range and max drawdown,
   - trade-path segment counts when fills exist,
   - zero-fill threshold gaps when fills do not exist,
   - a descriptive comparison against the completed second-holdout contrast.
10. Do not run a feature-set, hidden-units, regularization, preprocessing,
    training-depth, threshold, exit-policy, simulator, broker, dashboard, or
    scheduler branch.
11. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data; it should reuse the existing
  `snapshot=2026-06-18` Yahoo 1m file.
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

Also report any focused test, artifact-only smoke command, Docker `research`
command, GPU availability, and artifact paths used.

## Suggested Commit Message

`Run entry adverse source context contrast`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- validation behavior,
- what was intentionally not built,
- next goal.
