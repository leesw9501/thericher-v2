# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add a bounded unique-signal feature-input evaluation for TheRicher v2.

This advances feature/model research and backtest/walk-forward validation by
checking whether the raw pre-entry ranking evidence survives after duplicated
threshold-variant rows are collapsed or summarized by signal.

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

## Current Evidence To Consume

- Slice-aware ablation artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-slice-aware-cross-slice-20260717-r1\metrics.json`
- Full-row ablation artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-fullrow-cross-slice-20260717-r2\metrics.json`
- Source stability artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`

## Required Work

1. Keep the change inside the existing feature-input ablation helper/job unless
   there is a strong reason not to.
2. Add duplicate-aware unique-signal metrics using a stable signal key such as
   `slice_id`, `symbol`, `execution_bar_start`, and `offset`.
3. For each feature group, report unique-signal row context and descriptive
   metrics using a deterministic aggregation policy for repeated variants.
   Include label consistency checks and count any mixed-label signals.
4. Preserve existing selected-row behavior and existing full-row behavior.
5. Keep metric names descriptive/in-sample; do not imply held-out promotion or
   live readiness.
6. Add focused tests proving:
   - selected mode behavior is unchanged,
   - full-row and unique-signal metrics use only `diagnostic_overlay` rows,
   - local-paper fills remain evidence only,
   - duplicate variants collapse or summarize deterministically,
   - mixed-label or single-class signal groups are reported without crashing,
   - lineage traversal paths are rejected,
   - artifacts are outside Git or mocked in tests.
7. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research for metric interpretation,
   - Execution/Review for source separation and sprawl,
   - Infra/Data for artifact and data-boundary checks.
8. If the new payload needs trained per-row scores, run exactly one bounded
   Docker `research` PyTorch CUDA job. Otherwise keep it CPU/artifact-only and
   explain why.
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

`Add unique-signal feature input metrics`

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
