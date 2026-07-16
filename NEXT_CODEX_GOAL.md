# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Explain the short-vs-depth APH signal/path difference from existing artifacts.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by explaining why the longer-depth entry-adverse run lifted
fee-aware trade-path delta while also increasing max drawdown, without running
another training job or changing model axes.

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

3. Ask Claude CLI for a short drift-check before code edits. If this
   attribution can run through existing helpers and artifact-only scripts, no
   Claude check is needed.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed artifacts:
   - short feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-20260716\metrics.json`
   - short replay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-replay-20260716\metrics.json`
   - short trade path:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-fixed-gpu-validation-anet-avgo-trade-path-20260716\metrics.json`
   - depth feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-depth-gpu-validation-anet-avgo-20260716\metrics.json`
   - depth replay:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-depth-gpu-validation-anet-avgo-replay-20260716\metrics.json`
   - depth trade path:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-depth-gpu-validation-anet-avgo-trade-path-20260716\metrics.json`
   - depth-vs-short comparison:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-depth-vs-short-anet-avgo-20260716\metrics.json`
3. Focus on APH, the fill-bearing symbol in both runs. Use existing probability
   traces, threshold variants, local-paper event artifacts, and selected
   `snapshot=2026-06-18` bars.
4. Record a compact artifact-only explanation comparing:
   - threshold pairs,
   - buy opportunity timestamps and probability margins,
   - local-paper entry/exit timestamps and prices,
   - adverse/favorable movement,
   - sell-threshold timing,
   - drawdown-relevant path differences,
   - fill-source verification.
5. Do not rerun training, replay, threshold calibration, or model evaluation
   unless an artifact is missing or unreadable.
6. Do not add a CLI, research job kind, dashboard, scheduler, model feature,
   training path, replay path, threshold search, policy selection, simulator
   exit rule, or broker behavior unless a focused artifact parser bug appears.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data; it should reuse
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`.
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

`Explain entry adverse depth signal path`

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
