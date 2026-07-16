# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded out-of-symbol entry-quality diagnostic target.

This advances feature/model research, backtest/walk-forward validation, and PnL
attribution by explaining the buy opportunities and local-paper entries from the
completed out-of-symbol feature-branch replay before changing another feature,
model, preprocessing, or threshold axis.

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

3. Ask Claude CLI for a short drift-check before architecture-changing edits or
   before adding a new reusable helper.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed external artifacts as inputs:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-out-of-symbol-eval-bar-pressure-standardized-smoke-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-out-of-symbol-eval-bar-pressure-standardized-replay-cap2-240bars-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-out-of-symbol-eval-opportunity-attribution-20260716\metrics.json`
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-out-of-symbol-eval-trade-path-20260716\metrics.json`
3. Reuse only existing local market data from
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   for AAPL, ABNB, ABT, ACN, and ABBV.
4. Inspect replay probability traces and local bars for every buy opportunity
   and every local-paper entry from the replay.
5. Produce one compact external diagnostic artifact that records, at minimum:
   - local-paper source verification,
   - buy opportunity counts by slice and threshold variant,
   - forward 5/15/30-bar gross return marks when available,
   - adverse and favorable excursion after each buy opportunity or entry,
   - whether a sell-threshold signal appeared before the adverse move or
     bounded-window end,
   - which evidence came from diagnostic overlays rather than local-paper
     fills.
6. Add a tiny pure helper and focused tests only if it prevents another manual
   script from being repeated. The helper must accept provided `Bar` and trace
   data, perform no network or credential I/O, and write no artifacts itself.
7. Do not rerun training, broad replay, threshold search, model-axis search, or
   data acquisition unless an input artifact is missing or corrupt.
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

`Add bounded out-of-symbol entry-quality diagnostic`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- entry-quality diagnostic findings,
- what was intentionally not built,
- next recommended goal.
