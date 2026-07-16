# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Attribute the wider-holdout depth behavior from existing first-evaluation
source-context artifacts.

This advances PnL attribution and feature/model research by explaining why the
deeper source-context artifact produced fewer fills but larger aggregate
fee-aware delta on the wider holdout, concentrated in AMAT and AMZN. Do not
train a new model in this task.

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
  hidden-units sweep, source-context search, feature-set search, or model
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

3. Ask Claude CLI for a short drift-check before code or architecture edits.
   Artifact-only diagnostics using existing helpers and one-off scripts do not
   need a Claude check.

## Required Work

1. Treat `agents/*.md` as lane stateboards, not autonomous workers. Update them
   only where they clarify the active engine loop.
2. Consume these completed wider-holdout artifacts:
   - Short feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-validation-20260716\metrics.json`
   - Deeper feature branch:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch\bounded-entry-adverse-firsteval-source-context-depth-validation-20260716\metrics.json`
   - Short wider-holdout replays:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-batch1-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-batch2-20260716\metrics.json`
   - Depth wider-holdout replays:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-batch1-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-batch2-20260716\metrics.json`
   - Wider-holdout opportunity attributions:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-batch1-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-batch2-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-batch1-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-batch2-20260716\metrics.json`
   - Wider-holdout trade paths:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-trade-path-20260716\metrics.json`
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-trade-path-20260716\metrics.json`
   - Wider-holdout contrast:
     `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-wider-holdout-contrast-20260716\metrics.json`
3. Reuse selected rows from the existing
   `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`
   for AMAT, AMZN, and any short-side comparison symbols needed from the
   existing artifacts. Avoid expensive full recursive scans.
4. Build one compact artifact-only diagnostic that compares short versus depth
   wider-holdout behavior at the fill-bearing segment level:
   - entry probability margin above buy threshold,
   - sell-threshold latency after entry,
   - adverse and favorable excursion from selected local bars,
   - fee-aware segment delta,
   - symbol concentration and duplicate signal rows,
   - zero-fill variants where buy thresholds exceeded observed probability
     ranges.
5. Reconstruct only the existing `core_plus_entry_adverse_v1` feature inputs
   for fill-bearing entry rows and near-threshold rows when useful. Do not add
   a new feature set or selector.
6. Keep all original fills labeled `source: local_paper`. If diagnostic marks
   or retained/skipped sketches are needed, label them separately as
   `source: diagnostic_overlay`.
7. Write the diagnostic under
   `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task. If the diagnostic
   does not expose a data or attribution blocker, make the next goal a bounded
   Docker `research` GPU task so engine research returns to PyTorch CUDA work.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data; it should reuse the existing
  `snapshot=2026-06-18` Yahoo 1m file and existing external artifacts.
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
command if used, GPU availability if checked, and artifact paths used.

## Suggested Commit Message

`Attribute firsteval wider holdout depth behavior`

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
