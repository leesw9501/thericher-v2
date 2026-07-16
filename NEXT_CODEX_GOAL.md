# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded out-of-symbol replay probe for the disjoint-evaluation feature
branch.

This advances backtest and walk-forward validation plus PnL attribution by
testing whether the disjoint-evaluation-derived feature-branch thresholds still
produce replayable local-paper behavior on a small set of existing symbols that
were not used in the latest training/evaluation loop.

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
   - `bounded-disjoint-eval-bar-pressure-standardized-smoke-20260716`
   - `bounded-disjoint-eval-bar-pressure-standardized-replay-cap2-20260716`
   - `bounded-disjoint-eval-opportunity-attribution-20260716`
3. Inventory a small useful subset of
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18`
   without doing an expensive full recursive scan.
4. Select a bounded set of up to five symbols that are present in the snapshot
   and were not used by the latest source/evaluation loop (`CVS`, `FCX`, `KO`).
5. Prefer existing data. Acquire no new data unless the current snapshot cannot
   support the probe and any new source is no-auth, lawful,
   license-compatible, and useful for this exact loop.
6. Reuse the existing `candidate_feature_branch_replay` path if possible.
   Avoid new code unless the existing path cannot express the probe.
7. Run a bounded Docker `research` replay using:
   - feature branch artifact:
     `/app/model_artifacts/candidate-feature-branch/bounded-disjoint-eval-bar-pressure-standardized-smoke-20260716/metrics.json`,
   - threshold cap: `2`,
   - existing selected out-of-symbol slices from `snapshot=2026-06-18`.
8. Run artifact-only opportunity attribution if replay completes.
9. Record compact evidence outside Git:
   - selected symbols and why they were available,
   - replay fill count,
   - PnL/drawdown range,
   - opportunity counts,
   - local-paper fill-source verification,
   - artifact paths used.
10. Keep the result descriptive only. Do not rank symbols, pick thresholds,
    select a model, or add promotion language.
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

`Add bounded out-of-symbol replay probe`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- out-of-symbol replay findings,
- what was intentionally not built,
- next recommended goal.
