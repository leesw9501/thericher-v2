# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Record a duplicate-aware decision for the non-AMAT bridge-feasibility branch.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by deciding whether the current non-AMAT bridge evidence stops
here, needs one more existing label-ready row, or has a precise future
replay/data requirement before any ablation or GPU work.

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
- Do not run Docker/GPU compute for this decision. `docker compose config
  --quiet` is allowed only as required non-running verification.
- Do not run ablation, replay, training, threshold search, data acquisition, or
  new executable workers.
- Do not download market data into the Git workspace.
- Do not store generated GPU/model artifacts in the repo. Use
  `D:\thericher-v2\model-artifacts` or `/app/model_artifacts`.
- Keep original local-paper fills labeled with `source: local_paper`; keep
  reconstructed diagnostic rows labeled with `source: diagnostic_overlay`.
- Avoid promotional model-quality language except when quoting unavoidable
  existing artifact field names.
- Do not convert diagnostic context into an execution filter, order intent,
  replay rule, feature rule, threshold rule, or model-promotion rule.

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
   - Engine Research: review whether the feasibility artifact justifies
     another existing artifact probe or should stop the branch.
   - Data/Infra: verify the ADP strict early-bar shortfall and confirm no
     Docker/GPU compute or acquisition is needed.
   - Review/Execution: verify source labels, broker boundaries, and
     multi-agent drift.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Non-AMAT bridge-feasibility artifact:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-non-amat-bridge-feasibility-20260717-r1\metrics.json`
- Independent-evidence scan:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-amat-independent-evidence-scan-20260717-r1\metrics.json`
- Duplicate-aware AMAT bridge decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-bridge-duplicate-aware-decision-20260717-r1\metrics.json`
- AMAT recurrence/path bridge:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-amat-recurrence-path-bridge-20260717-r1\metrics.json`
- AMAT bridge ablation:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-recurrence-path-bridge-ablation-20260717-r1\metrics.json`
- Wider-sample trade paths and opportunity attribution:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-trade-path-20260716\metrics.json`
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\bounded-entry-adverse-wide-sample-opportunity-attribution-20260716\metrics.json`
- Local market data:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

## Required Work

1. Inspect the non-AMAT feasibility artifact and verify:
   - raw-feature bridge-ready row count,
   - strict feature-input label-ready row count,
   - duplicate/variant structure,
   - fee-aware sign balance,
   - ADP strict early-bar shortfall,
   - local-paper and diagnostic-overlay source evidence.
2. Compare the feasibility artifact against the prior AMAT bridge decision and
   current default feature-input ablation `min_examples=8`.
3. Build one compact external decision artifact under
   `D:\thericher-v2\model-artifacts` that records:
   - whether to queue no compute from current evidence,
   - whether one more existing non-AMAT label-ready row is needed,
   - whether a precise future replay or data requirement exists,
   - source lineage and missing evidence.
4. Prefer stopping or holding the branch if existing artifacts do not provide
   enough independent label-ready rows. Do not force replay or ablation.
5. Do not run Docker/GPU compute, ablation, replay, training, data acquisition,
   new workers, or new job kinds in this goal.
6. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

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
- that Docker/GPU compute was not run for the decision.

## Suggested Commit Message

`Record non-AMAT bridge feasibility`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced diagnostic/decision artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
