# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run an explicit-slice Engine Research Agent GPU/depth target through the
single-shot runner, with Data Agent as the companion inventory lane.

This advances feature/model research, backtest and walk-forward validation, and
data collection by correcting the previous runner-queued depth attempt, which
trained and evaluated on GPU but stopped at `prepared_not_depth_targeted`
because no source or holdout slices were queued.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not download market data into the Git workspace.
- Do not acquire market data in this slice unless a tiny no-auth,
  lawful, license-compatible external fixture is absolutely required.
- Do not store generated artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or the configured artifact root.
- Keep PyTorch CUDA confined to the Docker `research` target/profile.
- Keep Data Agent non-GPU and non-Docker in this slice.
- Do not make Execution, Infra, or Review executable workers in this slice.
- Do not add a daemon, scheduler, Windows service, dashboard, notification
  system, broad autonomous multi-agent platform, coordinator, or auto-commit
  path.
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

3. Ask Claude CLI for a short drift-check before any code or architecture
   edits. If the slice stays artifact-only plus stateboard updates, record why a
   drift-check was not needed.

## Required Work

1. Queue and run one Data Agent inventory refresh against existing
   `D:\market_data` before the Engine Research Agent job.
2. Queue exactly one Engine Research Agent `candidate_depth_target` job through
   `thericher-v2-engine-research-agent enqueue-research-job`.
3. Use the existing breadth-holdout artifact:
   `/app/model_artifacts/candidate-breadth-holdout/bounded-candidate-breadth-holdout-mini-smoke/metrics.json`.
4. Include explicit existing Yahoo 1m source and holdout slices. Use the
   runner/CLI format:

   ```powershell
   --data-slice src_adbe=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:ADBE
   --data-slice src_adi=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:ADI
   --data-slice src_adp=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:ADP
   --robustness-slice hold_aem=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:AEM
   --robustness-slice hold_agg=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:AGG
   --robustness-slice hold_amat=/app/market_data/us_equities/yahoo_intraday_starter/canonical/ohlcv_1m/snapshot=2026-06-18/ohlcv_1m.csv.gz:AMAT
   ```

5. Keep the job bounded with explicit caps such as `--max-bars 180`,
   `--max-epochs 16`, and `--max-steps 512`.
6. Execute exactly one Engine Research Agent `run-once`.
7. Inspect the compact metrics and record:
   - Docker `research` command,
   - GPU availability,
   - produced artifacts,
   - whether status reached `candidate_depth_target_ran_only`,
   - calibration/holdout slice counts,
   - local-paper source verification if replay/fills are present.
8. If the job still ends as `prepared_not_depth_targeted`, record the blocker
   and do not run a second Engine Research Agent job in the same slice.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing data, not expand the dataset.
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

Also report any worker commands, focused tests, Docker `research` command
observed through the Engine Research Agent status, GPU availability, and
artifact paths used.

## Suggested Commit Message

`Run explicit-slice depth target`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- Data Agent queue behavior,
- Engine Research Agent queue behavior,
- produced artifacts,
- local-paper source evidence if applicable,
- what was intentionally not built,
- next goal.
