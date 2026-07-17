# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run an artifact-only independent-evidence scan for non-AMAT bridge candidates
from existing wider-holdout trade-path artifacts.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by checking whether existing local-paper path evidence can
provide new symbol/timestamp rows before any replay, ablation, or GPU work.

## Current Agent Reality

- Engine Research Agent has an executable single-shot worker:
  `thericher-v2-engine-research-agent`.
- Data Agent has an executable single-shot worker:
  `thericher-v2-data-agent`.
- Execution, Infra, and Review are stateboards plus temporary Codex sidecar
  roles, not repo-owned executable workers.
- Temporary sidecars may run in parallel for scoped review, but do not build a
  durable multi-agent platform, scheduler, daemon, coordinator, notification
  loop, or auto-commit worker in this goal.

## Hard Boundaries

- Do not call KIS APIs.
- Do not place paper or live orders through any broker.
- Do not read credentials, `.env`, or secret-like files.
- Do not expose a public dashboard.
- Do not import v1 modules wholesale.
- Do not create report/gate sprawl.
- Do not create a durable multi-agent platform, scheduler, daemon,
  notification loop, coordinator, or auto-commit worker.
- Do not add a new research job kind.
- Do not run Docker/GPU for this scan.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  reconstructed diagnostic rows labeled with `source: diagnostic_overlay`.
- Avoid promotional model-quality language except when quoting unavoidable
  existing artifact field names.
- Do not convert diagnostic context into an execution filter, order intent,
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

3. Use temporary Codex sidecars for disjoint checks when useful:
   - Engine Research: inspect whether existing trade-path artifacts can supply
     independent non-AMAT rows.
   - Data/Infra: verify local data and artifact roots; confirm no Docker/GPU is
     needed.
   - Review/Execution: verify source labels, broker boundaries, and
     multi-agent drift.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Duplicate-aware AMAT bridge decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-bridge-duplicate-aware-decision-20260717-r1\metrics.json`
- AMAT recurrence/path bridge:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-amat-recurrence-path-bridge-20260717-r1\metrics.json`
- AMAT bridge ablation:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-path-bridge-ablation-20260717-r1\metrics.json`
- Short wider-holdout trade paths:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-short-wider-holdout-trade-path-20260716\metrics.json`
- Depth wider-holdout trade paths:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-firsteval-source-context-depth-wider-holdout-trade-path-20260716\metrics.json`
- Wider-sample trade paths:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-trade-path-20260716\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Inspect the decision, bridge, ablation, and three trade-path artifacts.
2. Build one compact external artifact-only scan under
   `D:\thericher-v2\model-artifacts` that summarizes closed trade/path segments
   outside the current AMAT-heavy bridge keys.
3. Deduplicate by symbol, entry timestamp, and available feature/timing context.
   Record:
   - row count,
   - unique signal count,
   - symbol concentration,
   - label balance if labels can be reconstructed,
   - source artifact lineage,
   - missing feature or bar evidence.
4. Prefer non-AMAT symbols. If the existing artifacts still concentrate in AMAT
   or only repeat the current bridge keys, record the shortfall instead of
   forcing replay.
5. Do not run Docker/GPU, ablation, replay, training, data acquisition, or new
   workers in this goal.
6. Preserve source labels:
   - original fills remain `source: local_paper`,
   - diagnostic rows remain `source: diagnostic_overlay`.
7. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused test or artifact-only smoke command,
- any sidecars used,
- artifact paths written outside Git,
- that Docker/GPU was not run for the scan.

## Suggested Commit Message

`Record AMAT duplicate decision`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker were used and where artifacts were written,
- produced diagnostic artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
