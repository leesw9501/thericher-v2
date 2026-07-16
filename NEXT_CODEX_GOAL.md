# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run a cap-limited calibration holdout replay.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by taking the bounded calibration artifact from the
data-quality-visible candidate and replaying its threshold pairs on disjoint
local Yahoo holdout slices through the existing broker-free local-paper path.

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
- Do not start a broad scheduler, agent framework, promotion gate, or dashboard
  expansion.
- Do not call any threshold, candidate, or model best, recommended, passed,
  promoted, or production ready.

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
2. Use the existing cap-limited calibration artifact:
   `D:\thericher-v2\model-artifacts\candidate-threshold-calibration\bounded-calibration-runtime-3slice-80-cap2-20260716\metrics.json`.
3. Prefer existing disjoint holdout data under
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18`.
4. Run a compact Docker `research` `candidate_threshold_holdout` job on CVS,
   FCX, and KO with bounded `max_bars`. Stop before another long no-output run.
5. Verify all generated fills are `source: local_paper` and record PnL,
   drawdown, fill counts, probability ranges, and artifact paths as
   descriptive evidence only.
6. Compare source calibration versus holdout evidence only descriptively. Do
   not rank, recommend, promote, or pass/fail thresholds or candidates.
7. Add or adjust focused tests only if code changes are required.
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

Report the Docker `research` holdout command used, whether GPU was available,
where artifacts were written, and whether every started container finished or
was explicitly stopped.

## Suggested Commit Message

`Run cap-limited calibration holdout replay`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- holdout replay findings,
- what was intentionally not built,
- next recommended goal.
