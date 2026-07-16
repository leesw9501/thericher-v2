# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add slice/variant-aware validation metrics for the full-row feature-input
ablation.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by checking whether the raw pre-entry feature signal seen in
the `659` reconstructed diagnostic rows survives label imbalance, per-slice
concentration, and duplicated threshold variants before any deeper GPU training
block.

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
  `D:\thericher-v2\model-artifacts` or the configured artifact root mounted as
  `/app/model_artifacts` in Docker.
- Use Docker `research` with PyTorch CUDA for any GPU/model run.
- Do not add PyTorch to the base/local runtime.
- Do not run a broad hyperparameter sweep.
- Do not mutate existing local-paper event artifacts or replay outputs.
- Keep original fills labeled and checked as `source: local_paper`.
- Label any diagnostic rows or outcomes as `source: diagnostic_overlay`; do not
  count them as local-paper fills.
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

3. Ask Claude CLI for a short drift-check before code, architecture, or policy
   edits. Judge the result against `HANDOFF.md`, `ARCHITECTURE.md`, and
   `DECISIONS.md`. If Claude CLI times out again, record the timeout and keep
   the change tightly scoped.

## Required Work

1. Consume:
   - selected-row ablation artifact:
     `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-cross-slice-20260717-r1\metrics.json`,
   - full-row ablation artifact:
     `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-cross-slice-20260717-r2\metrics.json`,
   - source stability artifact:
     `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`.
2. Add or extend a small research-only helper so the same reconstructed rows can
   report:
   - row counts and label balance,
   - adverse/no-lift majority-rate context,
   - balanced accuracy,
   - AUC or a deterministic fallback when scores are tied,
   - log loss,
   - per-slice metrics,
   - per-variant metrics or grouped variant counts,
   - source separation.
3. Keep the helper artifact-driven. Do not rerun local-paper replay and do not
   create a new report family.
4. Add focused tests proving:
   - selected-row behavior remains unchanged,
   - full-row mode uses only `source: diagnostic_overlay`,
   - local-paper fills remain evidence only,
   - balanced metrics do not reduce to majority-label accuracy,
   - unknown lineage paths are not read,
   - generated artifacts remain outside Git or mocked in tests.
5. If a Docker `research` rerun is useful for the metric payload, run exactly
   one bounded PyTorch CUDA job with tight caps. Otherwise keep the task CPU
   and artifact-only, and say why.
6. Compare selected-row and full-row evidence without selecting or ranking an
   option. Report row counts, label balance, feature-group losses/accuracies,
   balanced metrics, per-slice behavior, and source separation.
7. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research sidecar for interpretation,
   - Execution sidecar for source separation,
   - Infra sidecar for Docker/artifact mount assumptions,
   - Review sidecar for sprawl and promotion-language checks.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing artifacts and data, not expand the dataset.
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

Also report any focused CPU smoke, Docker `research`, or GPU command used,
artifact paths, local-paper source evidence, and diagnostic-overlay evidence.

## Suggested Commit Message

`Add slice-aware feature input metrics`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used and where artifacts were written,
- produced diagnostic or research artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- sub-agents used and what they checked,
- what was intentionally not built,
- next goal.
