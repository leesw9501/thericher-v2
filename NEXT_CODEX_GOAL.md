# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one bounded longer-depth PyTorch CUDA entry-adverse contrast.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by comparing the completed short fixed entry-adverse validation
block against one deeper but still capped training/evaluation/replay block on
the same data split.

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
  hidden-units sweep, or model search.
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
2. Consume the completed short block as baseline context:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-replay-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-trade-path-20260716\metrics.json`
3. Confirm Docker `research` can see PyTorch CUDA/GPU before launching the
   bounded contrast. Keep any smoke output outside Git.
4. Keep this configuration fixed:
   - `core_plus_entry_adverse_v1`
   - `hidden_units=4`
   - `weight_decay=0.001`
   - `feature_standardization`
   - source slices: ADBE, ADI, ADP, AEM, AGG, AMAT from `snapshot=2026-06-18`
   - evaluation/replay slices: ANET, APH, APO, APP, ASML, AVGO from
     `snapshot=2026-06-18`
5. Increase only bounded training depth, for example up to `max_epochs=16` and
   `max_steps=512`, while keeping `max_bars=240`.
6. Run the existing Docker `research` feature-branch job, then the existing
   feature-branch replay job with threshold-pair cap `2` on the same evaluation
   slices.
7. Record a compact artifact-only comparison against the short block:
   probability range, local-paper fill count, PnL range, max drawdown,
   trade-path segment counts, and fill-source verification.
8. Do not add a CLI, research job kind, dashboard, scheduler, model feature,
   training path, replay path, threshold search, policy selection, simulator
   exit rule, or broker behavior unless the bounded run exposes a focused bug.
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

Also report any focused test, artifact-only smoke command, Docker `research`
command, GPU availability, and artifact paths used.

## Suggested Commit Message

`Run bounded entry adverse GPU validation`

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
