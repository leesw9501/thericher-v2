# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run a bounded short fill-bearing replay contrast for the current entry-adverse
depth branch before any longer GPU training block.

This advances feature/model research, backtest and walk-forward validation, and
PnL attribution by comparing the ADBE/ADI/ADP zero-buy replay evidence against
a small replay slice set that has or can produce broker-free local-paper fills.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon, notification
  loop, or auto-commit worker.
- Do not add a new executable agent unless a specific engine loop need is
  proven and the user explicitly approves it.
- Do not add a new research job kind.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep PyTorch CUDA inside Docker `research` or the existing Engine Research
  Agent runner path. Do not add PyTorch to the base/runtime app path.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  diagnostic rows labeled with `source: diagnostic_overlay`.
- Do not call any context, band, threshold, model, slice, or feature group
  selected, passed, promoted, production ready, or live ready.
- Do not convert a diagnostic context into an execution filter, order intent,
  replay rule, feature rule, or model-promotion rule.

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

- Zero-buy ADBE/ADI/ADP opportunity-gap artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-opportunity-gap-20260717-r1\metrics.json`
- Source replay artifact:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1\metrics.json`
- Source robustness artifact:
  `D:\thericher-v2\model-artifacts\candidate-threshold-robustness\engine-agent-feature-replay-firsteval-depth-adbe-adi-adp-20260717-r1-robustness\metrics.json`
- Existing local data inventory:
  `D:\thericher-v2\model-artifacts\data-agent\market-data-inventory\data-agent-market-data-inventory-cadence-20260717-r2\metrics.json`

## Required Work

1. Check for an existing fill-bearing replay artifact for the same
   entry-adverse depth branch and `snapshot=2026-06-18` symbols before running
   anything new. Prefer existing artifacts over new replay.
2. If existing evidence is enough, produce one compact artifact-only contrast
   outside Git. If not, queue exactly one bounded Engine Research Agent
   `candidate_feature_branch_replay` job using an existing job kind, at most
   three symbols, `max-bars 240`, and existing `D:\market_data` rows.
3. The contrast must report counts, not decisions:
   - trace rows and probability ranges by slice group,
   - buy-threshold hits and near misses at already-derived thresholds only,
   - order intents, events, trades, fills, and PnL ranges,
   - local-paper source verification,
   - diagnostic-overlay source separation,
   - missing evidence counts.
4. If a new replay is queued, use the existing Data Agent inventory runner only
   if it materially helps confirm local data availability.
5. Do not queue longer candidate training in this task. The output should say
   which short contrast evidence is still missing before depth training.
6. Keep Engine Research queues visible in `agents/engine-research.md`:
   - short experiments for breadth,
   - longer candidate training for depth.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Data Policy

- Prefer existing `D:\market_data` snapshots before acquiring anything new.
- This task should not acquire data unless a no-auth, lawful,
  license-compatible source clearly improves the active contrast.
- Stop acquisition for a source when it requires credentials/payment/manual
  access, licensing is unclear, two automated attempts fail, or more data no
  longer improves the active goal.
- If operator help is needed, record exact artifact names, symbols, markets,
  date ranges, formats, and blocker reasons in `agents/data.md`,
  `agents/execution.md`, and the completion report.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused tests,
- any artifact-only smoke command,
- any Engine Research Agent command,
- Docker `research` or GPU command if used,
- artifact paths written outside Git.

## Suggested Commit Message

`Diagnose fill-bearing replay contrast`

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
