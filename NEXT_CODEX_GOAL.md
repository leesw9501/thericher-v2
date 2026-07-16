# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run one artifact-only cross-slice feature-input stability check before spending
more GPU time.

This advances PnL attribution, feature/model research, and backtest and
walk-forward validation by checking whether the ADI/AGG pre-entry separation
direction repeats on a few additional explicit-slice artifacts before any
bounded model-input or GPU training target is queued.

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
- Do not run new GPU training before this cross-slice diagnostic is complete.
- Do not queue another Engine Research Agent GPU job unless current artifacts
  are unreadable or incomplete.
- Do not mutate existing local-paper event artifacts or replay outputs.
- Keep original fills labeled and checked as `source: local_paper`.
- Label diagnostic outcomes as `source: diagnostic_overlay`; do not count them
  as local-paper fills.
- Do not make Execution, Infra, or Review durable executable workers in this
  slice.
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

1. Consume the completed ADI/AGG feature-input diagnostic:
   `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-diagnostic\engine-agent-depth-target-explicit-slices-20260717-r1-adi-agg-feature-input-diagnostic\metrics.json`.
2. Select a small additional explicit-slice set from existing artifacts only.
   Prefer ADBE, AEM, and AMAT if their probability traces and local-paper event
   artifacts are present; otherwise record exact missing paths and choose the
   nearest available explicit-slice traces.
3. Use existing probability traces, event artifacts, and selected local Yahoo
   rows from `snapshot=2026-06-18` only.
4. Reconstruct the same candidate-entry row diagnostic shape:
   - pre-entry 3-bar OHLCV context,
   - probability margin and local probability rank,
   - cluster position and cooldown distance,
   - early 3-bar MAE/MFE bucket,
   - sell-threshold exit outcome,
   - row-level AUC/median separation diagnostics.
5. Compare whether adverse/no-lift versus non-adverse separation direction is
   stable across the added slices and the prior ADI/AGG reference.
6. Explain whether the next bounded target should be:
   - a model-input/feature branch in Docker `research`, or
   - one more artifact-only diagnostic.
7. Preserve local-paper source verification from existing event artifacts and
   separately count all diagnostic outcomes as `source: diagnostic_overlay`.
8. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research sidecar for interpretation,
   - Execution sidecar for source separation,
   - Review sidecar for sprawl and model-promotion language.
9. If artifacts are insufficient, record exact missing paths and stop; do not
   substitute broker, credential, network, dashboard, scheduler, or new GPU
   training work.
10. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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

Also report any focused artifact-only command used, artifact paths, local-paper
source evidence, and diagnostic-overlay source evidence.

## Suggested Commit Message

`Check cross-slice entry feature stability`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used,
- produced diagnostic artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- sub-agents used and what they checked,
- what was intentionally not built,
- next goal.
