# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded entry-adverse hidden8 loss-attribution diagnostic target.

This advances PnL attribution and feature/model research by explaining why the
hidden-units `8` contrast concentrated fills into fee-aware negative AMAT
segments before another model, feature, preprocessing, threshold, or training
axis is tried.

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

3. Ask Claude CLI for a short drift-check before adding a reusable diagnostic
   helper or changing feature-building code. If a one-off artifact-only script
   is enough, do not add a helper.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume only existing external artifacts:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-hidden8-feature-branch-smoke-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-hidden8-replay-cap2-240bars-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-hidden8-opportunity-attribution-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-hidden8-trade-path-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-hidden8-contrast-summary-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-signal-quality-20260716\metrics.json`
3. Resolve probability trace and local-paper event artifact paths from the
   hidden8 replay or robustness metadata. Reuse selected AMAT rows from
   `snapshot=2026-06-18` only for path, feature, and forward diagnostic context
   not already in artifacts.
4. Produce one compact external diagnostic artifact that explains:
   - the hidden8 AMAT entry probabilities and threshold gaps,
   - first sell-threshold timing,
   - `upper_wick_share` and `low_vs_prior_low_return` around the AMAT entries,
   - fixed 5/15/30-bar forward diagnostic marks,
   - adverse/favorable excursion and holding duration,
   - how the hidden8 AMAT path differs from the hidden4 wide-sample AMAT path,
   - local-paper source verification.
5. Keep the result descriptive only. Do not rank hidden-unit values, select a
   branch, define promotion criteria, or produce a pass/fail field.
6. Do not rerun training, replay, threshold search, model-axis search, or data
   acquisition unless an input artifact is missing or corrupt.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

`Add bounded entry-adverse hidden8 loss attribution`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- hidden8 loss-attribution findings,
- what was intentionally not built,
- next recommended goal.
