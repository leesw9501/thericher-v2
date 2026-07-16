# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Add a bounded local-paper outcome attribution for the raw pre-entry feature
context.

This advances PnL attribution and backtest/walk-forward validation by checking
how the newly described raw pre-entry high adverse/no-lift context relates to
existing broker-free local-paper fills, trade paths, and diagnostic rows before
any new model training, threshold experiment, or replay behavior change.

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
- Do not call any context, band, threshold, model, slice, or feature group
  selected, passed, promoted, production ready, or live ready.
- Do not convert a diagnostic feature context into an execution filter, order
  intent, replay rule, or model-promotion rule.

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

- Raw pre-entry band-attribution artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-raw-band-attribution-cross-slice-20260717-r1\metrics.json`
- Probability-band ablation artifact:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\bounded-feature-input-ablation-probability-bands-cross-slice-20260717-r1\metrics.json`
- Source stability artifact:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-feature-input-stability\engine-agent-depth-target-explicit-slices-20260717-r1-cross-slice-feature-input-stability\metrics.json`
- Depth attribution and trade-path artifacts, if useful:
  `D:\thericher-v2\model-artifacts\candidate-depth-target-attribution\engine-agent-depth-target-explicit-slices-20260717-r1-attribution\metrics.json`
  `D:\thericher-v2\model-artifacts\candidate-depth-target-trade-path-diagnostic\engine-agent-depth-target-explicit-slices-20260717-r1-amat-aem-trade-paths\metrics.json`

## Required Work

1. Inventory only the small artifact subset needed to connect raw pre-entry
   feature context to existing local-paper outcomes. Avoid broad recursive
   scans.
2. Prefer a pure helper inside `research/` or an existing attribution path. Add
   a new job kind only if there is a strong reuse reason.
3. Join or compare only existing evidence:
   - `source: diagnostic_overlay` candidate-entry rows or feature context,
   - `source: local_paper` fills and trade paths,
   - existing external artifacts and local Yahoo rows from `D:\market_data`.
4. If per-signal raw feature context is not persisted in the current artifact,
   reconstruct it from existing stability lineage rather than dumping large
   per-row artifacts.
5. Produce descriptive outcome attribution by raw pre-entry context:
   counts, local-paper fill counts, closed/open path counts when available,
   gross PnL or segment outcome summaries when available, and missing-evidence
   counts.
6. Keep all names descriptive/in-sample. Do not search thresholds, choose a
   feature rule, rerun replay, or modify simulator behavior.
7. Add focused tests proving:
   - local-paper fills remain evidence only,
   - diagnostic rows remain `source: diagnostic_overlay`,
   - no broker/network/credential access is needed,
   - missing event or trade-path evidence is reported instead of guessed,
   - artifacts are outside Git or mocked in tests,
   - no order-intent or execution-filter language/path is introduced.
8. Use temporary Codex sub-agents as sidecar reviewers where useful:
   - Engine Research for attribution interpretation,
   - Execution/Review for source separation and sprawl,
   - Infra/Data for artifact and data-boundary checks.
9. GPU is not expected for this task. Run Docker `research` only if a bounded
   artifact refresh is strictly needed; otherwise keep the work CPU/artifact
   only and explain why.
10. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should use existing artifacts and data, not expand the dataset.
- Acquire additional data only when it is no-auth, lawful,
  license-compatible, and useful for the active engine loop.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact symbols, markets, date ranges,
  formats, artifact names, and blocker reasons in `agents/data.md`,
  `agents/execution.md`, and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report any focused CPU smoke, Docker `research`, or GPU command used.

## Suggested Commit Message

`Add local-paper feature context attribution`

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
