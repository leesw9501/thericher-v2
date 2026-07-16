# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add a bounded raw pre-entry band-attribution diagnostic for TheRicher v2.

This advances feature/model research and backtest/walk-forward validation by
explaining which raw pre-entry features characterize the high adverse/no-lift
unique-signal tertile before any deeper model training, threshold experiment,
or replay change.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, or
  auto-commit worker.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not call any band, threshold, model, slice, or feature group selected,
  passed, promoted, production ready, or live ready.
- Do not convert a diagnostic tertile into an execution filter or order intent.

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
   - `agents/engine-research.md`
   - `agents/data.md`
   - `agents/execution.md`
   - `agents/infra.md`
   - `agents/review.md`

3. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep the change tightly scoped.

## Current Evidence To Consume

- Probability-band ablation artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-probability-bands-cross-slice-20260717-r1\metrics.json`
- Unique-signal ablation artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-unique-signal-cross-slice-20260717-r1\metrics.json`
- Source stability artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`

## Required Work

1. Keep the change inside the existing feature-input ablation helper/job unless
   there is a strong reason not to.
2. For raw pre-entry feature groups, add descriptive feature summaries by
   unique-signal probability tertile: counts, medians, means, min/max, and
   per-slice summaries for each raw pre-entry feature.
3. Compare high-tertile raw feature summaries against the overall unique-signal
   population and the low tertile. Keep the comparison descriptive; do not
   search thresholds or choose a feature rule.
4. Preserve existing selected-row, full-row, row-level, slice-aware,
   unique-signal, and probability-band behavior.
5. Keep metric names descriptive/in-sample; do not imply held-out promotion or
   live readiness.
6. Add focused tests proving:
   - selected mode behavior is unchanged,
   - incomplete signal keys skip attribution rather than collapsing together,
   - feature attribution is deterministic under reversed row order,
   - mixed-label signals are reported and skipped from primary attribution,
   - local-paper fills remain evidence only,
   - artifacts are outside Git or mocked in tests.
7. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research for attribution interpretation,
   - Execution/Review for source separation and sprawl,
   - Infra/Data for artifact and data-boundary checks.
8. If feature attribution needs trained per-row scores in the artifact, run
   exactly one bounded Docker `research` PyTorch CUDA job. Otherwise keep it
   CPU/artifact-only and explain why.
9. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing artifacts and data, not expand the dataset.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active engine loop.
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

Also report any focused CPU smoke, Docker `research`, or GPU command used.

## Suggested Commit Message

`Add raw pre-entry band attribution`

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
