# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Build a bounded wider entry-adverse replay sample target.

This advances backtest/walk-forward validation and PnL attribution by replaying
the completed `core_plus_entry_adverse_v1` branch on a capped additional
out-of-symbol sample from existing local data before another feature, model,
preprocessing, threshold, or training axis is tried.

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

3. Ask Claude CLI for a short drift-check before adding a reusable helper,
   changing feature-building code, or adding a new research job kind. If
   existing replay and artifact-only scripts are enough, do not add code.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Inventory the existing
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   file for a deterministic capped additional symbol set:
   - exclude the source symbols `CVS`, `FCX`, and `KO`,
   - exclude the already replayed AAPL, ABNB, ABT, ACN, and ABBV slices unless
     an input artifact is missing,
   - select at most 10 symbols with at least 240 usable 1m rows,
   - record the selected symbols and any shortage in `agents/data.md`.
3. Reuse the existing feature-branch artifact:
   - `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-feature-branch-smoke-20260716\metrics.json`
4. Run the existing Docker `research` replay path with cap-2 threshold pairs
   and `max-bars 240` for the selected symbols. Keep market data read-only via
   `/app/market_data` and artifacts under `/app/model_artifacts`.
5. Produce concise external replay evidence and, if fills occur, artifact-only
   opportunity and trade-path attribution. If zero fills occur, write a compact
   zero-fill attribution instead of forcing another threshold branch.
6. Verify all generated fills are `source: local_paper`. Keep disabled broker
   and diagnostic overlay outcomes separate if they appear.
7. Do not rerun training, threshold search, model-axis search, data acquisition,
   or feature-building changes unless an input artifact is missing or corrupt.
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

`Add bounded wider entry-adverse replay sample`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU was used and where artifacts were written,
- wider entry-adverse replay findings,
- what was intentionally not built,
- next recommended goal.
