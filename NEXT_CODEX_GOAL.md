# Next Codex Goal

Read `HANDOFF.md` first, then continue TheRicher v2 from
`C:\Users\Public\Documents\thericher-v2`.

## Objective

Run a broader artifact-only inventory for additional non-AMAT strict
label-ready rows from existing artifacts.

This advances feature/model research, backtest validation, PnL attribution, and
data collection by deciding whether the current non-AMAT branch has enough
existing evidence to justify a later bounded compute question, or should stop
and rotate lanes.

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
- Do not run Docker/GPU compute for this inventory. `docker compose config
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
   - Engine Research: assess whether any newly inventoried non-AMAT rows are
     enough for a future bounded model-input question.
   - Data/Infra: verify artifact paths, local data references, and that no
     Docker/GPU compute or acquisition is needed.
   - Review/Execution: verify source labels, broker boundaries, and
     multi-agent drift.

4. Ask Claude CLI for a short drift-check before architecture-changing edits.
   If it times out, record that and keep changes tightly scoped.

## Evidence To Consume

- Non-AMAT feasibility decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-non-amat-bridge-feasibility-decision-20260717-r1\metrics.json`
- Non-AMAT bridge-feasibility artifact:
  `D:\thericher-v2\model-artifacts\feature-input-stability\engine-agent-non-amat-bridge-feasibility-20260717-r1\metrics.json`
- Independent-evidence scan:
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution\engine-agent-amat-independent-evidence-scan-20260717-r1\metrics.json`
- Duplicate-aware AMAT bridge decision:
  `D:\thericher-v2\model-artifacts\feature-input-ablation\engine-agent-amat-bridge-duplicate-aware-decision-20260717-r1\metrics.json`
- Existing candidate-feature-branch replay/attribution roots under
  `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay-attribution`
  and `D:\thericher-v2\model-artifacts\candidate-feature-branch-replay`.
- Existing feature-input roots under
  `D:\thericher-v2\model-artifacts\feature-input-stability` and
  `D:\thericher-v2\model-artifacts\feature-input-ablation`.
- Local market data only as referenced by existing artifacts, especially:
  `D:\market_data\us_equities\yahoo_intraday_starter\canonical\ohlcv_1m\snapshot=2026-06-18\ohlcv_1m.csv.gz`

Avoid expensive full recursive scans. Start with known artifact directories and
bounded filename/metadata discovery.

## Required Work

1. Inventory existing artifacts for additional non-AMAT rows that can become
   strict feature-input label-ready evidence without replay, training, ablation,
   threshold search, or data acquisition.
2. Deduplicate by timing-context key and source lineage. Carry the current
   non-AMAT baseline of `5` strict label-ready rows and `3` strict unique
   timing-context keys.
3. Determine whether existing artifacts can supply at least `+3` additional
   strict label-ready rows to meet the current default feature-input ablation
   `min_examples=8`.
4. Prefer `+5` additional strict unique timing-context keys before recommending
   any future duplicate-aware compute question.
5. Preserve the ADP `2026-06-09T14:05:00+00:00` missing bar as a conditional
   future data requirement only; do not acquire data in this goal.
6. Build one compact external inventory artifact under
   `D:\thericher-v2\model-artifacts` that records:
   - artifacts scanned,
   - additional strict label-ready rows found,
   - duplicate structure,
   - local-paper and diagnostic-overlay source evidence,
   - whether the branch should stop, stay held, or queue a future bounded
     question.
7. If existing artifacts cannot supply at least `+3` strict rows, record a
   branch stop or lane-rotation recommendation rather than forcing replay or
   compute.
8. Refresh `NEXT_CODEX_GOAL.md` again before ending the task.

## Verification

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
docker compose config --quiet
```

Also report:

- any focused artifact-only smoke command,
- any sidecars used,
- artifact paths written outside Git,
- that Docker/GPU compute was not run for the inventory.

## Suggested Commit Message

`Inventory non-AMAT label-ready evidence`

## Completion Report

Report:

- files changed,
- tests run,
- commit hash,
- which sidecars or executable workers were used,
- data found or acquired under `D:\market_data`,
- data still needed from the operator, if any,
- whether GPU/Docker compute was used and where artifacts were written,
- produced diagnostic/inventory artifacts,
- local-paper source evidence,
- diagnostic-overlay source evidence,
- what was intentionally not built,
- next goal.
