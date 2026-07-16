# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded cross-sample entry-filter overlay diagnostic.

This advances PnL attribution, feature/model research, and backtest validation
by checking whether the AMD-derived diagnostic entry-filter sketches remain
AMD-specific or recur across the wider existing entry-adverse sample. Use
existing artifacts and selected local bars only.

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
  hidden-units sweep, training-depth sweep, source-context search, or model
  search.
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

3. Ask Claude CLI for a short drift-check before code edits. If this diagnostic
   can run from existing artifacts and artifact-only scripts, no Claude check
   is needed.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts:
   - AMD entry-filter overlay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-amd-entry-filter-overlay-20260716\metrics.json`
   - Wider entry-adverse summary:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-summary-20260716\metrics.json`
   - Wider entry-adverse signal-quality diagnostic:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-signal-quality-20260716\metrics.json`
   - Wider entry-adverse trade-path attribution:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-trade-path-20260716\metrics.json`
   - Wider entry-adverse opportunity attribution:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-opportunity-attribution-20260716\metrics.json`
   - Existing feature-input concentration diagnostic, if useful for
     near-threshold row context:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-feature-input-concentration-20260716\metrics.json`
3. Reuse only selected rows from the existing
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   Yahoo 1m file. Do not acquire data for this task.
4. Do not rerun training, evaluation, replay, calibration, threshold
   derivation, or probability inference.
5. Apply the same fixed diagnostic overlay sketches from the AMD overlay:
   - upper-wick-lower-than-negative-entry,
   - close-position-nonzero,
   - entry-margin-above-negative-entry,
   - all-three-entry-filter-sketch.
6. Record compact artifact-only attribution:
   - which existing wider-sample local-paper entries each overlay would retain
     or skip,
   - whether retained/skipped behavior differs for negative and non-negative
     segments,
   - how near-threshold rows would be labeled when enough trace evidence is
     present,
   - all overlay outcomes with `source: diagnostic_overlay`,
   - original local-paper fills unchanged and still `source: local_paper`,
   - any missing artifact fields that prevent a row from being labeled.
7. If the wider artifacts do not contain enough information to reconstruct
   comparable feature rows without rerunning inference or replay, stop after a
   compact inventory artifact and record the exact missing fields.
8. Do not add a helper, CLI, research job kind, dashboard, scheduler, model
   feature, training path, replay path, threshold search, policy selection,
   simulator exit rule, or broker behavior unless a focused parser bug appears.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Run cross-sample entry filter overlay diagnostic`

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
